"""KETURUNANKU multi-tenant backend tests (post-refactor).

Covers ONLY the new Tree SaaS endpoints and semantics:
- POST/GET /api/trees
- GET /api/tree?tree_id=  (incl. NON-member -> 403)
- POST /api/people/add-relative?tree_id=  + Free-plan 50-person limit -> 402
- POST /api/trees/{id}/upgrade  (admin-only, unlocks limit)
- GET /api/trees/{id}/members, PUT /members/role, DELETE /members/{id}
- Chat + person_notes are tree-scoped (room_id == tree_id)
- Backup/Restore are tree-scoped (no leakage across trees)
- RBAC: viewer 403 on add-relative/upgrade, 200 on GET /tree

Cleanup: ONLY docs created by this run are removed. Never delete_many({}).
"""
import os
import uuid
import secrets
from datetime import datetime, timezone, timedelta

import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

BASE_URL = (
    os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or os.environ.get("EXPO_BACKEND_URL")
    or "http://localhost:8001"
).rstrip("/")
API = f"{BASE_URL}/api"

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


def now_utc():
    return datetime.now(timezone.utc)


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- Cleanup registry (per session) ----------
CREATED = {
    "user_ids": set(),
    "session_tokens": set(),
    "tree_ids": set(),
}


@pytest.fixture(scope="session")
def mongo_db():
    c = MongoClient(MONGO_URL)
    return c[DB_NAME]


def _seed_user(db, role_hint="viewer", name="TEST_MT_User"):
    uid = f"user_{uuid.uuid4().hex[:12]}"
    email = f"TEST_MT_{uuid.uuid4().hex[:8]}@example.com"
    token = secrets.token_hex(16)
    db.users.insert_one({
        "user_id": uid,
        "email": email,
        "name": f"{name}_{uid[-4:]}",
        "picture": None,
        "role": role_hint,  # global role — not used by tree endpoints
        "created_at": now_utc(),
    })
    db.user_sessions.insert_one({
        "session_token": token,
        "user_id": uid,
        "created_at": now_utc(),
        "expires_at": now_utc() + timedelta(days=7),
    })
    CREATED["user_ids"].add(uid)
    CREATED["session_tokens"].add(token)
    return uid, token, email


@pytest.fixture(scope="session")
def users(mongo_db):
    """Two synthetic users, both without any tree membership at start."""
    u1_id, u1_tok, u1_email = _seed_user(mongo_db, name="TEST_MT_A")
    u2_id, u2_tok, u2_email = _seed_user(mongo_db, name="TEST_MT_B")
    u3_id, u3_tok, u3_email = _seed_user(mongo_db, name="TEST_MT_Viewer")
    yield {
        "A": {"id": u1_id, "token": u1_tok, "email": u1_email},
        "B": {"id": u2_id, "token": u2_tok, "email": u2_email},
        "V": {"id": u3_id, "token": u3_tok, "email": u3_email},
    }
    # -------- Teardown: delete ONLY docs we created --------
    tree_ids = list(CREATED["tree_ids"])
    user_ids = list(CREATED["user_ids"])
    tokens = list(CREATED["session_tokens"])

    if tree_ids:
        mongo_db.trees.delete_many({"id": {"$in": tree_ids}})
        mongo_db.tree_members.delete_many({"tree_id": {"$in": tree_ids}})
        mongo_db.people.delete_many({"tree_id": {"$in": tree_ids}})
        mongo_db.relations.delete_many({"tree_id": {"$in": tree_ids}})
        mongo_db.family_chat.delete_many({"tree_id": {"$in": tree_ids}})
        mongo_db.family_chat.delete_many({"room_id": {"$in": tree_ids}})
        mongo_db.chat_typing.delete_many({"room_id": {"$in": tree_ids}})
        mongo_db.person_notes.delete_many({"tree_id": {"$in": tree_ids}})
        mongo_db.app_notifications.delete_many({"tree_id": {"$in": tree_ids}})
    # Also remove any auto-created trees whose owner is one of our test users
    auto_trees = list(mongo_db.trees.find({"owner_id": {"$in": user_ids}}, {"id": 1}))
    auto_tids = [t["id"] for t in auto_trees]
    if auto_tids:
        mongo_db.trees.delete_many({"id": {"$in": auto_tids}})
        mongo_db.tree_members.delete_many({"tree_id": {"$in": auto_tids}})
        mongo_db.people.delete_many({"tree_id": {"$in": auto_tids}})
        mongo_db.relations.delete_many({"tree_id": {"$in": auto_tids}})
    mongo_db.tree_members.delete_many({"user_id": {"$in": user_ids}})
    mongo_db.user_sessions.delete_many({"session_token": {"$in": tokens}})
    mongo_db.users.delete_many({"user_id": {"$in": user_ids}})


