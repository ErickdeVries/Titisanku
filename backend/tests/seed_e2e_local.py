"""Seed situs E2E Titisanku khusus untuk pengujian LOKAL.

Aman: hanya mau jalan bila MONGO_URL menunjuk ke MongoDB lokal (localhost /
127.0.0.1 / ::1). Database Atlas / remote akan DITOLAK seluruhnya agar data
produksi tidak pernah tersentuh.

Pemakaian:
    python backend/tests/seed_e2e_local.py            # buat data, cetak JSON
    python backend/tests/seed_e2e_local.py --cleanup   # hapus data uji

Data yang dibuat (semua berprefix TESTE2E_ agar mudah dikenali / dibersihkan):
    - 1 user admin pemilik pohon
    - 1 sesi login (session_token) -> disuntik ke localStorage frontend
    - 1 pohon + root person + spouse + 1 relasi
    - 1 anggota kedua (untuk uji privasi kartu / non-owner)
"""
import json
import os
import secrets
import sys
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from pymongo import MongoClient
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT, ".env"))

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "titisanku_e2e")
STAMP_FILE = os.path.join(ROOT, "tests", ".e2e_local_seed.json")

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _host(uri: str) -> str:
    if uri.startswith("mongodb+srv://") or uri.startswith("mongodb://"):
        netloc = urlparse(uri.replace("mongodb+srv://", "mongodb://", 1)).netloc
        netloc = netloc.split("@")[-1]
        return netloc.split(":")[0]
    return ""


def _assert_local():
    host = _host(MONGO_URL)
    if host not in _LOCAL_HOSTS:
        sys.exit(
            "REFUSED: MONGO_URL tidak menunjuk ke MongoDB lokal "
            f"(host={host!r}). Seed E2E hanya untuk database lokal agar data "
            "produksi (Atlas) aman. Set MONGO_URL=mongodb://localhost:27017."
        )
    if DB_NAME == "titisanku_atlas":
        sys.exit("REFUSED: DB_NAME menunjuk ke database produksi (titisanku_atlas).")


def now_utc():
    return datetime.now(timezone.utc)


def seed():
    _assert_local()
    c = MongoClient(MONGO_URL)
    db = c[DB_NAME]

    suff = uuid.uuid4().hex[:8]
    uid = f"user_TESTE2E_{suff}"
    member_uid = f"user_TESTE2E_M{suff}"
    token = secrets.token_hex(16)
    email = f"TESTE2E_{suff}@example.com"
    member_email = f"TESTE2E_M{suff}@example.com"

    db.users.insert_one({
        "user_id": uid, "email": email, "name": "TESTE2E_Admin",
        "picture": None, "role": "admin", "created_at": now_utc(),
    })
    db.users.insert_one({
        "user_id": member_uid, "email": member_email, "name": "TESTE2E_Viewer",
        "picture": None, "role": "member", "created_at": now_utc(),
    })
    db.user_sessions.insert_one({
        "session_token": token, "user_id": uid,
        "created_at": now_utc(), "expires_at": now_utc() + timedelta(days=7),
    })

    member_token = secrets.token_hex(16)
    db.user_sessions.insert_one({
        "session_token": member_token, "user_id": member_uid,
        "created_at": now_utc(), "expires_at": now_utc() + timedelta(days=7),
    })

    tid = f"tree_TESTE2E_{suff}"
    root_id = str(uuid.uuid4())
    spouse_id = str(uuid.uuid4())
    child_id = str(uuid.uuid4())
    db.people.insert_many([
        {"id": root_id, "tree_id": tid, "name": "TESTE2E_Root", "gender": "male",
         "is_alive": True, "is_root": True, "is_adopted": False,
         "created_by": uid, "created_at": now_utc(), "deleted_at": None},
        {"id": spouse_id, "tree_id": tid, "name": "TESTE2E_Spouse", "gender": "female",
         "is_alive": True, "is_root": False, "is_adopted": False,
         "created_by": uid, "created_at": now_utc(), "deleted_at": None},
        {"id": child_id, "tree_id": tid, "name": "TESTE2E_Child", "gender": "male",
         "is_alive": True, "is_root": False, "is_adopted": False,
         "created_by": uid, "created_at": now_utc(), "deleted_at": None},
    ])
    db.relations.insert_many([
        {"id": str(uuid.uuid4()), "tree_id": tid, "person_id": root_id,
         "related_person_id": spouse_id, "relation_type": "spouse",
         "marriage_date": "2010-01-15", "divorce_date": None,
         "created_at": now_utc(), "deleted_at": None},
        {"id": str(uuid.uuid4()), "tree_id": tid, "person_id": root_id,
         "related_person_id": child_id, "relation_type": "child",
         "marriage_date": None, "divorce_date": None,
         "created_at": now_utc(), "deleted_at": None},
    ])
    db.trees.insert_one({
        "id": tid, "name": "TESTE2E_Tree", "owner_id": uid,
        "plan": "free", "root_person_id": root_id, "created_at": now_utc(),
    })
    db.tree_members.insert_one({
        "id": str(uuid.uuid4()), "tree_id": tid, "user_id": uid,
        "role": "admin", "joined_at": now_utc(),
    })
    db.tree_members.insert_one({
        "id": str(uuid.uuid4()), "tree_id": tid, "user_id": member_uid,
        "role": "member", "joined_at": now_utc(),
    })

    stamp = {
        "user_id": uid, "member_uid": member_uid, "token": token,
        "member_token": member_token,
        "tree_id": tid, "root_id": root_id, "spouse_id": spouse_id,
        "child_id": child_id, "email": email,
    }
    with open(STAMP_FILE, "w", encoding="utf-8") as f:
        json.dump(stamp, f)
    print(json.dumps(stamp))


def cleanup():
    _assert_local()
    try:
        with open(STAMP_FILE, encoding="utf-8") as f:
            s = json.load(f)
    except FileNotFoundError:
        print("no seed file")
        return
    c = MongoClient(MONGO_URL)
    db = c[DB_NAME]
    tid = s["tree_id"]
    db.trees.delete_many({"id": tid})
    db.tree_members.delete_many({"tree_id": tid})
    db.people.delete_many({"tree_id": tid})
    db.relations.delete_many({"tree_id": tid})
    db.user_sessions.delete_many({"session_token": s["token"]})
    db.users.delete_many({"user_id": {"$in": [s["user_id"], s["member_uid"]]}})
    try:
        os.remove(STAMP_FILE)
    except OSError:
        pass
    print("cleaned")


if __name__ == "__main__":
    if "--cleanup" in sys.argv:
        cleanup()
    else:
        seed()
