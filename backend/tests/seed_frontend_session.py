"""Seed a synthetic session + tree + root person + a spouse relation
in Mongo for frontend playwright test. Prints the session token and person id.

Run before playwright:  python /app/backend/tests/seed_frontend_session.py

Cleanup after playwright:  python /app/backend/tests/seed_frontend_session.py --cleanup
"""
import os
import sys
import json
import uuid
import secrets
from datetime import datetime, timezone, timedelta

from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

STAMP_FILE = "/tmp/keturunanku_seed.json"


def now_utc():
    return datetime.now(timezone.utc)


def seed():
    uid = f"user_TESTFE{uuid.uuid4().hex[:6]}"
    token = secrets.token_hex(16)
    email = f"TESTFE_{uuid.uuid4().hex[:6]}@example.com"
    db.users.insert_one({
        "user_id": uid, "email": email, "name": "TESTFE_Admin",
        "picture": None, "role": "admin", "created_at": now_utc(),
    })
    db.user_sessions.insert_one({
        "session_token": token, "user_id": uid,
        "created_at": now_utc(), "expires_at": now_utc() + timedelta(days=7),
    })
    tid = f"tree_TESTFE{uuid.uuid4().hex[:8]}"
    root_id = str(uuid.uuid4())
    spouse_id = str(uuid.uuid4())
    db.people.insert_many([
        {"id": root_id, "tree_id": tid, "name": "TESTFE_Root", "gender": "male",
         "is_alive": True, "is_root": True, "is_adopted": False,
         "created_by": uid, "created_at": now_utc(), "deleted_at": None},
        {"id": spouse_id, "tree_id": tid, "name": "TESTFE_Spouse", "gender": "female",
         "is_alive": True, "is_root": False, "is_adopted": False,
         "created_by": uid, "created_at": now_utc(), "deleted_at": None},
    ])
    rel_id = str(uuid.uuid4())
    db.relations.insert_one({
        "id": rel_id, "tree_id": tid, "person_id": root_id,
        "related_person_id": spouse_id, "relation_type": "spouse",
        "marriage_date": "2010-01-15", "divorce_date": None,
        "created_at": now_utc(), "deleted_at": None,
    })
    db.trees.insert_one({
        "id": tid, "name": "TESTFE_Tree", "owner_id": uid,
        "plan": "free", "root_person_id": root_id, "created_at": now_utc(),
    })
    db.tree_members.insert_one({
        "id": str(uuid.uuid4()), "tree_id": tid, "user_id": uid,
        "role": "admin", "joined_at": now_utc(),
    })
    stamp = {"user_id": uid, "token": token, "tree_id": tid,
             "root_id": root_id, "spouse_id": spouse_id, "rel_id": rel_id}
    with open(STAMP_FILE, "w") as f:
        json.dump(stamp, f)
    print(json.dumps(stamp))


def cleanup():
    try:
        with open(STAMP_FILE) as f:
            s = json.load(f)
    except FileNotFoundError:
        return
    db.trees.delete_many({"id": s["tree_id"]})
    db.tree_members.delete_many({"tree_id": s["tree_id"]})
    db.people.delete_many({"tree_id": s["tree_id"]})
    db.relations.delete_many({"tree_id": s["tree_id"]})
    db.user_sessions.delete_many({"session_token": s["token"]})
    db.users.delete_many({"user_id": s["user_id"]})
    os.remove(STAMP_FILE)
    print("cleaned")


if __name__ == "__main__":
    if "--cleanup" in sys.argv:
        cleanup()
    else:
        seed()