# Shared state between tests (populated in order)
STATE = {}


# ---------------------------------------------------------------------------
# 1. POST /api/trees + GET /api/trees
# ---------------------------------------------------------------------------
class TestTreeCreation:
    def test_create_tree_returns_admin_role_and_root(self, users):
        r = requests.post(f"{API}/trees", json={"name": "TEST_MT_TreeA"},
                          headers=auth(users["A"]["token"]))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["role"] == "admin"
        assert data["person_count"] == 1
        assert data["limit"] == 50
        assert data["plan"] == "free"
        assert data["owner_id"] == users["A"]["id"]
        assert data["name"] == "TEST_MT_TreeA"
        assert data["id"].startswith("tree_")
        STATE["tree_a"] = data["id"]
        CREATED["tree_ids"].add(data["id"])

    def test_list_trees_includes_created(self, users):
        r = requests.get(f"{API}/trees", headers=auth(users["A"]["token"]))
        assert r.status_code == 200, r.text
        lst = r.json()
        found = [t for t in lst if t["id"] == STATE["tree_a"]]
        assert found, f"Tree {STATE['tree_a']} not in list: {[t['id'] for t in lst]}"
        t = found[0]
        assert t["role"] == "admin"
        assert t["person_count"] == 1
        assert t["member_count"] == 1
        assert t["limit"] == 50

    def test_second_user_creates_separate_tree(self, users):
        r = requests.post(f"{API}/trees", json={"name": "TEST_MT_TreeB"},
                          headers=auth(users["B"]["token"]))
        assert r.status_code == 200, r.text
        STATE["tree_b"] = r.json()["id"]
        CREATED["tree_ids"].add(STATE["tree_b"])
        assert STATE["tree_b"] != STATE["tree_a"]


# ---------------------------------------------------------------------------
# 2. GET /api/tree — tenant isolation
# ---------------------------------------------------------------------------
class TestGetTree:
    def test_owner_can_read_own_tree(self, users):
        r = requests.get(f"{API}/tree", params={"tree_id": STATE["tree_a"]},
                         headers=auth(users["A"]["token"]))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["tree"]["id"] == STATE["tree_a"]
        assert d["role"] == "admin"
        assert d["person_count"] == 1
        assert d["limit"] == 50
        assert d["root_id"]
        STATE["root_a"] = d["root_id"]

    def test_non_member_gets_403_on_other_tree(self, users):
        r = requests.get(f"{API}/tree", params={"tree_id": STATE["tree_a"]},
                         headers=auth(users["B"]["token"]))
        assert r.status_code == 403, r.text

    def test_default_tree_when_no_tree_id(self, users):
        # No tree_id -> primary (first) tree
        r = requests.get(f"{API}/tree", headers=auth(users["A"]["token"]))
        assert r.status_code == 200
        assert r.json()["tree"]["id"] == STATE["tree_a"]


