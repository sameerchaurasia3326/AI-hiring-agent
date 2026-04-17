import asyncio
import sys
import os

# Add src to path
sys.path.append(os.getcwd())

from src.nodes.resume_scorer import score_resumes, is_security_role, verify_security_domain
from src.state.schema import HiringState

async def verify_guardrail():
    # ── Test 1: Role Detection ──
    titles = ["Cloud Security Engineer", "Graphic Designer", "Senior DevSecOps", "Frontend Dev"]
    print("--- [TEST 1] Role Detection ---")
    for t in titles:
        print(f"Role: {t:30} | Is Security? {is_security_role(t)}")

    # ── Test 2: Domain Filtering ──
    # Aanchal's Resume (Summary of her text)
    aanchal_text = """
    Aanchal Chaurasia - Graphic Designer. 
    Skills: Adobe Creative Suite (Photoshop, Illustrator), Figma, Sketch.
    Experience: Creative Designer Intern, Graphic Design Intern.
    Education: Master of Fine Arts.
    """
    
    # Akash's Resume Mock (Security Professional)
    akash_text = """
    Akash - Cloud Security Engineer.
    Deep experience in OWASP Top 10, SIEM implementation, SOC2 compliance.
    DevSecOps expert with focus on vulnerability research and incident response.
    """

    print("\n--- [TEST 2] Domain Filtering ---")
    aanchal_matches = verify_security_domain(aanchal_text)
    akash_matches = verify_security_domain(akash_text)
    
    print(f"Aanchal (Graphic Designer) | Indicators: {aanchal_matches} | Passed? {aanchal_matches >= 2}")
    print(f"Akash (Security)           | Indicators: {akash_matches} | Passed? {akash_matches >= 2}")

    if aanchal_matches < 2 and akash_matches >= 2:
        print("\n✅ VERIFICATION SUCCESSFUL: Domain filter correctly identifies professional mismatch.")
    else:
        print("\n❌ VERIFICATION FAILED: Guardrail is not discriminating domains correctly.")

if __name__ == "__main__":
    asyncio.run(verify_guardrail())
