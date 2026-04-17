import asyncio
import httpx
import uuid
from datetime import datetime, timedelta, timezone

# Configuration
BASE_URL = "http://localhost:8000"
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "password123"

async def test_interview_flow():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        print("🔐 Logging in as Admin...")
        login_res = await client.post("/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        if login_res.status_code != 200:
            print(f"❌ Login failed: {login_res.text}")
            return
        
        token = login_res.json()["access_token"]
        admin_id = login_res.json()["user_id"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # 1. Create a Candidate
        print("📝 Creating a test candidate...")
        cand_data = {
            "name": "Interview Test Candidate",
            "email": f"test.cand.{uuid.uuid4().hex[:6]}@example.com",
            "interviewer_id": admin_id
        }
        res = await client.post("/candidates", json=cand_data, headers=headers)
        if res.status_code != 201:
            print(f"❌ Candidate creation failed: {res.text}")
            return
        candidate_id = res.json()["id"]

        # 2. Schedule an Interview
        print("📅 Scheduling an interview...")
        scheduled_time = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        interview_data = {
            "candidate_id": candidate_id,
            "interviewer_id": admin_id,
            "scheduled_time": scheduled_time,
            "meeting_link": "https://meet.google.com/abc-defg-hij"
        }
        res = await client.post("/interviews", json=interview_data, headers=headers)
        if res.status_code != 201:
            print(f"❌ Interview scheduling failed: {res.text}")
            return
        print("✅ Interview scheduled successfully.")

        # 3. List Interviews
        print("📋 Listing interviews...")
        res = await client.get("/interviews", headers=headers)
        if res.status_code != 200:
            print(f"❌ Interview listing failed: {res.text}")
        else:
            interviews = res.json()
            print(f"✅ Found {len(interviews)} interviews in the system.")
            for i in interviews:
                print(f"   - {i['candidate_name']} with {i['interviewer_name']} at {i['scheduled_time']}")

if __name__ == "__main__":
    try:
        asyncio.run(test_interview_flow())
    except Exception as e:
        print(f"❌ Error: {e}")
