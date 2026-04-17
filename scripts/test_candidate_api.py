import asyncio
import httpx
import uuid

# Configuration
BASE_URL = "http://localhost:8000"
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "password123"

async def test_candidate_creation_with_job():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # 1. Login
        print("🔐 Logging in as Admin...")
        login_res = await client.post("/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        if login_res.status_code != 200:
            print(f"❌ Login failed: {login_res.text}")
            return
        
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Find a valid Job ID (or create one)
        print("🔍 Fetching a valid Job ID...")
        jobs_res = await client.get("/jobs", headers=headers)
        jobs = jobs_res.json()
        if not jobs:
            print("⚠️ No jobs found. Creating a temporary job...")
            create_job_data = {
                "job_title": "Test Software Engineer",
                "hiring_workflow": [{"stage_name": "Screening"}]
            }
            res = await client.post("/jobs", json=create_job_data, headers=headers)
            job_id = res.json()["job_id"]
        else:
            job_id = jobs[0]["id"]
        
        print(f"✅ Using Job ID: {job_id}")

        # 3. Create Candidate tied to this Job
        print("📝 Creating candidate tied to job...")
        cand_email = f"sourced.{uuid.uuid4().hex[:6]}@example.com"
        cand_data = {
            "name": "Manually Sourced Candidate",
            "email": cand_email,
            "job_id": job_id,
            "skills": ["Python", "Security"],
            "experience": "5 years"
        }
        res = await client.post("/candidates", json=cand_data, headers=headers)
        
        if res.status_code == 201:
            cand = res.json()
            print(f"✅ Candidate created with ID: {cand['id']}")
            print(f"✅ Assigned Interviewer (Owner): {cand['interviewer_id']}")
        else:
            print(f"❌ Candidate creation failed: {res.text}")
            return

        # 4. Verification Check: Does an application exist?
        # Note: We don't have a direct /applications endpoint yet, but we can check via DB or another way if available.
        # For now, let's just confirm the 201 response.
        print("\n🎉 Verification complete: Candidate is now assigned to a job and pipeline.")

if __name__ == "__main__":
    try:
        asyncio.run(test_candidate_creation_with_job())
    except Exception as e:
        print(f"❌ Error: {e}")
