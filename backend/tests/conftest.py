"""Shared fixtures + DB seed helpers for KETURUNANKU backend tests."""
import os
import uuid
import secrets
from datetime import datetime, timezone, timedelta

import pytest
import requests
from pymongo import MongoClient

# Base URL for HTTP requests — use public EXPO_PUBLIC_BACKEND_URL when available,
# fallback to localhost:8001 for internal calls
BASE_URL = (
    os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or os.environ.get("EXPO_BACKEND_URL")
    or "http://localhost:8001"
).rstrip("/")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

# Host yang dianggap lokal. Fixture `seeded` menghapus SELURUH koleksi
# (`delete_many({})`), jadi ia hanya boleh menyentuh database sekali pakai.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _mongo_host(uri: str) -> str:
    """Ambil hostname dari URI MongoDB, termasuk bentuk mongodb+srv://."""
    rest = uri.split("://", 1)[-1]
    netloc = rest.split("/", 1)[0]
    netloc = netloc.rsplit("@", 1)[-1]  # buang user:pass@
    if netloc.startswith("["):  # IPv6 literal
        return netloc[1 : netloc.find("]")] if "]" in netloc else netloc[1:]
    return netloc.split(":", 1)[0].lower()


def _is_local_mongo(uri: str) -> bool:
    return _mongo_host(uri) in _LOCAL_HOSTS


def now_utc():
    return datetime.now(timezone.utc)


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture(scope="session")
def mongo_db():
    c = MongoClient(MONGO_URL)
    return c[DB_NAME]


@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    return s


def _seed_user(db, role: str, name_prefix="TEST"):
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    email = f"TEST_{role}_{uuid.uuid4().hex[:6]}@example.com"
    db.users.insert_one({
        "user_id": user_id,
        "email": email,
        "name": f"{name_prefix}_{role}_{user_id[-4:]}",
        "picture": None,
        "role": role,
        "created_at": now_utc(),
    })
    token = secrets.token_hex(16)
    db.user_sessions.insert_one({
        "session_token": token,
        "user_id": user_id,
        "created_at": now_utc(),
        "expires_at": now_utc() + timedelta(days=7),
    })
    return user_id, token, email


def _has_real_data(db):
    """True if the DB contains any non-synthetic user (real Google account)."""
    return db.users.count_documents({"email": {"$not": {"$regex": "^TEST_"}}}) > 0


@pytest.fixture(scope="session")
def seeded(mongo_db):
    """Wipe target collections and seed admin/editor/viewer + root person.

    SAFETY (berlapis):
    1. Kunci host: fixture ini hanya jalan bila MONGO_URL menunjuk ke database
       lokal (localhost/127.0.0.1/::1). Database Atlas/remote ditolak mentah-
       mentah, sehingga salah set env tidak bisa menghapus data produksi.
    2. Kunci data: hanya jalan bila DB murni sintetis (semua user berawalan
       TEST_) atau kosong.
    """
    db = mongo_db
    if not _is_local_mongo(MONGO_URL):
        pytest.skip(
            "Refusing destructive seed: MONGO_URL tidak menunjuk ke database lokal "
            f"(host={_mongo_host(MONGO_URL)!r}). Fixture ini menghapus seluruh koleksi, "
            "jadi hanya diizinkan untuk localhost guna melindungi data produksi."
        )
    if _has_real_data(db):
        pytest.skip(
            "Refusing destructive seed: DB contains non-synthetic users. "
            "This legacy fixture wipes whole collections and must never run against real data."
        )
    coll_names = [
        "users", "people", "relations", "user_sessions", "invites",
        "meta", "person_notes", "family_chat", "app_notifications",
        "chat_typing",
    ]
    for c in coll_names:
        db[c].delete_many({})

    admin_id, admin_token, admin_email = _seed_user(db, "admin")
    editor_id, editor_token, editor_email = _seed_user(db, "editor")
    editor2_id, editor2_token, editor2_email = _seed_user(db, "editor", name_prefix="TEST2")
    viewer_id, viewer_token, viewer_email = _seed_user(db, "viewer")

    # Fetch admin name for room_name assertion
    admin_doc = db.users.find_one({"user_id": admin_id})

    root_person_id = str(uuid.uuid4())
    db.people.insert_one({
        "id": root_person_id,
        "name": "TEST_Root_Person",
        "email": admin_email,  # link to admin user for email-join tests
        "gender": "male",
        "birth_date": None,
        "birth_place": None,
        "death_date": None,
        "photo_url": None,
        "job": None,
        "is_adopted": False,
        "notes": None,
        "is_alive": True,
        "is_root": True,
        "created_by": admin_id,
        "created_at": now_utc(),
        "deleted_at": None,
    })
    # Person linked to editor (alive)
    editor_person_id = str(uuid.uuid4())
    db.people.insert_one({
        "id": editor_person_id,
        "name": "TEST_Editor_Person",
        "email": editor_email,
        "gender": "male",
        "death_date": None,
        "is_adopted": False,
        "is_alive": True,
        "is_root": False,
        "created_by": admin_id,
        "created_at": now_utc(),
        "deleted_at": None,
    })
    # Person linked to editor2 with death_date (dead) — sender_is_alive should be False
    editor2_person_id = str(uuid.uuid4())
    db.people.insert_one({
        "id": editor2_person_id,
        "name": "TEST_Editor2_Person",
        "email": editor2_email,
        "gender": "female",
        "death_date": "2020-01-01",
        "is_adopted": False,
        "is_alive": False,
        "is_root": False,
        "created_by": admin_id,
        "created_at": now_utc(),
        "deleted_at": None,
    })
    db.meta.update_one(
        {"key": "root_person_id"},
        {"$set": {"key": "root_person_id", "value": root_person_id}},
        upsert=True,
    )

    ctx = {
        "admin": {"id": admin_id, "token": admin_token, "email": admin_email, "name": admin_doc["name"]},
        "editor": {"id": editor_id, "token": editor_token, "email": editor_email, "person_id": editor_person_id},
        "editor2": {"id": editor2_id, "token": editor2_token, "email": editor2_email, "person_id": editor2_person_id},
        "viewer": {"id": viewer_id, "token": viewer_token, "email": viewer_email},
        "root_person_id": root_person_id,
    }
    yield ctx

    # Teardown: wipe collections so real Google user becomes admin+root
    for c in coll_names:
        db[c].delete_many({})


def auth(token):
    return {"Authorization": f"Bearer {token}"}
