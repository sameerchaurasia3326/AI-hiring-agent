import asyncio
import sys
import os

# Add src to path
sys.path.append(os.getcwd())

from src.nodes.resume_scorer import calculate_deterministic_score, ParsedResume

async def verify_deterministic():
    # ── Test Resumes ──
    aanchal_resume = ParsedResume(
        skills=["Photoshop", "Illustrator", "Figma", "Sketch", "Graphic Design"],
        summary="Creative graphic designer with expertise in visual communication and branding."
    )
    aanchal_text = "Adobe Creative Suite expert. Worked on UI/UX mockups in Figma."

    akash_resume = ParsedResume(
        skills=["AWS Security", "OWASP", "SIEM", "Terraform", "Kubernetes", "Splunk", "SOC2"],
        summary="Cloud Security Engineer focused on DevSecOps and Infrastructure security."
    )
    akash_text = "Implemented SIEM with Splunk and GuardDuty. Automated compliance with Terraform and Snyk."

    print("--- [VERIFICATION] Deterministic Scoring Test ---")

    # 1. Test Repeatability (Akash run 3 times)
    print("\n[Audit 1] Verifying Repeatability (Same Resume x3)...")
    scores = []
    for i in range(3):
        res = calculate_deterministic_score(akash_resume, akash_text)
        scores.append(res["score"])
        print(f"Run {i+1}: Score = {res['score']}")
    
    if len(set(scores)) == 1:
        print("✅ SUCCESS: Scoring is 100% deterministic (No randomness detected).")
    else:
        print("❌ FAILED: Scoring is non-deterministic.")

    # 2. Test Domain Accuracy
    print("\n[Audit 2] Verifying Domain Accuracy...")
    aanchal_res = calculate_deterministic_score(aanchal_resume, aanchal_text)
    akash_res = calculate_deterministic_score(akash_resume, akash_text)

    print(f"Aanchal (Graphic Designer) | Score: {aanchal_res['score']:>5} | Reasoning: {aanchal_res['reasoning']}")
    print(f"Akash (Security Eng)      | Score: {akash_res['score']:>5} | Reasoning: {akash_res['reasoning']}")

    if aanchal_res["score"] < 10 and akash_res["score"] >= 25:
        print("\n✅ SUCCESS: Scoring engine correctly separates domains and rewards technical depth.")
    else:
        print("\n❌ FAILED: Scoring engine lacks proper discrimination.")

if __name__ == "__main__":
    asyncio.run(verify_deterministic())
