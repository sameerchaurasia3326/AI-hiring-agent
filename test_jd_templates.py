import sys
import asyncio
from dotenv import load_dotenv

load_dotenv()

from langchain_core.prompts import ChatPromptTemplate
from src.tools.llm_factory import get_llm
from src.nodes.jd_generator import StructuredJD, _SYSTEM, _HUMAN
from src.config.jd_templates import JD_TEMPLATES
import json

async def main():
    base_state = {
        "job_title": "Backend Developer",
        "department": "Engineering",
        "location": "Remote",
        "employment_type": "Full-Time",
        "experience_required": "3-5 years",
        "salary_range": "Competitive",
        "required_skills": ["Python", "PostgreSQL"],
        "preferred_skills": ["Docker"],
        "joining_requirement": "Immediate",
    }
    
    templates_to_test = ["startup", "corporate", "fresher", "random"]
    
    llm = get_llm(temperature=0.5)
    structured_llm = llm.with_structured_output(StructuredJD)
    chain = ChatPromptTemplate.from_messages([
        ("system", _SYSTEM), ("human", _HUMAN)
    ]) | structured_llm
    
    for template_type in templates_to_test:
        print(f"\n{'='*50}\nTesting template: {template_type}\n{'='*50}")
        selected_template_dict = JD_TEMPLATES.get(template_type, JD_TEMPLATES["startup"])
        template_block = selected_template_dict["template"]
        
        try:
            structured_response = chain.invoke({
                "template_block":      template_block,
                "job_title":           base_state.get("job_title", ""),
                "department":          base_state.get("department", ""),
                "location":            base_state.get("location", ""),
                "employment_type":     base_state.get("employment_type", ""),
                "experience_required": base_state.get("experience_required", ""),
                "salary_range":        base_state.get("salary_range", "Competitive"),
                "required_skills":     ", ".join(base_state.get("required_skills", [])),
                "preferred_skills":    ", ".join(base_state.get("preferred_skills", [])),
                "joining_requirement": base_state.get("joining_requirement", ""),
                "feedback_block":      "",
            })
            jd_json = structured_response.model_dump()
            print(f"Summary ({template_type}): {jd_json.get('summary', '')}")
            print(f"Skills: {jd_json.get('skills', [])}")
            jd_body = jd_json.get('full_jd', '')
            print(f"Full JD snippet: {jd_body[:200]}...")
            
            if jd_json.get("summary") and jd_json.get("skills"):
                print(f"✅ Validation Passed for {template_type}")
            else:
                print(f"❌ Validation Failed for {template_type} (missing keys)")
        except Exception as e:
            print(f"❌ Error for template {template_type}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
