import json
import asyncio
import re
from typing import List, Dict, Any
from loguru import logger
from langchain_core.prompts import ChatPromptTemplate
from datetime import datetime, timezone

from src.state.schema import HiringState, ScoringBlueprint
from src.tools.llm_factory import get_llm
from src.utils.production_safety import StructuredLogger, db_timeout, safe_tool_call, log_event
from src.state.validator import validate_node
from src.db.database import AsyncSessionLocal
from src.db.models import Job

# Senior AI Engineer Fix: Double-escape curly braces to prevent f-string injection
_ANALYZER_SYSTEM = """You are a senior AI engineer.

Return ONLY valid JSON.
Do NOT include explanation.
Do NOT include markdown.
Do NOT include extra text.

Required JSON schema:
{{
  "required_skills": [],
  "optional_skills": [],
  "tools": [],
  "experience_level": number
}}
"""

@validate_node
async def generate_evaluation_profile(state: HiringState) -> dict:
    """
    LangGraph Node: jd_analyzer
    Analyzes JD text to produce a dynamic, per-job ScoringBlueprint.
    Uses ultra-resilient template escaping and recursive JSON unpacking.
    """
    job_id = state.get("job_id")
    trace_id = state.get("trace_id")
    s_logger = StructuredLogger(trace_id=trace_id, job_id=job_id)
    jd_text = state.get("jd_draft", "")

    if not job_id or not jd_text:
        return state

    s_logger.info("JD_ANALYSIS_STARTED")

    llm = get_llm(temperature=0.0)
    # The format call happens here - braces MUST be escaped in _ANALYZER_SYSTEM
    prompt = ChatPromptTemplate.from_messages([
        ("system", _ANALYZER_SYSTEM),
        ("human", "Analyze this Job Description:\n\n{jd_text}")
    ])

    try:
        from src.utils.resilience import with_resilience
        
        # Inject the JD into the human message correctly
        formatted_prompt = prompt.format(jd_text=jd_text)
        
        response = await with_resilience("ollama", llm.ainvoke, input=formatted_prompt)
        
        content = response.content
        logger.debug(f"JD_ANALYZER_RAW: {content[:500]}")
        
        # 1. Multi-Stage Block Extraction
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON block found in JD analysis")
            
        json_str = json_match.group(0).replace("```json", "").replace("```", "").strip()
        data = json.loads(json_str)
        
        # Phase 17 Resilience: Handle double-encoded LLM strings
        if isinstance(data, str):
            data = json.loads(data)

        if not isinstance(data, dict):
            raise ValueError(f"Decoded data is not a dictionary: {type(data)}")

        # 2. Semantic Key Sanitizer
        def _get_val(raw_dict: dict, target: str, default: Any):
            t_clean = re.sub(r"[^a-z]", "", target.lower())
            for k, v in raw_dict.items():
                if re.sub(r"[^a-z]", "", k.lower()) == t_clean:
                    return v
            return default

        # 3. Normalized Blueprint Assembly
        blueprint = ScoringBlueprint(
            required_skills=[str(s).lower().strip() for s in _get_val(data, "required_skills", []) or []],
            optional_skills=[str(s).lower().strip() for s in _get_val(data, "optional_skills", []) or []],
            tools=[str(s).lower().strip() for s in _get_val(data, "tools", []) or []],
            domain_keywords=[str(s).lower().strip() for s in _get_val(data, "domain_keywords", []) or []], # Kept domain keywords as a secret bonus
            experience_level=float(_get_val(data, "experience_level", 0.0) or 0.0)
        )

        s_logger.success("JD_ANALYSIS_SUCCESS")

        # Persistence
        try:
            async with AsyncSessionLocal() as session:
                from sqlalchemy import update
                await session.execute(
                    update(Job).where(Job.id == job_id).values(scoring_blueprint=blueprint)
                )
                await session.commit()
        except: pass

        return {
            "scoring_blueprint": blueprint,
            "action_type": "jd_analysis_complete"
        }

    except Exception as e:
        s_logger.error("JD_ANALYSIS_FAILED", str(e))
        return state