# ---------------------------------------------------------------------------
# 3. add-relative + 402 limit + upgrade
# ---------------------------------------------------------------------------
class TestAddRelativeAndLimit:
    def test_add_relative_success(self, users):
        r = requests.post(
            f"{API}/people/add-relative",
            params={"tree_id": STATE["tree_a"]},
            json={"focus_id": STATE["root_a"], "direction": "child",
                  "person": {"name": "TEST_MT_Child1"}},
            headers=auth(users["A"]["token"]),
        )
        assert r.status_code == 200, r.text
        assert r.json()["person"]["name"] == "TEST_MT_Child1"

    def test_non_member_add_relative_forbidden(self, users):
        r = requests.post(
            f"{API}/people/add-relative",
            params={"tree_id": STATE["tree_a"]},
            json={"focus_id": STATE["root_a"], "direction": "child",
                  "person": {"name": "TEST_MT_Intruder"}},
            headers=auth(users["B"]["token"]),
        )
        assert r.status_code == 403, r.text

    def test_free_plan_402_at_50(self, users, mongo_db):
        # Bulk-insert to bring total people to 50 (already 2)
        docs = []
        for i in range(48):
            docs.append({
                "id": str(uuid.uuid4()),
                "tree_id": STATE["tree_a"],
                "name": f"TEST_MT_Filler_{i}",
                "is_alive": True, "is_root": False,
                "deleted_at": None, "created_at": now_utc(),
            })
        mongo_db.people.insert_many(docs)
        assert mongo_db.people.count_documents(
            {"tree_id": STATE["tree_a"], "deleted_at": None}) == 50

        r = requests.post(
            f"{API}/people/add-relative",
            params={"tree_id": STATE["tree_a"]},
            json={"focus_id": STATE["root_a"], "direction": "child",
                  "person": {"name": "TEST_MT_OverLimit"}},
            headers=auth(users["A"]["token"]),
        )
        assert r.status_code == 402, r.text
        assert r.json()["detail"].startswith("LIMIT_REACHED:")

    def test_upgrade_admin_only_and_unlocks(self, users):
        # Non-member cannot upgrade
        r_bad = requests.post(f"{API}/trees/{STATE['tree_a']}/upgrade",
                              headers=auth(users["B"]["token"]))
        assert r_bad.status_code == 403, r_bad.text

        # Admin can upgrade
        r = requests.post(f"{API}/trees/{STATE['tree_a']}/upgrade",
                          headers=auth(users["A"]["token"]))
        assert r.status_code == 200, r.text
        assert r.json()["plan"] == "pro"

        # After upgrade: add beyond 50 succeeds
        r2 = requests.post(
            f"{API}/people/add-relative",
            params={"tree_id": STATE["tree_a"]},
            json={"focus_id": STATE["root_a"], "direction": "child",
                  "person": {"name": "TEST_MT_AfterPro"}},
            headers=auth(users["A"]["token"]),
        )
        assert r2.status_code == 200, r2.text

        # /tree should now report limit=None (pro)
        t = requests.get(f"{API}/tree", params={"tree_id": STATE["tree_a"]},
                         headers=auth(users["A"]["token"])).json()
        assert t["limit"] is None
        assert t["tree"]["plan"] == "pro"


