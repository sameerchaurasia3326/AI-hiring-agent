"""
src/nodes/resume_scorer.py
───────────────────────────
LangGraph Node: score_resumes
──────────────────────────────
Uses LangChain bind_tools + PydanticOutputParser to score each resume.
Calls parse_resume_tool (LangChain @tool) for extraction.
Returns scored_resumes + shortlist in state delta.
NO routing — graph edge decides next node.
"""
from __future__ import annotations

import json
from typing import List

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from loguru import logger

from src.config import settings
from src.state.schema import HiringState, ScoredResume, ShortlistedCandidate, PipelineStatus
from src.tools.llm_factory import get_llm
from src.tools.hiring_tools import parse_resume_tool


class CandidateScore(BaseModel):
    score:     float      = Field(..., ge=0, le=100)
    reasoning: str        = Field(...)
    strengths: List[str]  = Field(...)
    gaps:      List[str]  = Field(...)


_SYSTEM = """You are a senior technical recruiter. Evaluate the resume against the JD.
Be objective and fair. Focus on: relevant skills, years of experience, measurable achievements, and role fit."""

_HUMAN = """
## Job Description
{jd}

## Candidate: {name}
{resume_text}

{format_instructions}
"""


def score_resumes(state: HiringState) -> dict:
    """Score all unscored resumes using the LLM and parse_resume_tool."""
    applications   = state.get("applications", [])
    jd             = state.get("jd_draft", "")
    threshold      = settings.resume_score_threshold
    top_n          = settings.shortlist_top_n
    already_scored = {r["candidate_id"] for r in state.get("scored_resumes", [])}

    parser = PydanticOutputParser(pydantic_object=CandidateScore)
    chain  = ChatPromptTemplate.from_messages([
        ("system", _SYSTEM), ("human", _HUMAN)
    ]) | get_llm(temperature=0.1) | parser

    new_scored: List[ScoredResume] = []

    for app in applications:
        if app["candidate_id"] in already_scored:
            continue

        # ── Tool invocation via LangChain ──────────────────────────────────────
        resume_text: str = parse_resume_tool.invoke({"resume_path": app["resume_path"]})

        if not resume_text.strip() or resume_text.startswith("ERROR"):
            logger.warning("⚠️  Skipping {}: {}", app["name"], resume_text[:80])
            continue

        try:
            result: CandidateScore = chain.invoke({
                "jd":                  jd,
                "name":                app["name"],
                "resume_text":         resume_text,
                "format_instructions": parser.get_format_instructions(),
            })
            new_scored.append({
                "candidate_id": app["candidate_id"],
                "name":         app["name"],
                "email":        app["email"],
                "score":        result.score,
                "reasoning":    result.reasoning,
                "strengths":    result.strengths,
                "gaps":         result.gaps,
            })
            logger.info("  → {} | {:.1f}/100", app["name"], result.score)
        except Exception as e:
            logger.error("Scoring failed {}: {}", app["name"], e)

    all_scored = state.get("scored_resumes", []) + new_scored

    shortlist: List[ShortlistedCandidate] = [
        {
            "candidate_id": r["candidate_id"], "name": r["name"],
            "email": r["email"], "score": r["score"],
            "interview_slot": None, "calendar_event_id": None,
            "offer_sent": False, "rejected": False,
        }
        for r in sorted(all_scored, key=lambda x: x["score"], reverse=True)
        if r["score"] >= threshold
    ][:top_n]

    logger.info("📊 Scored: {} | Shortlisted: {}", len(all_scored), len(shortlist))
    return {
        "scored_resumes":  all_scored,
        "shortlist":       shortlist,
        "pipeline_status": PipelineStatus.SCREENING.value,
    }
