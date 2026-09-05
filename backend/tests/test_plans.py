"""Backend tests for KETURUNANKU 3-tier subscription plans + limit enforcement.

CRITICAL: DB may hold REAL production data. This file MUST only insert synthetic
docs and MUST only delete docs it created (tracked in the module-level CREATED
registry). NEVER call delete_many({}).

Run: cd /app/backend/tests && pytest test_plans.py -n 0 -v
(pytest.ini forces -n 2 --dist loadscope; module-level shared state requires -n 0.)
"""
import io
import os
import uuid
import secrets
from datetime import datetime, timezone, timedelta

import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

BASE_URL = "http://localhost:8001/api"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

_client = MongoClient(MONGO_URL)
db = _client[DB_NAME]


def now_utc():
    return datetime.now(timezone.utc)


# Registry of everything we create so teardown deletes ONLY our synthetic docs
CREATED = {
    "user_ids": set(),
    "session_tokens": set(),
    "tree_ids": set(),
    "person_ids": set(),
    "note_ids": set(),
    "invite_tokens": set(),
    "member_ids": set(),   # tree_members _uuid_ ids that we inserted directly
}


def _seed_user(name_prefix="PLAN"):
    uid = f"user_{uuid.uuid4().hex[:12]}"
    tok = secrets.token_hex(16)
    email = f"TEST_PLAN_{uid[-6:]}@example.com"
    db.users.insert_one({
        "user_id": uid,
        "email": email,
        "name": f"TEST_{name_prefix}_{uid[-4:]}",
        "picture": None,
        "role": "admin",   # global role (only used for legacy endpoints)
        "created_at": now_utc(),
    })
    db.user_sessions.insert_one({
        "session_token": tok,
        "user_id": uid,
        "created_at": now_utc(),
        "expires_at": now_utc() + timedelta(days=7),
    })
    CREATED["user_ids"].add(uid)
    CREATED["session_tokens"].add(tok)
    return uid, tok, email


def auth(tok):
    return {"Authorization": f"Bearer {tok}"}


