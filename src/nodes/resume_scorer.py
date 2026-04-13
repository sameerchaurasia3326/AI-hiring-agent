"""
src/nodes/resume_scorer.py
───────────────────────────
LangGraph Node: score_resumes
──────────────────────────────
Final JD-Driven Evaluation Engine:
1. Category Alignment: Ingests required_skills, optional_skills, tools, and experience_level.
2. Calibrated Pillars: Weighted match math derived from the dynamic blueprint.
3. Experience Verification: Role-specific seniority alignment.
4. Qualitative Synthesis: Final contextual grading from a specialized LLM agent.
"""
from __future__ import annotations

import json
import math
import asyncio
import re
from typing import List, Optional, Any, Dict
from datetime import datetime, timezone
from loguru import logger
from sqlalchemy import update, select

from src.config import settings
from src.state.schema import HiringState, ScoredResume, ShortlistedCandidate, PipelineStatus
from src.tools.llm_factory import get_llm
from src.tools.hiring_tools import parse_resume_tool
from src.utils.production_safety import StructuredLogger, db_timeout, safe_tool_call, lease_guard, log_event
from src.state.validator import validate_node
from src.db.database import AsyncSessionLocal
from src.db.models import Application, Job

# --- Scorer Prompts ---
_SCORING_SYSTEM = """Evaluate the candidate's alignment with the Dynamic Job Blueprint.
REQUIRED SKILLS: {required_skills}
OPTIONAL SKILLS: {optional_skills}
TOOLS: {tools}

Return ONLY valid JSON: 
{{ 
  "alignment_score": float (0-10), 
  "reasoning": string,
  "strengths": list[string],
  "gaps": list[string]
}}
"""

# GLOBAL SEMAPHORE (Concurrency Control)
llm_semaphore = None

@validate_node
@lease_guard
async def score_resumes(state: HiringState) -> dict:
    """
    LangGraph Node: score_resumes
    Fully JD-Driven Adaptive Screening.
    """
    global llm_semaphore
    if llm_semaphore is None:
        llm_semaphore = asyncio.Semaphore(getattr(settings, "max_concurrent_llm_calls", 3))

    job_id = state.get("job_id")
    trace_id = state.get("trace_id")
    s_logger = StructuredLogger(trace_id=trace_id, job_id=job_id)
    
    blueprint = state.get("scoring_blueprint")
    if not blueprint:
        s_logger.warning("SCORING_SKIPPED", {"reason": "missing_blueprint"})
        return state

    applications = state.get("applications", [])
    if not applications:
        return state

    s_logger.info("SCORING_STARTED", {"candidate_count": len(applications)})
    await log_event(job_id, "SCORING_STARTED")

    llm = get_llm(temperature=0.0)
    new_scored: List[ScoredResume] = []

    async def _process_candidate(app) -> Optional[ScoredResume]:
        async with llm_semaphore:
            try:
                # 1. Extraction (Technical Data)
                resume_text: str = await safe_tool_call(parse_resume_tool.func, resume_path=app["resume_path"])
                if not resume_text or resume_text.startswith("ERROR"):
                    return None
                
                text_lower = resume_text.lower()
                
                # 2. True Elastic Weighting (Normalized to 100)
                req_skills   = blueprint.get("required_skills", [])
                opt_skills   = blueprint.get("optional_skills", [])
                tool_list    = blueprint.get("tools", [])
                exp_baseline = blueprint.get("experience_level", 0.0)

                # -- Tech Pillar (70 points) --
                # Distribute 40 pts among required, 20 pts among optional, 10 pts among tools
                pts_per_req  = 40.0 / len(req_skills) if req_skills else 0.0
                pts_per_opt  = 20.0 / len(opt_skills) if opt_skills else 0.0
                pts_per_tool = 10.0 / len(tool_list)  if tool_list  else 0.0

                found_req   = [kw for kw in req_skills if kw.lower() in text_lower]
                found_opt   = [kw for kw in opt_skills if kw.lower() in text_lower]
                found_tools = [kw for kw in tool_list  if kw.lower() in text_lower]
                
                tech_score = (len(found_req) * pts_per_req) + \
                             (len(found_opt) * pts_per_opt) + \
                             (len(found_tools) * pts_per_tool)

                # -- Experience Pillar (10 points) --
                exp_score = 0.0
                exp_match = re.search(r"(\d+)\+?\s+years", text_lower)
                if exp_match:
                    actual_exp = float(exp_match.group(1))
                    if actual_exp >= exp_baseline: exp_score = 10.0
                    elif actual_exp >= (exp_baseline * 0.7): exp_score = 5.0

                # 3. LLM Qualitative Alignment (20 points)
                prompt = ChatPromptTemplate.from_messages([
                    ("system", _SCORING_SYSTEM.format(
                        required_skills=req_skills, 
                        optional_skills=opt_skills,
                        tools=tool_list
                    )),
                    ("human", f"Resume Text Segment: {resume_text[:4000]}")
                ])
                
                from src.utils.resilience import with_resilience
                response = await with_resilience("ollama", llm.ainvoke, input=prompt.format())
                
                llm_json_match = re.search(r"(\{.*\})", response.content, re.DOTALL)
                if not llm_json_match:
                    raise ValueError("Failed to extract qualitative score from LLM")
                    
                llm_data = json.loads(llm_json_match.group(1))
                llm_points = (float(llm_data.get("alignment_score", 0)) / 10.0) * 20.0
                
                final_score = min(100.0, tech_score + exp_score + llm_points)

                scored_obj = ScoredResume(
                    candidate_id=app["candidate_id"],
                    name=app["name"],
                    email=app["email"],
                    score=round(final_score, 1),
                    reasoning=llm_data.get("reasoning", "Elastic JD-driven evaluation complete."),
                    strengths=found_req + found_tools,
                    gaps=[m for m in req_skills if m not in found_req]
                )

                # Persistence
                async with AsyncSessionLocal() as session:
                    await session.execute(
                        update(Application).where(
                            Application.job_id == job_id,
                            Application.candidate_id == app["candidate_id"]
                        ).values(
                            is_scored=True,
                            score=final_score,
                            ai_reasoning=scored_obj["reasoning"],
                            ai_strengths=scored_obj["strengths"],
                            ai_gaps=scored_obj["gaps"],
                            evaluated_at=datetime.now(timezone.utc),
                            stage="SCREENING_COMPLETE"
                        )
                    )
                    await session.commit()
                
                return scored_obj

            except Exception as e:
                logger.error(f"❌ Scorer failure for {app['name']}: {str(e)}")
                return None

    tasks = [_process_candidate(app) for app in applications]
    results = await asyncio.gather(*tasks)
    new_scored = [r for r in results if r]

    # Post-Scoring: Shortlist Ranking
    threshold = getattr(settings, "resume_score_threshold", 60.0)
    top_n = getattr(settings, "shortlist_top_n", 5)
    
    all_scored = state.get("scored_resumes", []) + new_scored
    shortlist = [
        ShortlistedCandidate(
            candidate_id=r["candidate_id"], name=r["name"],
            email=r["email"], score=r["score"],
            offer_sent=False, rejected=False,
            interview_slot=None, calendar_event_id=None
        )
        for r in sorted(all_scored, key=lambda x: x["score"], reverse=True)
        if r["score"] >= threshold
    ][:top_n]

    return {
        "scored_resumes": new_scored,
        "shortlist": shortlist,
        "pipeline_status": PipelineStatus.SCREENING.value,
        "current_stage": "shortlisting",
        "action_type": "shortlisting_complete"
    }
