import asyncio
import httpx
import time
import json
import uuid

API_URL = "http://localhost:8000"

async def test_full_rbac_flow():
    async with httpx.AsyncClient(base_url=API_URL, timeout=30.0) as client:
        print("=== STEP 1: Admin Signs Up ===")
        admin_email = f"admin_{uuid.uuid4().hex[:6]}@companya.com"
        res = await client.post("/signup", json={
            "company_name": "Company A",
            "email": admin_email,
            "password": "password123"
        })
        assert res.status_code == 200, res.text
        print("✅ Admin created")

        res = await client.post("/login", json={"email": admin_email, "password": "password123"})
        admin_token = res.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        print("✅ Admin logged in")

        print("\n=== STEP 2: Admin Invites Interviewer ===")
        interviewer_email = f"interviewer_{uuid.uuid4().hex[:6]}@companya.com"
        res = await client.post("/invite-user", json={
            "email": interviewer_email,
            "role": "interviewer"
        }, headers=admin_headers)
        assert res.status_code == 200, res.text
        invite_link = res.json().get("invite_link")
        invite_token = invite_link.split("/")[-1]
        print(f"✅ Invite sent (token: {invite_token[:8]}...)")

        print("\n=== STEP 3: Interviewer Accepts Invite ===")
        res = await client.post("/accept-invite", json={
            "token": invite_token,
            "name": "Jane Interviewer",
            "password": "interviewerpass"
        })
        assert res.status_code == 200, res.text
        print("✅ Interviewer account created")

        res = await client.post("/login", json={
            "email": interviewer_email, 
            "password": "interviewerpass"
        })
        interviewer_token = res.json()["access_token"]
        interviewer_headers = {"Authorization": f"Bearer {interviewer_token}"}
        print("✅ Interviewer logged in")

        print("\n=== STEP 3a: Get Interviewer ID from /team endpoint ===")
        res = await client.get("/team", headers=admin_headers)
        team = res.json()["team"]
        interviewer_user = next(u for u in team if u["email"] == interviewer_email)
        interviewer_id = interviewer_user["id"]
        print(f"✅ Found Interviewer ID: {interviewer_id}")

        print("\n=== STEP 4: Admin Creates Job & Assigns Interviewer ===")
        job_payload = {
            "job_title": "Python Developer",
            "department": "Engineering",
            "hiring_manager_name": "Admin Manager",
            "hiring_manager_email": admin_email,
            "location": "Remote",
            "experience_required": "3-5 years",
            "employment_type": "Full-time",
            "joining_requirement": "Immediate",
            "required_skills": ["Python", "FastAPI"],
            "preferred_skills": ["Docker"],
            "screening_questions": [],
            "technical_test_type": None,
            "technical_test_mcq": [],
            "hiring_workflow": [
                {"stage_name": "resume_screening", "assigned_user_id": None},
                {"stage_name": "technical_interview", "assigned_user_id": interviewer_id}
            ],
            "scoring_weights": {"semantic_similarity": 25, "llm_evaluation": 75, "screening_score": 0, "test_score": 0}
        }
        res = await client.post("/jobs", json=job_payload, headers=admin_headers)
        assert res.status_code == 200, res.text
        job_id = res.json()["job_id"]
        print(f"✅ Job created: {job_id}")

        print("\n=== STEP 5: Add Candidate to Job ===")
        # Wait for the system to settle
        await asyncio.sleep(2)
        # We simulate candidate application by pushing directly or via an endpoint if one exists
        # In this system, resumes are parsed via langgraph, or uploaded via `upload_resumes`
        # Let's bypass full LLM wait by cheating the DB for My Tasks logic since we just want to test isolation
        # But we can try to test isolation of My Tasks directly.
        import asyncpg
        conn = await asyncpg.connect("postgresql://hiring_user:hiring_pass@localhost:5432/hiring_ai")
        
        cand_id = str(uuid.uuid4())
        await conn.execute("INSERT INTO candidates (id, name, email) VALUES ($1, $2, $3)", cand_id, "Test Candidate", f"cand_{uuid.uuid4().hex[:6]}@test.com")
        
        app_id = str(uuid.uuid4())
        # assign technical_interview user directly to the application
        await conn.execute('''
            INSERT INTO applications (id, job_id, candidate_id, assigned_user_id, hr_selected)
            VALUES ($1, $2, $3, $4, false)
        ''', app_id, job_id, cand_id, interviewer_id)
        print("✅ Candidate fully assigned in DB")
        await conn.close()

        print("\n=== STEP 6: Interviewer sees candidate in 'My Tasks' ===")
        res = await client.get("/my-tasks", headers=interviewer_headers)
        assert res.status_code == 200, res.text
        tasks = res.json()["tasks"]
        assert len(tasks) > 0, "Interviewer has no tasks!"
        print(f"✅ Interviewer sees {len(tasks)} assigned task(s)")

        print("Testing Data Isolation...")
        # Admin shouldn't see tasks because they aren't assigned to Admin
        res_admin = await client.get("/my-tasks", headers=admin_headers)
        assert len(res_admin.json()["tasks"]) == 0
        print("✅ Admin 'My Tasks' correctly shows 0 tasks (strict isolation)")
        
        print("\n🎉 ALL TESTS PASSED SUCCESSFULLY! 🎉")

if __name__ == "__main__":
    asyncio.run(test_full_rbac_flow())
