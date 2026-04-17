import asyncio
import httpx
import uuid

# Configuration
BASE_URL = "http://localhost:8000"
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "password123"

# We will create two interviewers and one admin
INT1_EMAIL = f"interviewer1.{uuid.uuid4().hex[:6]}@example.com"
INT2_EMAIL = f"interviewer2.{uuid.uuid4().hex[:6]}@example.com"
COMMON_PWD = "password123"

async def test_interviewer_silo():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # 1. Admin Login
        print("🔐 Logging in as Admin...")
        login_res = await client.post("/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        if login_res.status_code != 200:
            # Try to create admin if login failed
            from scripts.seed_users import seed_user
            await seed_user(ADMIN_EMAIL, ADMIN_PASSWORD, "admin", "Hiring.AI", "Admin")
            login_res = await client.post("/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        
        admin_token = login_res.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        
        # 2. Create two interviewers
        print("👥 Creating two interviewers...")
        def create_int(email):
            from scripts.seed_users import seed_user
            return seed_user(email, COMMON_PWD, "interviewer", "Hiring.AI", email.split("@")[0])
        
        await create_int(INT1_EMAIL)
        await create_int(INT2_EMAIL)
        
        # Get interviewer IDs
        print("🔍 Fetching interviewer IDs...")
        int1_login = await client.post("/login", json={"email": INT1_EMAIL, "password": COMMON_PWD})
        int1_id = int1_login.json()["user_id"] # Assuming user_id is in response, or fetch via /me
        int1_token = int1_login.json()["access_token"]
        int1_headers = {"Authorization": f"Bearer {int1_token}"}
        
        int2_login = await client.post("/login", json={"email": INT2_EMAIL, "password": COMMON_PWD})
        int2_id = int2_login.json()["user_id"]
        int2_token = int2_login.json()["access_token"]
        int2_headers = {"Authorization": f"Bearer {int2_token}"}
        
        print(f"✅ Int1: {int1_id}, Int2: {int2_id}")

        # 3. Admin creates Candidate A1 assigned to Int1
        print("📝 Admin creating Candidate A1 assigned to Int1...")
        cand_a1_data = {
            "name": "Candidate A1",
            "email": f"a1.{uuid.uuid4().hex[:6]}@example.com",
            "interviewer_id": int1_id
        }
        res = await client.post("/candidates", json=cand_a1_data, headers=admin_headers)
        cand_a1_id = res.json()["id"]
        print(f"✅ Candidate A1 created: {cand_a1_id}")

        # 4. Int1 attempts to view A1 (Success)
        print("👀 Int1 viewing A1...")
        res = await client.get(f"/candidates/{cand_a1_id}", headers=int1_headers)
        if res.status_code == 200:
            print("✅ Int1 successfully viewed assigned candidate.")
        else:
            print(f"❌ Int1 failed to view assigned candidate: {res.status_code}")

        # 5. Int2 attempts to view A1 (Should Fail 403)
        print("🚫 Int2 attempting to view A1...")
        res = await client.get(f"/candidates/{cand_a1_id}", headers=int2_headers)
        if res.status_code == 403:
            print("✅ Int2 was correctly blocked from viewing A1.")
        else:
            print(f"❌ Security Failure: Int2 accessed A1 with status {res.status_code}")

        # 6. Int1 lists candidates (Should see A1)
        print("📋 Int1 listing candidates...")
        res = await client.get("/candidates", headers=int1_headers)
        cands = res.json()
        if any(c["id"] == cand_a1_id for c in cands):
            print("✅ Int1 sees A1 in list.")
        else:
            print("❌ Int1 does NOT see A1 in list.")

        # 7. Int2 lists candidates (Should NOT see A1)
        print("📋 Int2 listing candidates...")
        res = await client.get("/candidates", headers=int2_headers)
        cands = res.json()
        if any(c["id"] == cand_a1_id for c in cands):
            print("❌ Security Failure: Int2 sees A1 in list.")
        else:
            print("✅ Int2 does NOT see A1 in list.")

if __name__ == "__main__":
    try:
        asyncio.run(test_interviewer_silo())
    except Exception as e:
        print(f"❌ Error: {e}")
