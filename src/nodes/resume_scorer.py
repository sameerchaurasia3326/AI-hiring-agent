"""
src/nodes/resume_scorer.py
───────────────────────────
LangGraph Node: score_resumes
──────────────────────────────
Advanced Multi-Stage Evaluation Pipeline:
1. Extraction: Parse resume to structured JSON.
2. Embedding Similarity: Semantic match between JD and Resume.
3. Deep LLM Score: Multi-factor evaluation.
4. Final Ranking: Weighted average of Similarity and LLM scores.
"""
from __future__ import annotations

import json
import math
from typing import List

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from loguru import logger

from src.config import settings
from src.state.schema import HiringState, ScoredResume, ShortlistedCandidate, PipelineStatus
from src.tools.llm_factory import get_llm, get_embeddings
from src.tools.hiring_tools import parse_resume_tool
from src.utils.activity import log_activity_sync


class ParsedResume(BaseModel):
    skills: List[str] = Field(default_factory=list, description="Extract technical and soft skills.")
    experience_years: float = Field(default=0.0, description="Total years of relevant experience.")
    summary: str = Field(default="", description="A 2-sentence summary of the profile.")
    projects: List[str] = Field(default_factory=list, description="Key professional or personal projects.")


class CandidateScore(BaseModel):
    alignment_score: float = Field(default=0.0, ge=0, le=10)
    experience_score: float = Field(default=0.0, ge=0, le=10)
    project_score: float = Field(default=0.0, ge=0, le=10)
    reasoning: str = Field(default="No reasoning provided.")


def calculate_cosine_similarity(v1: List[float], v2: List[float]) -> float:
    dot_product = sum(a * b for a, b in zip(v1, v2))
    mag1 = math.sqrt(sum(a * a for a in v1))
    mag2 = math.sqrt(sum(b * b for b in v2))
    if not mag1 or not mag2:
        return 0.0
    return dot_product / (mag1 * mag2)


_EXTRACTION_SYSTEM = """You are a specialized CV parser.
Return ONLY valid JSON. No preamble, no explanation.

Example Format:
{{
  "skills": ["Python", "AWS"],
  "experience_years": 5.5,
  "summary": "Experienced engineer...",
  "projects": ["Built a compiler"]
}}
"""

_SCORING_SYSTEM = """Evaluate the candidate against the job description.

Return ONLY valid JSON with this structure:
{{
 "alignment_score": float (0-10),
 "experience_score": float (0-10),
 "project_score": float (0-10),
 "reasoning": string
}}

Do not include explanations outside JSON.
Do not include schema descriptions.
"""

_HUMAN_PROMPT = """
## Job Description
{jd}

## Candidate: {name}
{resume_text}

Provide the evaluation in JSON format.
"""

