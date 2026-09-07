"""Seed synthetic user + tree + 2 people to test the stat-birthday card.
Data-safety: only inserts docs with TEST_ prefixed IDs, cleans up ONLY those exact
docs on --cleanup. Never touches real user data.
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, date

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

# Deterministic IDs for this test run so cleanup is safe.
USER_ID = "TEST_bdstat_user"
SESSION_TOKEN = "TEST_bdstat_session_token_xyz"
TREE_ID = "TEST_bdstat_tree"
ROOT_PERSON_ID = "TEST_bdstat_person_root"
BD_PERSON_ID = "TEST_bdstat_person_mahdiana"


async def seed():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    now = datetime.utcnow()

    # Cleanup any leftovers with our exact ids first (idempotent).
    await cleanup(db, silent=True)

    # 1) user
    await db.users.insert_one({
        "user_id": USER_ID,
        "email": "TEST_bdstat@example.com",
        "name": "TEST BDStat",
        "picture": None,
        "role": "admin",
        "created_at": now,
    })
    # 2) user_sessions
    await db.user_sessions.insert_one({
        "session_token": SESSION_TOKEN,
        "user_id": USER_ID,
        "created_at": now,
        "expires_at": now + timedelta(days=7),
    })
    # 3) tree
    await db.trees.insert_one({
        "id": TREE_ID,
        "name": "TEST BDStat Tree",
        "owner_id": USER_ID,
        "plan": "free",
        "root_person_id": ROOT_PERSON_ID,
        "created_at": now,
    })
    # 4) tree_members
    await db.tree_members.insert_one({
        "tree_id": TREE_ID,
        "user_id": USER_ID,
        "role": "admin",
        "joined_at": now,
    })
    # 5) two people: root (no birthday), Mahdiana with upcoming ~56 days.
    today = date.today()
    target = today + timedelta(days=56)
    birth_date = f"1970-{target.month:02d}-{target.day:02d}"
    await db.people.insert_many([
        {
            "id": ROOT_PERSON_ID,
            "tree_id": TREE_ID,
            "name": "TEST Root",
            "gender": "male",
            "birth_date": None,
            "death_date": None,
            "deleted_at": None,
            "is_alive": True,
            "created_at": now,
        },
        {
            "id": BD_PERSON_ID,
            "tree_id": TREE_ID,
            "name": "Mahdiana",
            "gender": "female",
            "birth_date": birth_date,
            "death_date": None,
            "deleted_at": None,
            "is_alive": True,
            "created_at": now,
        },
    ])
    print(f"SEEDED: session_token={SESSION_TOKEN} birth_date={birth_date}")


async def cleanup(db=None, silent=False):
    close_after = False
    if db is None:
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        close_after = True
    r1 = await db.users.delete_one({"user_id": USER_ID})
    r2 = await db.user_sessions.delete_one({"session_token": SESSION_TOKEN})
    r3 = await db.trees.delete_one({"id": TREE_ID})
    r4 = await db.tree_members.delete_one({"tree_id": TREE_ID, "user_id": USER_ID})
    r5 = await db.people.delete_many({"id": {"$in": [ROOT_PERSON_ID, BD_PERSON_ID]}})
    if not silent:
        print(
            f"CLEANED: users={r1.deleted_count} sessions={r2.deleted_count} "
            f"trees={r3.deleted_count} tree_members={r4.deleted_count} people={r5.deleted_count}"
        )
    if close_after:
        pass


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "cleanup":
        asyncio.run(cleanup())
    else:
        asyncio.run(seed())
