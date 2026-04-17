import asyncio
import sys
import os
import json
from unittest.mock import MagicMock, AsyncMock

# Add src to path
sys.path.append(os.getcwd())

# MOCK DATABASE AND LOGGING TO PREVENT CONNECTION ERRORS
import src.nodes.jd_analyzer as analyzer
analyzer.AsyncSessionLocal = MagicMock()
analyzer.log_event = AsyncMock()

from src.nodes.jd_analyzer import generate_evaluation_profile
from src.state.schema import HiringState

async def verify_clean_json_profiling():
    print("--- [FINAL PURE-LOGIC VERIFICATION] Clean JSON Audit ---")
    
    test_jds = [
        {
            "title": "Senior Cloud Security Engineer",
            "text": "REQUIRED: AWS Security, SIEM, SOC2. OPTIONAL: Docker, K8s. TOOLS: Splunk. Experience: 5 years."
        },
        {
            "title": "UI/UX Design Lead",
            "text": "REQUIRED: Figma, User Research. OPTIONAL: Motion Design. TOOLS: Principle, Framer. Experience: 3 years."
        }
    ]

    for jd in test_jds:
        print(f"\nAnalyzing: {jd['title']}...")
        state = HiringState(
            job_id="00000000-0000-0000-0000-000000000000",
            trace_id="test-trace-id",
            jd_draft=jd["text"]
        )
        
        # This will now run without touching the database
        result = await generate_evaluation_profile(state)
        blueprint = result.get("scoring_blueprint", {})
        
        print(f"Required Skills:  {blueprint.get('required_skills')}")
        print(f"Optional Skills:  {blueprint.get('optional_skills')}")
        print(f"Tools:            {blueprint.get('tools')}")
        print(f"Exp Level:        {blueprint.get('experience_level')} years")
        
        # Verification
        if "required_skills" in blueprint and len(blueprint["required_skills"]) > 0:
            print(f"Status: ✅ PASS (Clean JSON extracted)")
        else:
            print(f"Status: ❌ FAIL (Extraction failed)")

if __name__ == "__main__":
    asyncio.run(verify_clean_json_profiling())
