"""
src/nodes/test_generator.py
───────────────────────────
LangGraph Node: generate_tests
───────────────────────────────
Extracts technical requirements from the JD and generates 
a set of multiple-choice questions (MCQs) for candidate assessment.
"""
from __future__ import annotations

import json
import uuid
from typing import List
from pydantic import BaseModel, Field
from loguru import logger
from sqlalchemy import select, delete

from src.db.database import AsyncSessionLocal
from src.db.models import Job, Test, TestQuestion
from src.state.schema import HiringState
from src.tools.llm_factory import get_llm

class MCQ(BaseModel):
    question: str = Field(description="The technical question text.")
    options: List[str] = Field(description="Exactly 4 multiple choice options.")
    correct_index: int = Field(description="Zero-based index of the correct option (0-3).")

class MCQList(BaseModel):
    questions: List[MCQ] = Field(description="List of 5-8 technical MCQ questions.")

_SYSTEM = """You are a technical assessment expert. 
Your goal is to generate a high-quality technical assessment for a candidate based on a Job Description.

Rules:
1. Generate exactly 5-8 multiple-choice questions.
2. Each question must have exactly 4 options.
3. Target the seniority level specified in the JD.
4. Focus on core technical skills, problem-solving, and best practices.
5. Return ONLY valid JSON matching the schema.
"""

_HUMAN = """
Job Title: {job_title}
Job Description:
{jd_draft}

Generate a technical MCQ assessment for this role.
"""

async def generate_tests(state: HiringState) -> dict:
    """Generate MCQ technical assessment based on the JD."""
    if not state.get("job_id"):
        raise Exception("CRITICAL: Missing job_id in generate_tests")

    logger.info("STAGE: generate_tests")
    logger.info("ACTION: {}", state.get("action_type"))
    logger.info("JOB_ID: {}", state.get("job_id"))

    job_id = state.get("job_id")
    test_type = state.get("technical_test_type", "none")
    jd_draft = state.get("jd_draft", "")
    job_title = state.get("job_title", "Candidate")

    if test_type != "mcq":
        logger.info("⏭️ [generate_tests] Skipping MCQ generation (type={})", test_type)
        return {}

    logger.info("🧪 [generate_tests] Generating AI assessment for job_id={}", job_id)

    llm = get_llm()
    prompt = ChatPromptTemplate.from_messages([
        ("system", _SYSTEM),
        ("human", _HUMAN),
    ])

    chain = prompt | llm.with_structured_output(MCQList)

    try:
        # [NEW] Explicit config to avoid 'get_config' outside runnable context
        result: MCQList = await chain.ainvoke({
            "job_title": job_title,
            "jd_draft": jd_draft
        }, config={"callbacks": []})
        
        questions_data = [q.model_dump() for q in result.questions]
        logger.success("✅ [generate_tests] Generated {} questions", len(questions_data))

        # ── Database Sync: Save Questions to Postgres ────────────────────────
        async with AsyncSessionLocal() as session:
            # 1. Ensure a Test record exists for this job
            stmt = select(Test).where(Test.job_id == job_id, Test.type == "mcq")
            existing_test = (await session.execute(stmt)).scalar_one_or_none()

            if existing_test:
                test_id = existing_test.id
                # Clear old questions if any (re-generation logic)
                await session.execute(delete(TestQuestion).where(TestQuestion.test_id == test_id))
            else:
                test_id = uuid.uuid4()
                new_test = Test(id=test_id, job_id=job_id, type="mcq")
                session.add(new_test)
            
            # 2. Add new questions
            for q in result.questions:
                tq = TestQuestion(
                    test_id=test_id,
                    question=q.question,
                    options=q.options,
                    correct_index=q.correct_index
                )
                session.add(tq)
            
            await session.commit()
            logger.info("💾 [generate_tests] Persisted assessment to database for job_id={}", job_id)

        return {
            "technical_test_mcq": questions_data
        }

    except Exception as e:
        logger.error("❌ [generate_tests] Failed to generate tests: {}", e)
        return {"error_log": [f"Test generation failed: {e}"]}