# ---------------------------------------------------------------------------
# 4. Members endpoints  (role change + removal + owner protection)
# ---------------------------------------------------------------------------
class TestMembers:
    def test_add_viewer_member_directly(self, users, mongo_db):
        """Insert a tree_members doc with role=viewer for user V into tree A
        (simulates an accepted invite as viewer)."""
        mongo_db.tree_members.insert_one({
            "id": str(uuid.uuid4()),
            "tree_id": STATE["tree_a"],
            "user_id": users["V"]["id"],
            "role": "viewer",
            "joined_at": now_utc(),
        })

    def test_list_members(self, users):
        r = requests.get(f"{API}/trees/{STATE['tree_a']}/members",
                         headers=auth(users["A"]["token"]))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["role"] == "admin"
        assert data["owner_id"] == users["A"]["id"]
        members = data["members"]
        assert len(members) == 2
        by_id = {m["user_id"]: m for m in members}
        assert by_id[users["A"]["id"]]["is_owner"] is True
        assert by_id[users["A"]["id"]]["role"] == "admin"
        assert by_id[users["V"]["id"]]["is_owner"] is False
        assert by_id[users["V"]["id"]]["role"] == "viewer"
        assert by_id[users["V"]["id"]]["email"] == users["V"]["email"]

    def test_viewer_get_tree_ok_but_write_forbidden(self, users):
        # RBAC: viewer 200 on GET /tree
        r = requests.get(f"{API}/tree", params={"tree_id": STATE["tree_a"]},
                         headers=auth(users["V"]["token"]))
        assert r.status_code == 200
        assert r.json()["role"] == "viewer"

        # viewer 403 on add-relative
        r2 = requests.post(
            f"{API}/people/add-relative",
            params={"tree_id": STATE["tree_a"]},
            json={"focus_id": STATE["root_a"], "direction": "child",
                  "person": {"name": "TEST_MT_ViewerAttempt"}},
            headers=auth(users["V"]["token"]),
        )
        assert r2.status_code == 403

        # viewer 403 on upgrade
        r3 = requests.post(f"{API}/trees/{STATE['tree_a']}/upgrade",
                           headers=auth(users["V"]["token"]))
        assert r3.status_code == 403

    def test_admin_can_change_viewer_to_editor(self, users):
        r = requests.put(
            f"{API}/trees/{STATE['tree_a']}/members/role",
            json={"user_id": users["V"]["id"], "role": "editor"},
            headers=auth(users["A"]["token"]),
        )
        assert r.status_code == 200, r.text
        # verify
        m = requests.get(f"{API}/trees/{STATE['tree_a']}/members",
                         headers=auth(users["A"]["token"])).json()
        by_id = {mm["user_id"]: mm for mm in m["members"]}
        assert by_id[users["V"]["id"]]["role"] == "editor"

    def test_cannot_change_owner_role(self, users):
        r = requests.put(
            f"{API}/trees/{STATE['tree_a']}/members/role",
            json={"user_id": users["A"]["id"], "role": "viewer"},
            headers=auth(users["A"]["token"]),
        )
        assert r.status_code == 400, r.text

    def test_non_admin_cannot_change_role(self, users):
        r = requests.put(
            f"{API}/trees/{STATE['tree_a']}/members/role",
            json={"user_id": users["V"]["id"], "role": "viewer"},
            headers=auth(users["V"]["token"]),
        )
        assert r.status_code == 403

    def test_remove_non_owner_member(self, users, mongo_db):
        # Insert a second synthetic member to remove
        temp_uid = f"user_{uuid.uuid4().hex[:12]}"
        mongo_db.users.insert_one({
            "user_id": temp_uid,
            "email": f"TEST_MT_temp_{temp_uid}@example.com",
            "name": "TEST_MT_TempMember",
            "role": "viewer",
            "created_at": now_utc(),
        })
        CREATED["user_ids"].add(temp_uid)
        mongo_db.tree_members.insert_one({
            "id": str(uuid.uuid4()),
            "tree_id": STATE["tree_a"],
            "user_id": temp_uid,
            "role": "viewer",
            "joined_at": now_utc(),
        })
        r = requests.delete(f"{API}/trees/{STATE['tree_a']}/members/{temp_uid}",
                            headers=auth(users["A"]["token"]))
        assert r.status_code == 200, r.text
        # verify gone
        m = requests.get(f"{API}/trees/{STATE['tree_a']}/members",
                         headers=auth(users["A"]["token"])).json()
        assert temp_uid not in {mm["user_id"] for mm in m["members"]}

    def test_cannot_remove_owner(self, users):
        r = requests.delete(
            f"{API}/trees/{STATE['tree_a']}/members/{users['A']['id']}",
            headers=auth(users["A"]["token"]),
        )
        assert r.status_code == 400, r.text


# ---------------------------------------------------------------------------
# 5. Backup / Restore — tree-scoped, no leakage across trees
# ---------------------------------------------------------------------------
class TestBackupRestoreScoped:
    def test_backup_only_returns_this_tree(self, users, mongo_db):
        # Ensure tree_b has 1 person (its root) — add a marker child
        root_b_doc = mongo_db.people.find_one({"tree_id": STATE["tree_b"], "is_root": True})
        root_b_id = root_b_doc["id"]
        r = requests.post(
            f"{API}/people/add-relative",
            params={"tree_id": STATE["tree_b"]},
            json={"focus_id": root_b_id, "direction": "child",
                  "person": {"name": "TEST_MT_TreeBOnly"}},
            headers=auth(users["B"]["token"]),
        )
        assert r.status_code == 200, r.text

        # A's backup must NOT contain 'TEST_MT_TreeBOnly'
        bk = requests.get(f"{API}/backup", params={"tree_id": STATE["tree_a"]},
                          headers=auth(users["A"]["token"]))
        assert bk.status_code == 200, bk.text
        data = bk.json()
        assert data["tree"]["id"] == STATE["tree_a"]
        names = {p["name"] for p in data["people"]}
        assert "TEST_MT_TreeBOnly" not in names
        # And every person carries the correct tree_id
        for p in data["people"]:
            assert p.get("tree_id") == STATE["tree_a"]

    def test_non_admin_backup_forbidden(self, users):
        r = requests.get(f"{API}/backup", params={"tree_id": STATE["tree_a"]},
                         headers=auth(users["V"]["token"]))  # V is now editor after earlier test
        assert r.status_code == 403

    def test_restore_only_touches_target_tree(self, users, mongo_db):
        # Snapshot tree_b's people count BEFORE restore on tree_a
        b_count_before = mongo_db.people.count_documents(
            {"tree_id": STATE["tree_b"], "deleted_at": None})

        bk = requests.get(f"{API}/backup", params={"tree_id": STATE["tree_a"]},
                          headers=auth(users["A"]["token"])).json()
        r = requests.post(
            f"{API}/restore",
            params={"tree_id": STATE["tree_a"]},
            json={"people": bk["people"], "relations": bk["relations"]},
            headers=auth(users["A"]["token"]),
        )
        assert r.status_code == 200, r.text

        b_count_after = mongo_db.people.count_documents(
            {"tree_id": STATE["tree_b"], "deleted_at": None})
        assert b_count_before == b_count_after, \
            f"Restore on tree_a touched tree_b! before={b_count_before} after={b_count_after}"