def _api_create_tree(tok, name):
    r = requests.post(f"{BASE_URL}/trees", headers=auth(tok), json={"name": name}, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    CREATED["tree_ids"].add(data["id"])
    return data


# ---------------------------------------------------------------------------
# Session-scoped: seed one admin user, everything else is per-class
# ---------------------------------------------------------------------------
STATE = {}


@pytest.fixture(scope="session", autouse=True)
def _seed_and_teardown():
    """Seed base users and always clean up only what this test run created."""
    STATE["admin_id"], STATE["admin_tok"], STATE["admin_email"] = _seed_user("ADMIN")
    yield
    # Teardown: delete ONLY docs we created.
    tids = list(CREATED["tree_ids"])
    if tids:
        db.people.delete_many({"tree_id": {"$in": tids}})
        db.relations.delete_many({"tree_id": {"$in": tids}})
        db.tree_members.delete_many({"tree_id": {"$in": tids}})
        db.trees.delete_many({"id": {"$in": tids}})
        db.family_chat.delete_many({"tree_id": {"$in": tids}})
        db.person_notes.delete_many({"tree_id": {"$in": tids}})
        db.app_notifications.delete_many({"tree_id": {"$in": tids}})
        db.tree_invites.delete_many({"tree_id": {"$in": tids}})
    uids = list(CREATED["user_ids"])
    if uids:
        db.users.delete_many({"user_id": {"$in": uids}})
        db.tree_members.delete_many({"user_id": {"$in": uids}})
        db.user_sessions.delete_many({"user_id": uids[0]} if False else {"user_id": {"$in": uids}})


# ===========================================================================
# 1. Basic tree creation + list-shape (plan_limits, editor_count, photo_count)
# ===========================================================================
class TestTreeCreateAndList:
    def test_create_tree_returns_admin_role_and_free_plan(self):
        tok = STATE["admin_tok"]
        data = _api_create_tree(tok, "TEST_PLAN_TreeCreate")
        STATE["ct_tree_id"] = data["id"]
        assert data["role"] == "admin"
        assert data["plan"] == "free"
        assert data["person_count"] == 1
        assert data["member_count"] == 1
        assert data["limit"] == 50
        assert data["plan_limits"] == {"people": 50, "editors": 3, "photos": 20}

    def test_list_trees_returns_new_fields(self):
        r = requests.get(f"{BASE_URL}/trees", headers=auth(STATE["admin_tok"]), timeout=15)
        assert r.status_code == 200, r.text
        trees = r.json()
        t = next((x for x in trees if x["id"] == STATE["ct_tree_id"]), None)
        assert t is not None, "Newly created tree not in listing"
        # Every new field required by the spec
        for key in ("role", "person_count", "member_count", "editor_count",
                    "photo_count", "plan_limits", "limit"):
            assert key in t, f"missing key '{key}' in /trees item: {t}"
        assert t["role"] == "admin"
        assert t["editor_count"] == 0
        assert t["photo_count"] == 0
        assert t["plan_limits"]["people"] == 50
        assert t["plan_limits"]["editors"] == 3
        assert t["plan_limits"]["photos"] == 20
        assert t["limit"] == 50

    def test_tree_has_root_person(self):
        r = requests.get(f"{BASE_URL}/tree", params={"tree_id": STATE["ct_tree_id"]},
                         headers=auth(STATE["admin_tok"]), timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["root_id"] is not None
        assert d["role"] == "admin"
        STATE["ct_root_id"] = d["root_id"]


# ===========================================================================
# 2. THE 2-TREE FLOW — Tree A free, Tree B upgraded to pro
# ===========================================================================
class TestTwoTreeFlow:
    def test_setup_two_trees_and_upgrade_b(self):
        tok = STATE["admin_tok"]
        a = _api_create_tree(tok, "TEST_PLAN_TreeA")
        b = _api_create_tree(tok, "TEST_PLAN_TreeB")
        STATE["A"] = a["id"]
        STATE["B"] = b["id"]

        # Upgrade only B to pro
        r = requests.post(f"{BASE_URL}/trees/{b['id']}/upgrade",
                          headers=auth(tok), json={"plan": "pro"}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["plan"] == "pro"

    def test_list_shows_a_free_and_b_pro(self):
        r = requests.get(f"{BASE_URL}/trees", headers=auth(STATE["admin_tok"]), timeout=15)
        assert r.status_code == 200, r.text
        trees = {t["id"]: t for t in r.json()}
        a, b = trees[STATE["A"]], trees[STATE["B"]]
        # Tree A remains free
        assert a["plan"] == "free"
        assert a["limit"] == 50
        assert a["plan_limits"] == {"people": 50, "editors": 3, "photos": 20}
        # Tree B is pro: people unlimited (None), editors=10
        assert b["plan"] == "pro"
        assert b["limit"] is None
        assert b["plan_limits"]["editors"] == 10
        assert b["plan_limits"]["people"] is None
        assert b["plan_limits"]["photos"] is None


# ===========================================================================
# 3. PEOPLE LIMIT — free = 50, then upgrade unlocks
# ===========================================================================
class TestPeopleLimit:
    """Uses Tree A from TestTwoTreeFlow. Fills to 50 via DB seed (fast), then
    tries API add-relative (should 402), then upgrades and retries (should 200).
    """

    def test_free_tree_402_at_51st(self):
        tid = STATE["A"]
        tok = STATE["admin_tok"]
        # get root
        r = requests.get(f"{BASE_URL}/tree", params={"tree_id": tid},
                         headers=auth(tok), timeout=15)
        assert r.status_code == 200, r.text
        root = r.json()["root_id"]
        # Tree A has 1 person (root) — insert 49 synthetic to reach 50.
        docs = []
        for i in range(49):
            pid = str(uuid.uuid4())
            docs.append({
                "id": pid, "tree_id": tid, "name": f"TEST_PLAN_Fill_{i}",
                "gender": None, "is_alive": True, "is_root": False,
                "created_by": STATE["admin_id"], "created_at": now_utc(),
                "deleted_at": None,
            })
            CREATED["person_ids"].add(pid)
        db.people.insert_many(docs)
        assert db.people.count_documents({"tree_id": tid, "deleted_at": None}) == 50

        # 51st via API MUST 402 LIMIT_REACHED
        r = requests.post(f"{BASE_URL}/people/add-relative",
                          params={"tree_id": tid}, headers=auth(tok),
                          json={"focus_id": root, "direction": "child",
                                "person": {"name": "TEST_PLAN_51st"}}, timeout=15)
        assert r.status_code == 402, r.text
        assert r.json()["detail"].startswith("LIMIT_REACHED:")

    def test_upgrade_to_pro_unlocks_add(self):
        tid = STATE["A"]
        tok = STATE["admin_tok"]
        # Upgrade A to pro
        r = requests.post(f"{BASE_URL}/trees/{tid}/upgrade",
                          headers=auth(tok), json={"plan": "pro"}, timeout=15)
        assert r.status_code == 200 and r.json()["plan"] == "pro"

        # get root & add beyond 50
        r = requests.get(f"{BASE_URL}/tree", params={"tree_id": tid},
                         headers=auth(tok), timeout=15)
        root = r.json()["root_id"]
        r = requests.post(f"{BASE_URL}/people/add-relative",
                          params={"tree_id": tid}, headers=auth(tok),
                          json={"focus_id": root, "direction": "child",
                                "person": {"name": "TEST_PLAN_AfterPro"}}, timeout=15)
        assert r.status_code == 200, r.text
        CREATED["person_ids"].add(r.json()["person"]["id"])
        assert db.people.count_documents({"tree_id": tid, "deleted_at": None}) >= 51

    def test_pro_tree_reports_unlimited(self):
        r = requests.get(f"{BASE_URL}/tree", params={"tree_id": STATE["A"]},
                         headers=auth(STATE["admin_tok"]), timeout=15)
        assert r.status_code == 200
        assert r.json()["limit"] is None


# ===========================================================================
# 4. UPGRADE plan values + RBAC
# ===========================================================================
class TestUpgradeRBAC:
    def test_family_plan_gives_editors_50_people_none(self):
        # Create a fresh tree so we don't disturb existing state
        t = _api_create_tree(STATE["admin_tok"], "TEST_PLAN_FamilyTree")
        tid = t["id"]
        r = requests.post(f"{BASE_URL}/trees/{tid}/upgrade",
                          headers=auth(STATE["admin_tok"]),
                          json={"plan": "family"}, timeout=15)
        assert r.status_code == 200 and r.json()["plan"] == "family"
        # Verify plan_limits shape
        r = requests.get(f"{BASE_URL}/trees", headers=auth(STATE["admin_tok"]), timeout=15)
        t = next(x for x in r.json() if x["id"] == tid)
        assert t["plan"] == "family"
        assert t["plan_limits"]["editors"] == 50
        assert t["plan_limits"]["people"] is None
        assert t["plan_limits"]["photos"] is None
        assert t["limit"] is None

    def test_pro_upgrade_accepted(self):
        t = _api_create_tree(STATE["admin_tok"], "TEST_PLAN_ProTree")
        r = requests.post(f"{BASE_URL}/trees/{t['id']}/upgrade",
                          headers=auth(STATE["admin_tok"]),
                          json={"plan": "pro"}, timeout=15)
        assert r.status_code == 200 and r.json()["plan"] == "pro"

    def test_non_admin_cannot_upgrade(self):
        # Create tree with admin, then seed a second user as viewer + editor member
        t = _api_create_tree(STATE["admin_tok"], "TEST_PLAN_RBACTree")
        tid = t["id"]

        # Seed a viewer member
        viewer_id, viewer_tok, _ = _seed_user("VIEWER")
        mid = str(uuid.uuid4())
        db.tree_members.insert_one({
            "id": mid, "tree_id": tid, "user_id": viewer_id,
            "role": "viewer", "joined_at": now_utc(),
        })
        CREATED["member_ids"].add(mid)

        # Also seed as editor via another user
        editor_id, editor_tok, _ = _seed_user("EDITOR")
        mid2 = str(uuid.uuid4())
        db.tree_members.insert_one({
            "id": mid2, "tree_id": tid, "user_id": editor_id,
            "role": "editor", "joined_at": now_utc(),
        })
        CREATED["member_ids"].add(mid2)

        # Viewer -> 403
        r = requests.post(f"{BASE_URL}/trees/{tid}/upgrade",
                          headers=auth(viewer_tok),
                          json={"plan": "pro"}, timeout=15)
        assert r.status_code == 403, r.text

        # Editor -> 403 (only admin may upgrade)
        r = requests.post(f"{BASE_URL}/trees/{tid}/upgrade",
                          headers=auth(editor_tok),
                          json={"plan": "pro"}, timeout=15)
        assert r.status_code == 403, r.text


# ===========================================================================
# 5. EDITOR LIMIT — free plan caps at 3 editors
# ===========================================================================
class TestEditorLimit:
    def test_invite_accept_hits_editor_limit_then_upgrade_unlocks(self):
        # Fresh free tree owned by admin
        t = _api_create_tree(STATE["admin_tok"], "TEST_PLAN_EditorLimitTree")
        tid = t["id"]

        # Seed 3 editor members directly to reach the free-plan cap of 3
        for _ in range(3):
            uid, _, _ = _seed_user("EDITOR_SEED")
            mid = str(uuid.uuid4())
            db.tree_members.insert_one({
                "id": mid, "tree_id": tid, "user_id": uid,
                "role": "editor", "joined_at": now_utc(),
            })
            CREATED["member_ids"].add(mid)

        # Sanity: editor_count exposed by /trees
        r = requests.get(f"{BASE_URL}/trees", headers=auth(STATE["admin_tok"]), timeout=15)
        t_row = next(x for x in r.json() if x["id"] == tid)
        assert t_row["editor_count"] == 3

        # Create invite-link
        r = requests.post(f"{BASE_URL}/trees/{tid}/invite-link",
                          headers=auth(STATE["admin_tok"]), timeout=15)
        assert r.status_code == 200, r.text
        token = r.json()["token"]
        CREATED["invite_tokens"].add(token)

        # A fresh (4th) user tries to accept -> 402 EDITOR_LIMIT
        new_uid, new_tok, _ = _seed_user("EDITOR_ACCEPT")
        r = requests.post(f"{BASE_URL}/invite-accept/{token}",
                          headers=auth(new_tok), timeout=15)
        assert r.status_code == 402, r.text
        assert r.json()["detail"].startswith("EDITOR_LIMIT:")

        # Upgrade to pro (editors=10) and retry -> 200
        r = requests.post(f"{BASE_URL}/trees/{tid}/upgrade",
                          headers=auth(STATE["admin_tok"]),
                          json={"plan": "pro"}, timeout=15)
        assert r.status_code == 200

        r = requests.post(f"{BASE_URL}/invite-accept/{token}",
                          headers=auth(new_tok), timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["tree_id"] == tid

        # Verify the accepting user is now an editor
        assert db.tree_members.count_documents(
            {"tree_id": tid, "user_id": new_uid, "role": "editor"}) == 1

        STATE["editor_limit_tree_id"] = tid
        STATE["editor_limit_new_uid"] = new_uid
        STATE["editor_limit_token"] = token

    def test_invite_accept_idempotent(self):
        # Accepting again should NOT duplicate membership
        tid = STATE["editor_limit_tree_id"]
        new_tok = None
        # Retrieve the token this specific user was seeded with:
        # We stored session tokens for all seeded users; find the one matching the uid.
        uid = STATE["editor_limit_new_uid"]
        sess = db.user_sessions.find_one({"user_id": uid})
        new_tok = sess["session_token"]

        before = db.tree_members.count_documents({"tree_id": tid, "user_id": uid})
        r = requests.post(f"{BASE_URL}/invite-accept/{STATE['editor_limit_token']}",
                          headers=auth(new_tok), timeout=15)
        assert r.status_code == 200, r.text
        after = db.tree_members.count_documents({"tree_id": tid, "user_id": uid})
        assert before == after == 1, f"membership duplicated: before={before} after={after}"

    def test_change_member_role_402_when_at_editor_cap(self):
        # Fresh free tree, seed 3 editors + 1 viewer member; try promoting viewer -> 402
        t = _api_create_tree(STATE["admin_tok"], "TEST_PLAN_PromoteCapTree")
        tid = t["id"]
        for _ in range(3):
            uid, _, _ = _seed_user("PROMOTE_ED")
            mid = str(uuid.uuid4())
            db.tree_members.insert_one({
                "id": mid, "tree_id": tid, "user_id": uid, "role": "editor",
                "joined_at": now_utc(),
            })
            CREATED["member_ids"].add(mid)
        viewer_uid, _, _ = _seed_user("PROMOTE_VW")
        mid = str(uuid.uuid4())
        db.tree_members.insert_one({
            "id": mid, "tree_id": tid, "user_id": viewer_uid, "role": "viewer",
            "joined_at": now_utc(),
        })
        CREATED["member_ids"].add(mid)

        r = requests.put(f"{BASE_URL}/trees/{tid}/members/role",
                         headers=auth(STATE["admin_tok"]),
                         json={"user_id": viewer_uid, "role": "editor"}, timeout=15)
        assert r.status_code == 402, r.text
        assert r.json()["detail"].startswith("EDITOR_LIMIT:")

        # Upgrade to family (editors=50) -> promotion succeeds
        r = requests.post(f"{BASE_URL}/trees/{tid}/upgrade",
                          headers=auth(STATE["admin_tok"]),
                          json={"plan": "family"}, timeout=15)
        assert r.status_code == 200
        r = requests.put(f"{BASE_URL}/trees/{tid}/members/role",
                         headers=auth(STATE["admin_tok"]),
                         json={"user_id": viewer_uid, "role": "editor"}, timeout=15)
        assert r.status_code == 200, r.text


# ===========================================================================
# 6. PHOTO LIMIT — free plan caps at 20 photos
# ===========================================================================
class TestPhotoLimit:
    def test_photo_limit_402_then_upgrade_unlocks(self):
        # Fresh free tree, add a person we can upload against
        t = _api_create_tree(STATE["admin_tok"], "TEST_PLAN_PhotoTree")
        tid = t["id"]
        r = requests.get(f"{BASE_URL}/tree", params={"tree_id": tid},
                         headers=auth(STATE["admin_tok"]), timeout=15)
        root = r.json()["root_id"]

        # Insert 20 person_notes with non-empty attachments to reach the cap
        notes = []
        for i in range(20):
            nid = str(uuid.uuid4())
            notes.append({
                "id": nid, "person_id": root, "tree_id": tid,
                "author_id": STATE["admin_id"], "author_name": "TEST",
                "note_text": f"seed_photo_{i}",
                "attachments": [f"fake/path/{i}.jpg"],  # non-empty
                "created_at": now_utc(), "deleted_at": None,
            })
            CREATED["note_ids"].add(nid)
        db.person_notes.insert_many(notes)

        # Sanity: photo_count reflected in /trees
        r = requests.get(f"{BASE_URL}/trees", headers=auth(STATE["admin_tok"]), timeout=15)
        t_row = next(x for x in r.json() if x["id"] == tid)
        assert t_row["photo_count"] == 20

        # Uploading 21st file -> 402 PHOTO_LIMIT
        files = {"file": ("test.jpg", io.BytesIO(b"fakebytes"), "image/jpeg")}
        r = requests.post(f"{BASE_URL}/people/{root}/files",
                          params={"tree_id": tid},
                          headers=auth(STATE["admin_tok"]),
                          files=files, timeout=15)
        assert r.status_code == 402, r.text
        assert r.json()["detail"].startswith("PHOTO_LIMIT:")

        # Upgrade to pro (photos=None) -> upload succeeds
        r = requests.post(f"{BASE_URL}/trees/{tid}/upgrade",
                          headers=auth(STATE["admin_tok"]),
                          json={"plan": "pro"}, timeout=15)
        assert r.status_code == 200

        # Note: this second upload actually hits the storage backend. We just
        # want to confirm the plan check does NOT 402 anymore. If storage
        # succeeds we get 200; if storage init fails externally we still
        # expect NOT 402.
        files = {"file": ("test2.jpg", io.BytesIO(b"fakebytes2"), "image/jpeg")}
        r = requests.post(f"{BASE_URL}/people/{root}/files",
                          params={"tree_id": tid},
                          headers=auth(STATE["admin_tok"]),
                          files=files, timeout=30)
        assert r.status_code != 402, f"unexpected 402 after upgrade: {r.text}"
        if r.status_code == 200:
            body = r.json()
            CREATED["note_ids"].add(body["id"])


# ===========================================================================
# 7. Regression: cross-tenant isolation and existing tree scoping
# ===========================================================================
class TestRegression:
    def test_non_member_cannot_read_other_tree(self):
        # A brand-new user should not be able to GET Tree B (from earlier)
        _, tok, _ = _seed_user("STRANGER")
        r = requests.get(f"{BASE_URL}/tree", params={"tree_id": STATE["B"]},
                         headers=auth(tok), timeout=15)
        assert r.status_code == 403, r.text

    def test_chat_is_tree_scoped(self):
        # POST a chat msg to tree A, verify it appears in A's chat only
        tid_a = STATE["A"]
        tid_b = STATE["B"]
        r = requests.post(f"{BASE_URL}/chat",
                          params={"tree_id": tid_a},
                          headers=auth(STATE["admin_tok"]),
                          json={"message": "TEST_PLAN_isolated_chat"}, timeout=15)
        assert r.status_code == 200, r.text
        msg_id = r.json()["id"]
        # In A: present
        r_a = requests.get(f"{BASE_URL}/chat", params={"tree_id": tid_a},
                           headers=auth(STATE["admin_tok"]), timeout=15).json()
        assert any(m["id"] == msg_id for m in r_a["messages"])
        # In B: absent
        r_b = requests.get(f"{BASE_URL}/chat", params={"tree_id": tid_b},
                           headers=auth(STATE["admin_tok"]), timeout=15).json()
        assert not any(m["id"] == msg_id for m in r_b["messages"])