def _robust_pydantic_parse(content: str, pydantic_class: type[BaseModel]) -> BaseModel:
    """
    Attempts to parse LLM output into a Pydantic class, handling common 
    errors like the LLM returning the schema/properties wrapper or 
    plain key-value text.
    """
    import re
    # ── Try 1: JSON Search ────────────────────────────────────────────────
    json_match = re.search(r"(\{.*\})", content, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            # Handle "properties" wrapper (common local LLM mistake)
            if "properties" in data and isinstance(data["properties"], dict):
                data = data["properties"]
            # Clean schema noise
            for k in ["required", "type", "$schema", "definitions"]:
                data.pop(k, None)
            return pydantic_class.model_validate(data)
        except Exception:
            pass # Fall through to Try 2

    # ── Try 2: Key-Value Text Parsing (for Ollama stubbornness) ───────────
    data = {}
    for line in content.splitlines():
        # Match key: value or "key": value
        line_match = re.search(r"^\s*\"?([\w_]+)\"?\s*[:=]\s*(.*)$", line)
        if line_match:
            key, val = line_match.groups()
            val = val.strip().strip(",").strip("\"").strip("'")
            # Type cast numbers
            try:
                if "." in val: data[key] = float(val)
                elif val.isdigit(): data[key] = int(val)
                else: data[key] = val
            except:
                data[key] = val
    
    if data:
        try:
            return pydantic_class.model_validate(data)
        except Exception:
            pass

    # ── Try 3: Raw JSON validation ────────────────────────────────────────
    try:
        return pydantic_class.model_validate_json(content)
    except:
        raise ValueError(f"Could not parse LLM output into {pydantic_class.__name__}")


def score_resumes(state: HiringState) -> dict:
    applications = state.get("applications", [])
    jd = state.get("jd_draft", "")
    threshold = settings.resume_score_threshold
    top_n = settings.shortlist_top_n
    already_scored = {r["candidate_id"] for r in state.get("scored_resumes", [])}

    llm = get_llm(temperature=0.1)
    embeddings_model = get_embeddings()
    
    # ── Stage 0: Embed the JD once ───────────────────────────────────────────
    jd_vector = embeddings_model.embed_query(jd)

    new_scored: List[ScoredResume] = []

    for app in applications:
        if app["candidate_id"] in already_scored:
            continue

        resume_text: str = parse_resume_tool.invoke({"resume_path": app["resume_path"]})
        if not resume_text.strip() or resume_text.startswith("ERROR"):
            continue

        try:
            # ── Stage 1: Extraction ──────────────────────────────────────────
            extract_prompt = ChatPromptTemplate.from_messages([
                ("system", _EXTRACTION_SYSTEM), ("human", "{resume_text}")
            ])
            
            # [Step 4] Print Raw Output
            raw_extraction = llm.invoke(extract_prompt.format(resume_text=resume_text))
            print(f"--- RAW EXTRACTION OUTPUT ({app['name']}) ---\n{raw_extraction.content}\n---")

            # Try structured output if available
            try:
                if hasattr(llm, "with_structured_output"):
                    structured_extract_llm = llm.with_structured_output(ParsedResume, method="json_mode")
                    parsed = structured_extract_llm.invoke(extract_prompt.format(resume_text=resume_text))
                else:
                    raise AttributeError("LLM chain does not support with_structured_output directly")
            except Exception as e:
                logger.warning("Structured extraction unavailable or failed: {}", e)
                try:
                    parsed = _robust_pydantic_parse(raw_extraction.content, ParsedResume)
                except Exception:
                    parsed = ParsedResume(
                        skills=[], experience_years=0.0, 
                        summary="Parsing failed", projects=[]
                    )

            # ── Stage 2: Embedding Similarity ────────────────────────────────
            resume_vector = embeddings_model.embed_query(resume_text)
            similarity = calculate_cosine_similarity(jd_vector, resume_vector)
            similarity_score = similarity * 100  # Normalise to 0-100

            # ── Stage 3: Deep LLM Evaluation ─────────────────────────────────
            score_prompt = ChatPromptTemplate.from_messages([
                ("system", _SCORING_SYSTEM), ("human", _HUMAN_PROMPT)
            ])
            
            # [Step 4] Print Raw Output
            raw_evaluation = llm.invoke(score_prompt.format(
                jd=jd,
                name=app["name"],
                resume_text=resume_text
            ))
            print(f"--- RAW SCORING OUTPUT ({app['name']}) ---\n{raw_evaluation.content}\n---")

            try:
                if hasattr(llm, "with_structured_output"):
                    structured_score_llm = llm.with_structured_output(CandidateScore, method="json_mode")
                    evaluation = structured_score_llm.invoke(score_prompt.format(
                        jd=jd,
                        name=app["name"],
                        resume_text=resume_text
                    ))
                else:
                    raise AttributeError("LLM chain does not support with_structured_output directly")
            except Exception as e:
                logger.warning("Structured scoring unavailable or failed: {}", e)
                try:
                    evaluation = _robust_pydantic_parse(raw_evaluation.content, CandidateScore)
                except Exception:
                    evaluation = CandidateScore(
                        alignment_score=0, experience_score=0, project_score=0,
                        reasoning="Evaluation failed due to non-JSON output"
                    )

            # ── Stage 4: Weighted Ranking ────────────────────────────────────
            # 30% Similarity, 70% LLM Deep Evaluation (Avg of 3 factors)
            # Multiplying by 10 to convert 0-10 scale back to 0-100
            llm_avg = ((evaluation.alignment_score + evaluation.experience_score + evaluation.project_score) / 3) * 10
            final_score = (similarity_score * 0.3) + (llm_avg * 0.7)

            new_scored.append({
                "candidate_id": app["candidate_id"],
                "name":         app["name"],
                "email":        app["email"],
                "score":        round(final_score, 1),
                "reasoning":    f"Similarity: {similarity_score:.1f} | {evaluation.reasoning}",
                "strengths":    getattr(parsed, 'skills', [])[:5],
                "gaps":         ["Review manual profile for specific gaps"]
            })
            logger.info("  → {} | Score: {:.1f} (Sim: {:.1f}, LLM: {:.1f})", 
                        app["name"], final_score, similarity_score, llm_avg)
            
            job_id = state.get("job_id", "")
            if job_id:
                log_activity_sync(
                    job_id, 
                    message=f"Scored candidate {app['name']}: {final_score:.1f}/100", 
                    type="scoring"
                )

        except Exception as e:
            logger.error("❌ Refined scoring failed for {}: {}", app["name"], e)
            with open("/tmp/scorer_debug.log", "a") as f:
                f.write(f"Scoring failed for {app['name']}: {str(e)}\n")
            continue

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

    logger.success("✅ Multi-stage screening complete. Best match: {} ({})", 
                   shortlist[0]["name"] if shortlist else "None", 
                   shortlist[0]["score"] if shortlist else 0)

    return {
        "scored_resumes":  new_scored,
        "shortlist":       shortlist,
        "pipeline_status": PipelineStatus.SCREENING.value,
    }
