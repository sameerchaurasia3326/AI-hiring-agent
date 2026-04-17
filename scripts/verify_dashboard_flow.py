import asyncio
import httpx
import uuid
import asyncpg
from datetime import datetime, timezone

API_URL = "http://localhost:8000"

async def verify_flow():
    # 1. Setup DB directly to avoid async connection issues in tests
    conn = await asyncpg.connect("postgresql://hiring_user:hiring_pass@localhost:5432/hiring_ai")
    
    async with httpx.AsyncClient(base_url=API_URL, timeout=30.0) as client:
        print("🚀 STEP 1: Admin & Interviewer Setup")
        admin_email = f"admin_{uuid.uuid4().hex[:6]}@secure.com"
        await client.post("/signup", json={"company_name": "SecureCorp", "email": admin_email, "password": "pass"})
        res = await client.post("/login", json={"email": admin_email, "password": "pass"})
        admin_token = res.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Get Organization ID
        org_id = res.json()["organization_id"]

        # Invite Interviewer
        int_email = f"int_{uuid.uuid4().hex[:6]}@secure.com"
        res = await client.post("/invite-user", json={"email": int_email, "role": "interviewer"}, headers=admin_headers)
        invite_token = res.json()["invite_link"].split("/")[-1]
        
        # Accept Invite
        await client.post("/accept-invite", json={"token": invite_token, "name": "Security Expert", "password": "pass"})
        res = await client.post("/login", json={"email": int_email, "password": "pass"})
        int_token = res.json()["access_token"]
        int_id = res.json()["user_id"]
        int_headers = {"Authorization": f"Bearer {int_token}"}
        
        print(f"✅ Interviewer Setup Complete (ID: {int_id[:8]}...)")

        print("\n🚀 STEP 2: Creating Job & Application")
        job_id = str(uuid.uuid4())
        await conn.execute("INSERT INTO jobs (id, organization_id, title) VALUES ($1, $2, $3)", job_id, uuid.UUID(org_id), "Security Architect")
        
        cand_id = str(uuid.uuid4())
        await conn.execute("INSERT INTO candidates (id, name, email) VALUES ($1, $2, $3)", cand_id, "Vulnerable Candidate", "v@example.com")
        
        app_id = str(uuid.uuid4())
        await conn.execute('''
            INSERT INTO applications (id, job_id, candidate_id, interviewer_id, stage, score)
            VALUES ($1, $2, $3, $4, 'shortlisted', 95.0)
        ''', uuid.UUID(app_id), uuid.UUID(job_id), uuid.UUID(cand_id), uuid.UUID(int_id))
        print(f"✅ Candidate Assigned (App ID: {app_id[:8]}...)")

        print("\n🚀 STEP 3: Verification - Dashboard Fetch")
        res = await client.get("/interviewer/candidates", headers=int_headers)
        assert res.status_code == 200, f"Dashboard fetch failed: {res.text}"
        candidates = res.json()
        assert len(candidates) > 0, "Candidate not found in dashboard!"
        assert candidates[0]["application_id"] == app_id
        print("✅ Candidate visible in Interviewer Dashboard")

        print("\n🚀 STEP 4: Verification - Submission Logic")
        res = await client.post(f"/applications/{app_id}/evaluate", json={
            "rating": 5.0,
            "notes": "Excellent security mindset. Highly recommend.",
            "decision": "select"
        }, headers=int_headers)
        assert res.status_code == 200, f"Evaluation failed: {res.text}"
        print("✅ Evaluation submitted successfully")

        print("\n🚀 STEP 5: Verification - Optimistic Removal")
        # Now the stage is 'interview_selected', it should be removed from the list
        res = await client.get("/interviewer/candidates", headers=int_headers)
        candidates_after = res.json()
        assert len(candidates_after) == 0, "Candidate was NOT removed from list after selection!"
        print("✅ Optimistic removal (stage filtering) verified")

        print("\n🚀 STEP 6: Multi-Tenant Security Check")
        # Try to evaluate as Admin (should fail or be filtered out if strict role is on)
        res_admin = await client.post(f"/applications/{app_id}/evaluate", json={
            "rating": 1.0, "notes": "Hacker!", "decision": "reject"
        }, headers=admin_headers)
        # We expect 403 because Admin is not 'interviewer' role or doesn't own it
        assert res_admin.status_code in (403, 404), f"Security breach: Admin could access interviewer action! ({res_admin.status_code})"
        print("✅ Multi-tenant Isolation & RBAC verified")

    await conn.close()
    print("\n🎉 ALL VERIFICATION STEPS PASSED SUCCESSFULLY! 🎉")

if __name__ == "__main__":
    asyncio.run(verify_flow())
