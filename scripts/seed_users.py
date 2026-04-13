import asyncio
import argparse
from sqlalchemy import select
from src.db.database import AsyncSessionLocal
from src.db.models import User, Organization, UserRole
from src.utils.security import hash_password

async def seed_user(email: str, password: str, role: str, company: str, name: str):
    async with AsyncSessionLocal() as session:
        # Check if user exists
        res = await session.execute(select(User).where(User.email == email))
        user = res.scalars().first()
        if user:
            print(f"[{email}] User already exists. Updating role to {role}...")
            user.role = role
            # Also update org? Just leave org alone for now
            await session.commit()
            return
            
        print(f"[{email}] Creating new user...")
        
        # Check for company
        res = await session.execute(select(Organization).where(Organization.name == company))
        org = res.scalars().first()
        
        if not org:
            print(f"[{company}] Organization not found. Creating it...")
            org = Organization(name=company)
            session.add(org)
            await session.flush()
        
        # Create user
        new_user = User(
            email=email,
            password=hash_password(password),
            name=name,
            organization_id=org.id,
            role=role,
            is_email_verified=True
        )
        session.add(new_user)
        await session.commit()
        print(f"✅ User '{email}' created successfully with role '{role}' under organization '{company}'.")

def main():
    parser = argparse.ArgumentParser(description="Seed initial admin or interviewer accounts manually.")
    parser.add_argument("--email", required=True, help="User email")
    parser.add_argument("--password", required=True, help="User password")
    parser.add_argument("--role", choices=["admin", "interviewer", "candidate"], default="admin", help="User role (default: admin)")
    parser.add_argument("--company", default="Hiring.AI", help="Organization name (default: Hiring.AI)")
    parser.add_argument("--name", default="Admin", help="User's full name")
    
    args = parser.parse_args()
    
    asyncio.run(seed_user(args.email, args.password, args.role, args.company, args.name))

if __name__ == "__main__":
    main()
