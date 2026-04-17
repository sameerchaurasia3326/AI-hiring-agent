from typing import Optional
from langchain_core.prompts import ChatPromptTemplate
from src.tools.llm_factory import get_llm
from loguru import logger

# --- [NEW] Deterministic Role Map (Fast Path) ---
ROLE_MAP = {
    "security": "security_engineer",
    "cyber": "security_engineer",
    "cybersecurity": "security_engineer",
    "infosec": "security_engineer",
    "secops": "security_engineer",
    "backend": "backend_developer",
    "frontend": "frontend_developer",
    "fullstack": "fullstack_developer",
    "graphic": "graphic_designer",
    "designer": "graphic_designer",
    "ui/ux": "graphic_designer",
    "illustrator": "graphic_designer",
    "product": "product_manager",
    "project": "project_manager",
    "devops": "devops_engineer",
    "sre": "devops_engineer",
    "mobile": "mobile_developer",
    "ios": "mobile_developer",
    "android": "mobile_developer",
    "data": "data_scientist",
}

_ROLE_NORMALIZATION_SYSTEM = """You are a job role classification system.
Your goal is to normalize complex job titles into a standard, concise category.

EXAMPLES:
"Senior Lead Cloud Security Professional" -> "Security Engineer"
"Backend Guru (Node.js/Python)" -> "Backend Developer"
"Creative UI/UX Designer and Illustrator" -> "Graphic Designer"

Return ONLY the normalized role name. No preamble.
"""

async def normalize_job_role(title: str, description: Optional[str] = None) -> str:
    """
    Standardizes a job title into a clean professional category.
    Hybrid approach: Regex-based Fast Path -> LLM Smart Path fallback.
    """
    if not title:
        return "general_role"

    title_lower = title.lower()
    
    # ── Stage 1: Fast Path (Deterministic Map) ────────────────────────
    for keyword, normalized in ROLE_MAP.items():
        # Check for word boundary matches to prevent accidental sub-string matches
        import re
        if re.search(rf"\b{keyword}\b", title_lower):
            logger.info("ROLE_NORMALIZATION", f"Fast Path Match: '{title}' -> {normalized}")
            return normalized

    # ── Stage 2: Smart Path (LLM Fallback) ────────────────────────────
    try:
        llm = get_llm(temperature=0.0)
        prompt = ChatPromptTemplate.from_messages([
            ("system", _ROLE_NORMALIZATION_SYSTEM),
            ("human", "Normalize this title: {title}")
        ])
        
        response = await llm.ainvoke(prompt.format(title=title))
        normalized = response.content.strip().lower().replace(" ", "_")
        
        logger.info("ROLE_NORMALIZATION", f"Smart Path Match: '{title}' -> {normalized}")
        return normalized
    except Exception as e:
        logger.error("ROLE_NORMALIZATION_FAILED", f"Fallback to raw title for '{title}': {str(e)}")
        # Default fallback: safe lowercase slug
        return title_lower.replace(" ", "_")
