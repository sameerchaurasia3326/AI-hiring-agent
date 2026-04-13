
import asyncio
import uuid
import sys
from loguru import logger
from src.db.database import AsyncSessionLocal
from src.db.models import Job
from sqlalchemy import select, update
from src.tools.llm_factory import get_llm
from langchain_core.messages import HumanMessage, SystemMessage

async def regenerate_jd_isolated(job_id: str):
    logger.info(f"⚡ [JD Patch] Regenerating JD for job_id={job_id}...")
    
    async with AsyncSessionLocal() as session:
        stmt = select(Job).where(Job.id == (uuid.UUID(job_id) if isinstance(job_id, str) else job_id))
        res = await session.execute(stmt)
        job = res.scalar_one_or_none()
        
        if not job:
            logger.error("❌ [JD Patch] Job not found.")
            return

        title = job.title
        requirements = job.requirements or "Not specified."
        
        logger.info(f"🎯 [JD Patch] Target role: {title}")

        llm = get_llm(temperature=0.7)
        
        prompt = f"""
        Generate a comprehensive and professional Job Description for the following role:
        TITLE: {title}
        REQUIREMENTS: {requirements}

        Requirements Checklist:
        - Cloud Security Architecture
        - AWS IAM, Azure Security Center, or Google Cloud IAM
        - Cloud Security Frameworks (NIST, HIPAA)
        - Penetration Testing in Cloud
        - Compliance (PCI-DSS, SOC2)

        Format:
        **Job Title:** {title}
        **Job Summary:** (a professional summary)
        **Key Responsibilities:** (bullet points)
        **Required Skills:** (bullet points)
        """

        messages = [
            SystemMessage(content="You are an expert technical recruiter specializing in Cloud Security."),
            HumanMessage(content=prompt)
        ]
        
        response = await llm.ainvoke(messages)
        new_jd = response.content
        
        # Update DB
        await session.execute(
            update(Job)
            .where(Job.id == job.id)
            .values(
                jd_draft=new_jd,
                full_jd=new_jd,
                jd_approved=False, # Reset approval to trigger fresh review cycle logic if needed
                status_field="PROCESSING"
            )
        )
        await session.commit()
        
    logger.success("✅ [JD Patch] JD successfully regenerated and aligned with Cloud Security.")

if __name__ == "__main__":
    job_id = "b4e069df-5f95-4916-b0c4-1517bd5a3fc5"
    asyncio.run(regenerate_jd_isolated(job_id))
