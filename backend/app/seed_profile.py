import json
import os
from app.database import SessionLocal
from app.models import User
from app.redis_client import redis_client

def seed():
    db = SessionLocal()
    try:
        username = "Atulmishra22"
        email = "atulmishralearn@gmail.com"
        
        # 1. Read README content
        readme_path = "/app/profile_readme.md"
        readme_content = ""
        if os.path.exists(readme_path):
            with open(readme_path, "r", encoding="utf-8") as f:
                readme_content = f.read()
        else:
            readme_content = "# Atul Mishra\nAI Software Engineer & Data Science Student at IIT Madras"

        # 2. Upsert User
        user = db.query(User).filter(User.github_username == username).first()
        if not user:
            user = User(
                email=email,
                github_username=username,
                auth_provider="github",
                is_active=True
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"Created new user {username} in database.")
        else:
            print(f"User {username} already exists in database.")
        
        # 3. Cache profile details in Redis
        profile_data = {
            "username": username,
            "name": "Atul Mishra",
            "email": email,
            "bio": "AI Software Engineer & Data Science Student at IIT Madras",
            "avatar_url": "https://avatars.githubusercontent.com/u/47101899?v=4",
            "github_id": 47101899,
            "readme": readme_content
        }
        redis_client.set(f"github_profile:{username}", json.dumps(profile_data))
        print("Successfully seeded profile for Atulmishra22 in DB and Redis!")
    except Exception as e:
        print(f"Error seeding profile: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed()