# ---------------------------------------------------------------------------
# 6. Chat & person notes — tree scoped
# ---------------------------------------------------------------------------
class TestChatTreeScoped:
    def test_post_and_get_chat_uses_tree_id_as_room(self, users):
        r = requests.post(
            f"{API}/chat", params={"tree_id": STATE["tree_a"]},
            json={"message": "TEST_MT_ChatMsg"},
            headers=auth(users["A"]["token"]),
        )
        assert r.status_code == 200, r.text
        msg_id = r.json()["id"]
        STATE["chat_msg_id"] = msg_id

        got = requests.get(f"{API}/chat", params={"tree_id": STATE["tree_a"]},
                           headers=auth(users["A"]["token"])).json()
        assert got["room_id"] == STATE["tree_a"]
        assert msg_id in [m["id"] for m in got["messages"]]

    def test_chat_isolation_between_trees(self, users):
        # B's chat must not contain A's message
        got_b = requests.get(f"{API}/chat", params={"tree_id": STATE["tree_b"]},
                             headers=auth(users["B"]["token"])).json()
        assert STATE["chat_msg_id"] not in [m["id"] for m in got_b["messages"]]
        assert got_b["room_id"] == STATE["tree_b"]

    def test_delete_chat_by_sender(self, users):
        r = requests.delete(f"{API}/chat/{STATE['chat_msg_id']}",
                            headers=auth(users["A"]["token"]))
        assert r.status_code == 200
        got = requests.get(f"{API}/chat", params={"tree_id": STATE["tree_a"]},
                           headers=auth(users["A"]["token"])).json()
        assert STATE["chat_msg_id"] not in [m["id"] for m in got["messages"]]

    def test_non_member_cannot_post_chat(self, users):
        r = requests.post(
            f"{API}/chat", params={"tree_id": STATE["tree_a"]},
            json={"message": "TEST_MT_Intruder"},
            headers=auth(users["B"]["token"]),
        )
        assert r.status_code == 403


class TestPersonNotesTreeScoped:
    def test_add_and_list_note_scoped(self, users):
        r = requests.post(
            f"{API}/people/{STATE['root_a']}/notes",
            params={"tree_id": STATE["tree_a"]},
            json={"note_text": "TEST_MT_Note1"},
            headers=auth(users["A"]["token"]),
        )
        assert r.status_code == 200, r.text
        note_id = r.json()["id"]

        r2 = requests.get(
            f"{API}/people/{STATE['root_a']}/notes",
            params={"tree_id": STATE["tree_a"]},
            headers=auth(users["A"]["token"]),
        )
        assert r2.status_code == 200
        assert note_id in [n["id"] for n in r2.json()]

    def test_non_member_cannot_add_note(self, users):
        r = requests.post(
            f"{API}/people/{STATE['root_a']}/notes",
            params={"tree_id": STATE["tree_a"]},
            json={"note_text": "TEST_MT_ForbiddenNote"},
            headers=auth(users["B"]["token"]),
        )
        # B is not a member -> resolve_tree raises 403
        assert r.status_code == 403
