"""KETURUNANKU backend tests — Join Tree flow (Onboarding + Search + Join Requests).

Covers:
- PUT /api/trees/{tid}/visibility            (admin toggles is_public; non-admin 403)
- GET /api/trees/search?q=                   (only public; min 2 chars; enrichment fields)
- POST /api/trees/{tid}/join-request         (create/idempotent/already-member/404)
- GET /api/trees/{tid}/join-requests         (admin-only; enriched with name/email/picture)
- POST /api/join-requests/{req_id}/approve   (adds editor member + marks approved)
- POST /api/join-requests/{req_id}/reject    (marks rejected; no member add)
- Invalid action -> 400; unknown req_id -> 404
- Full flow: B searches -> requests -> admin A approves -> B can GET /api/tree?tree_id=A

Cleanup: ONLY docs we create are removed. Never delete_many({}).
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


CREATED = {
    "user_ids": set(),
    "session_tokens": set(),
    "tree_ids": set(),
    "join_request_ids": set(),
}


@pytest.fixture(scope="module")
def mongo_db():
    c = MongoClient(MONGO_URL)
    return c[DB_NAME]


def _seed_user(db, name="TEST_JOIN_User"):
    uid = f"user_{uuid.uuid4().hex[:12]}"
    email = f"TEST_JOIN_{uuid.uuid4().hex[:8]}@example.com"
    token = secrets.token_hex(16)
    db.users.insert_one({
        "user_id": uid,
        "email": email,
        "name": f"{name}_{uid[-4:]}",
        "picture": f"https://example.com/pic_{uid[-4:]}.png",
        "role": "viewer",
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


@pytest.fixture(scope="module")
def users(mongo_db):
    """A = admin/owner of tree_a; B = outsider; C = another outsider."""
    a_id, a_tok, a_email = _seed_user(mongo_db, name="TEST_JOIN_A")
    b_id, b_tok, b_email = _seed_user(mongo_db, name="TEST_JOIN_B")
    c_id, c_tok, c_email = _seed_user(mongo_db, name="TEST_JOIN_C")
    yield {
        "A": {"id": a_id, "token": a_tok, "email": a_email},
        "B": {"id": b_id, "token": b_tok, "email": b_email},
        "C": {"id": c_id, "token": c_tok, "email": c_email},
    }
    # ------- Teardown: delete ONLY our synthetic docs -------
    tree_ids = list(CREATED["tree_ids"])
    user_ids = list(CREATED["user_ids"])
    tokens = list(CREATED["session_tokens"])
    jr_ids = list(CREATED["join_request_ids"])

    if tree_ids:
        mongo_db.trees.delete_many({"id": {"$in": tree_ids}})
        mongo_db.tree_members.delete_many({"tree_id": {"$in": tree_ids}})
        mongo_db.people.delete_many({"tree_id": {"$in": tree_ids}})
        mongo_db.relations.delete_many({"tree_id": {"$in": tree_ids}})
    # Any join_requests our users created for any tree
    mongo_db.join_requests.delete_many({"user_id": {"$in": user_ids}})
    if jr_ids:
        mongo_db.join_requests.delete_many({"id": {"$in": jr_ids}})
    # Auto-trees owned by test users (paranoid catch-all — no-op if none)
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


STATE = {}
# Unique-ish name suffix so search results are deterministic even in a shared DB
NAME_TAG = f"TEST_JOIN_TreeA_{uuid.uuid4().hex[:6]}"


# ---------------------------------------------------------------------------
# 0. Setup — user A creates a tree via API
# ---------------------------------------------------------------------------
class TestSetup:
    def test_user_a_creates_tree(self, users):
        r = requests.post(f"{API}/trees", json={"name": NAME_TAG},
                          headers=auth(users["A"]["token"]))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["role"] == "admin"
        assert d["owner_id"] == users["A"]["id"]
        STATE["tree_a"] = d["id"]
        CREATED["tree_ids"].add(d["id"])


# ---------------------------------------------------------------------------
# 1. PUT /api/trees/{tid}/visibility
# ---------------------------------------------------------------------------
class TestVisibility:
    def test_non_admin_forbidden(self, users):
        r = requests.put(f"{API}/trees/{STATE['tree_a']}/visibility",
                         json={"is_public": True},
                         headers=auth(users["B"]["token"]))
        assert r.status_code == 403, r.text

    def test_admin_can_set_public_true(self, users, mongo_db):
        r = requests.put(f"{API}/trees/{STATE['tree_a']}/visibility",
                         json={"is_public": True},
                         headers=auth(users["A"]["token"]))
        assert r.status_code == 200, r.text
        assert r.json()["is_public"] is True
        # verify persisted
        t = mongo_db.trees.find_one({"id": STATE["tree_a"]}, {"_id": 0})
        assert t["is_public"] is True

    def test_admin_can_set_public_false(self, users, mongo_db):
        r = requests.put(f"{API}/trees/{STATE['tree_a']}/visibility",
                         json={"is_public": False},
                         headers=auth(users["A"]["token"]))
        assert r.status_code == 200, r.text
        assert r.json()["is_public"] is False
        t = mongo_db.trees.find_one({"id": STATE["tree_a"]}, {"_id": 0})
        assert t["is_public"] is False

    def test_re_set_public_true_for_downstream_tests(self, users):
        r = requests.put(f"{API}/trees/{STATE['tree_a']}/visibility",
                         json={"is_public": True},
                         headers=auth(users["A"]["token"]))
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# 2. GET /api/trees/search
# ---------------------------------------------------------------------------
class TestSearch:
    def test_min_two_chars_returns_empty(self, users):
        r = requests.get(f"{API}/trees/search", params={"q": "a"},
                         headers=auth(users["B"]["token"]))
        assert r.status_code == 200
        assert r.json() == []

    def test_empty_query_returns_empty(self, users):
        r = requests.get(f"{API}/trees/search", params={"q": ""},
                         headers=auth(users["B"]["token"]))
        assert r.status_code == 200
        assert r.json() == []

    def test_public_tree_appears_with_enrichment(self, users):
        # NAME_TAG is unique; must be present and only ours
        r = requests.get(f"{API}/trees/search", params={"q": NAME_TAG[:10]},
                         headers=auth(users["B"]["token"]))
        assert r.status_code == 200, r.text
        results = r.json()
        hits = [t for t in results if t["id"] == STATE["tree_a"]]
        assert len(hits) == 1, f"Expected our tree in results, got: {results}"
        h = hits[0]
        assert h["name"] == NAME_TAG
        assert "owner_name" in h and h["owner_name"] and h["owner_name"] != "?"
        assert isinstance(h["member_count"], int) and h["member_count"] >= 1
        assert h["is_member"] is False   # B is not member yet
        assert h["pending"] is False     # no request yet

    def test_private_tree_not_returned(self, users, mongo_db):
        # Toggle private, search must not return it
        requests.put(f"{API}/trees/{STATE['tree_a']}/visibility",
                     json={"is_public": False},
                     headers=auth(users["A"]["token"]))
        r = requests.get(f"{API}/trees/search", params={"q": NAME_TAG[:10]},
                         headers=auth(users["B"]["token"]))
        assert r.status_code == 200
        assert not any(t["id"] == STATE["tree_a"] for t in r.json())
        # Restore public for further tests
        requests.put(f"{API}/trees/{STATE['tree_a']}/visibility",
                     json={"is_public": True},
                     headers=auth(users["A"]["token"]))

    def test_is_member_true_for_owner(self, users):
        r = requests.get(f"{API}/trees/search", params={"q": NAME_TAG[:10]},
                         headers=auth(users["A"]["token"]))
        assert r.status_code == 200
        hits = [t for t in r.json() if t["id"] == STATE["tree_a"]]
        assert hits and hits[0]["is_member"] is True


# ---------------------------------------------------------------------------
# 3. POST /api/trees/{tid}/join-request
# ---------------------------------------------------------------------------
class TestCreateJoinRequest:
    def test_unknown_tree_returns_404(self, users):
        r = requests.post(f"{API}/trees/tree_nonexistent_xyz/join-request",
                          headers=auth(users["B"]["token"]))
        assert r.status_code == 404, r.text

    def test_b_creates_join_request(self, users, mongo_db):
        r = requests.post(f"{API}/trees/{STATE['tree_a']}/join-request",
                          headers=auth(users["B"]["token"]))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["status"] == "pending"
        assert body["tree_name"] == NAME_TAG
        # Verify DB
        docs = list(mongo_db.join_requests.find(
            {"tree_id": STATE["tree_a"], "user_id": users["B"]["id"], "status": "pending"}))
        assert len(docs) == 1, f"Expected exactly 1 pending doc, got {len(docs)}"
        CREATED["join_request_ids"].add(docs[0]["id"])
        STATE["req_b"] = docs[0]["id"]

    def test_idempotent_no_duplicate(self, users, mongo_db):
        r = requests.post(f"{API}/trees/{STATE['tree_a']}/join-request",
                          headers=auth(users["B"]["token"]))
        assert r.status_code == 200, r.text
        # Should still be exactly 1 pending
        n = mongo_db.join_requests.count_documents(
            {"tree_id": STATE["tree_a"], "user_id": users["B"]["id"], "status": "pending"})
        assert n == 1, f"Duplicate pending join_request created (count={n})"

    def test_search_now_shows_pending_true_for_b(self, users):
        r = requests.get(f"{API}/trees/search", params={"q": NAME_TAG[:10]},
                         headers=auth(users["B"]["token"]))
        assert r.status_code == 200
        hits = [t for t in r.json() if t["id"] == STATE["tree_a"]]
        assert hits and hits[0]["pending"] is True
        assert hits[0]["is_member"] is False


# ---------------------------------------------------------------------------
# 4. GET /api/trees/{tid}/join-requests  (admin only)
# ---------------------------------------------------------------------------
class TestListJoinRequests:
    def test_non_admin_forbidden(self, users):
        r = requests.get(f"{API}/trees/{STATE['tree_a']}/join-requests",
                         headers=auth(users["B"]["token"]))
        assert r.status_code == 403, r.text

    def test_admin_sees_enriched_requests(self, users):
        r = requests.get(f"{API}/trees/{STATE['tree_a']}/join-requests",
                         headers=auth(users["A"]["token"]))
        assert r.status_code == 200, r.text
        lst = r.json()
        assert isinstance(lst, list)
        b_req = next((x for x in lst if x["user_id"] == users["B"]["id"]), None)
        assert b_req is not None
        assert b_req["status"] == "pending"
        assert b_req["email"] == users["B"]["email"]
        assert b_req["name"]        # non-empty
        assert "picture" in b_req   # even if None; here we set a pic
        assert b_req["picture"]


# ---------------------------------------------------------------------------
# 5. Reject flow (use user C to test reject; user B remains for approve)
# ---------------------------------------------------------------------------
class TestReject:
    def test_c_creates_join_request(self, users, mongo_db):
        r = requests.post(f"{API}/trees/{STATE['tree_a']}/join-request",
                          headers=auth(users["C"]["token"]))
        assert r.status_code == 200, r.text
        doc = mongo_db.join_requests.find_one(
            {"tree_id": STATE["tree_a"], "user_id": users["C"]["id"], "status": "pending"})
        assert doc
        CREATED["join_request_ids"].add(doc["id"])
        STATE["req_c"] = doc["id"]

    def test_invalid_action_returns_400(self, users):
        r = requests.post(f"{API}/join-requests/{STATE['req_c']}/foobar",
                          headers=auth(users["A"]["token"]))
        assert r.status_code == 400, r.text

    def test_unknown_req_id_returns_404(self, users):
        r = requests.post(f"{API}/join-requests/nonexistent_xxx/approve",
                          headers=auth(users["A"]["token"]))
        assert r.status_code == 404, r.text

    def test_admin_rejects_c(self, users, mongo_db):
        r = requests.post(f"{API}/join-requests/{STATE['req_c']}/reject",
                          headers=auth(users["A"]["token"]))
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True
        # Verify DB: status=rejected, resolved_at present, NOT a tree_member
        doc = mongo_db.join_requests.find_one({"id": STATE["req_c"]})
        assert doc["status"] == "rejected"
        assert doc.get("resolved_at") is not None
        m = mongo_db.tree_members.find_one(
            {"tree_id": STATE["tree_a"], "user_id": users["C"]["id"]})
        assert m is None, "Rejected request must NOT create a tree_member"


# ---------------------------------------------------------------------------
# 6. Approve flow (user B) + full end-to-end
# ---------------------------------------------------------------------------
class TestApproveAndFullFlow:
    def test_b_cannot_read_tree_before_approval(self, users):
        r = requests.get(f"{API}/tree", params={"tree_id": STATE["tree_a"]},
                         headers=auth(users["B"]["token"]))
        assert r.status_code == 403, r.text

    def test_admin_approves_b(self, users, mongo_db):
        r = requests.post(f"{API}/join-requests/{STATE['req_b']}/approve",
                          headers=auth(users["A"]["token"]))
        assert r.status_code == 200, r.text
        # Verify DB
        doc = mongo_db.join_requests.find_one({"id": STATE["req_b"]})
        assert doc["status"] == "approved"
        assert doc.get("resolved_at") is not None
        m = mongo_db.tree_members.find_one(
            {"tree_id": STATE["tree_a"], "user_id": users["B"]["id"]})
        assert m is not None, "Approved request must add tree_member"
        assert m["role"] == "editor"

    def test_b_now_appears_in_members(self, users):
        r = requests.get(f"{API}/trees/{STATE['tree_a']}/members",
                         headers=auth(users["A"]["token"]))
        assert r.status_code == 200, r.text
        by_id = {m["user_id"]: m for m in r.json()["members"]}
        assert users["B"]["id"] in by_id
        assert by_id[users["B"]["id"]]["role"] == "editor"
        assert by_id[users["B"]["id"]]["is_owner"] is False

    def test_b_can_get_tree_by_id(self, users):
        r = requests.get(f"{API}/tree", params={"tree_id": STATE["tree_a"]},
                         headers=auth(users["B"]["token"]))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["tree"]["id"] == STATE["tree_a"]
        assert d["role"] == "editor"

    def test_search_now_shows_is_member_true_for_b(self, users):
        r = requests.get(f"{API}/trees/search", params={"q": NAME_TAG[:10]},
                         headers=auth(users["B"]["token"]))
        assert r.status_code == 200
        hits = [t for t in r.json() if t["id"] == STATE["tree_a"]]
        assert hits and hits[0]["is_member"] is True
        # pending must now be False (request was resolved)
        assert hits[0]["pending"] is False

    def test_join_requests_list_no_longer_shows_b(self, users):
        # Only status=pending is listed; B is now approved
        r = requests.get(f"{API}/trees/{STATE['tree_a']}/join-requests",
                         headers=auth(users["A"]["token"]))
        assert r.status_code == 200
        assert not any(x["user_id"] == users["B"]["id"] for x in r.json())

    def test_existing_member_cannot_re_request(self, users):
        r = requests.post(f"{API}/trees/{STATE['tree_a']}/join-request",
                          headers=auth(users["B"]["token"]))
        assert r.status_code == 400, r.text
