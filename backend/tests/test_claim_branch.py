"""KETURUNANKU backend tests — POST /api/trees/{tid}/claim-branch.

Covers:
- scope='descendants' : person + all descendants + spouses (of anyone included)
- scope='children'    : person + direct children + spouses (of anyone included)
- scope='whole'       : full duplicate of source tree
- Relations remapping : only relations whose BOTH endpoints are copied are
                        carried over, with fresh ids + new tree_id
- Response fields     : person_count / copied / root_person_id (= new id of
                        the claimed person); is_root=True on that new doc
- Source tree stays UNCHANGED (people + relations counts identical)
- Caller becomes admin of the new tree (tree_members) and it shows up in
  GET /api/trees; GET /api/tree?tree_id=<new> returns the copies
- 404 for unknown person_id / 403 for non-member of source tree
- Regression: Free tree at 50 people → POST /people/add-relative → 402
              detail starts with 'LIMIT_REACHED'

Cleanup: ONLY our synthetic docs are removed (tracked ids); never
delete_many({}). Real family data in shared preview DB is preserved.
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


# All ids we touch — cleaned up on module teardown.
CREATED = {
    "user_ids": set(),
    "session_tokens": set(),
    "tree_ids": set(),      # trees we (or claim-branch) created
    "person_ids": set(),    # people we insert directly into the source tree
    "relation_ids": set(),  # relations we insert directly
}


@pytest.fixture(scope="module")
def mongo_db():
    c = MongoClient(MONGO_URL)
    return c[DB_NAME]


def _seed_user(db, name="TEST_CLAIM_User"):
    uid = f"user_{uuid.uuid4().hex[:12]}"
    email = f"TEST_CLAIM_{uuid.uuid4().hex[:8]}@example.com"
    token = secrets.token_hex(16)
    db.users.insert_one({
        "user_id": uid,
        "email": email,
        "name": f"{name}_{uid[-4:]}",
        "picture": None,
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


def _insert_person(db, tree_id, name, gender=None, is_root=False, created_by=None):
    pid = str(uuid.uuid4())
    db.people.insert_one({
        "id": pid,
        "tree_id": tree_id,
        "name": name,
        "email": None,
        "gender": gender,
        "birth_date": None,
        "birth_place": None,
        "death_date": None,
        "photo_url": None,
        "job": None,
        "is_adopted": False,
        "notes": None,
        "is_alive": True,
        "is_root": is_root,
        "created_by": created_by,
        "created_at": now_utc(),
        "deleted_at": None,
    })
    CREATED["person_ids"].add(pid)
    return pid


def _insert_relation(db, tree_id, person_id, related_person_id, rtype, created_by=None):
    rid = str(uuid.uuid4())
    db.relations.insert_one({
        "id": rid,
        "tree_id": tree_id,
        "person_id": person_id,
        "related_person_id": related_person_id,
        "relation_type": rtype,
        "created_by": created_by,
        "created_at": now_utc(),
        "deleted_at": None,
    })
    CREATED["relation_ids"].add(rid)
    return rid


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
NAME_TAG = f"TEST_CLAIM_TreeA_{uuid.uuid4().hex[:6]}"


@pytest.fixture(scope="module")
def users(mongo_db):
    a_id, a_tok, a_email = _seed_user(mongo_db, name="TEST_CLAIM_A")
    b_id, b_tok, b_email = _seed_user(mongo_db, name="TEST_CLAIM_B")  # outsider
    yield {
        "A": {"id": a_id, "token": a_tok, "email": a_email},
        "B": {"id": b_id, "token": b_tok, "email": b_email},
    }
    # ------------- Teardown: remove ONLY our synthetic docs -------------
    tree_ids = list(CREATED["tree_ids"])
    user_ids = list(CREATED["user_ids"])
    tokens = list(CREATED["session_tokens"])
    person_ids = list(CREATED["person_ids"])
    relation_ids = list(CREATED["relation_ids"])

    # Any trees the API auto-created (e.g. claim-branch new trees, /trees POST)
    auto = list(mongo_db.trees.find({"owner_id": {"$in": user_ids}}, {"id": 1}))
    all_tids = list({*tree_ids, *[t["id"] for t in auto]})

    if all_tids:
        mongo_db.people.delete_many({"tree_id": {"$in": all_tids}})
        mongo_db.relations.delete_many({"tree_id": {"$in": all_tids}})
        mongo_db.tree_members.delete_many({"tree_id": {"$in": all_tids}})
        mongo_db.trees.delete_many({"id": {"$in": all_tids}})
    # In case any tracked docs live outside the tracked trees (safety net)
    if person_ids:
        mongo_db.people.delete_many({"id": {"$in": person_ids}})
    if relation_ids:
        mongo_db.relations.delete_many({"id": {"$in": relation_ids}})
    mongo_db.tree_members.delete_many({"user_id": {"$in": user_ids}})
    mongo_db.user_sessions.delete_many({"session_token": {"$in": tokens}})
    mongo_db.users.delete_many({"user_id": {"$in": user_ids}})


# Shared state across the family-tree tests
STATE = {}


@pytest.fixture(scope="module")
def family_tree(mongo_db, users):
    """Build source tree A owned by user A with this shape:

              G  ---(spouse)--- G_sp
              |                  |
       +------+------+           |
       |             |           |
       C1--(sp)--C1_sp   C2      (C1_sp has NO parents in-tree)
       |
    +--+--+
    GC1   GC2

    Plus Z — an unrelated outsider person in the SAME tree (only relevant to
    the 'whole' scope).
    """
    # Create tree via API so tree_members/root are set up correctly.
    r = requests.post(f"{API}/trees", json={"name": NAME_TAG},
                      headers=auth(users["A"]["token"]))
    assert r.status_code == 200, r.text
    tree = r.json()
    tid = tree["id"]
    CREATED["tree_ids"].add(tid)

    # The API created a root person for user A already — grab & keep it as Z
    # so we don't have to delete it (whole-scope test accounts for it).
    root_docs = list(mongo_db.people.find({"tree_id": tid}, {"_id": 0}))
    assert len(root_docs) == 1, "tree should start with exactly 1 root person"
    z_id = root_docs[0]["id"]
    CREATED["person_ids"].add(z_id)

    # Insert grandparents, parents, spouses, grandchildren.
    g_id     = _insert_person(mongo_db, tid, "TEST_CLAIM_G",      "male",   created_by=users["A"]["id"])
    g_sp_id  = _insert_person(mongo_db, tid, "TEST_CLAIM_G_sp",   "female", created_by=users["A"]["id"])
    c1_id    = _insert_person(mongo_db, tid, "TEST_CLAIM_C1",     "male",   created_by=users["A"]["id"])
    c1_sp_id = _insert_person(mongo_db, tid, "TEST_CLAIM_C1_sp",  "female", created_by=users["A"]["id"])
    c2_id    = _insert_person(mongo_db, tid, "TEST_CLAIM_C2",     "female", created_by=users["A"]["id"])
    gc1_id   = _insert_person(mongo_db, tid, "TEST_CLAIM_GC1",    "male",   created_by=users["A"]["id"])
    gc2_id   = _insert_person(mongo_db, tid, "TEST_CLAIM_GC2",    "female", created_by=users["A"]["id"])

    # parent relations: person_id=parent, related_person_id=child
    _insert_relation(mongo_db, tid, g_id,    c1_id,  "parent")
    _insert_relation(mongo_db, tid, g_id,    c2_id,  "parent")
    _insert_relation(mongo_db, tid, g_sp_id, c1_id,  "parent")
    _insert_relation(mongo_db, tid, g_sp_id, c2_id,  "parent")
    _insert_relation(mongo_db, tid, c1_id,   gc1_id, "parent")
    _insert_relation(mongo_db, tid, c1_id,   gc2_id, "parent")
    # spouses
    _insert_relation(mongo_db, tid, g_id,  g_sp_id,  "spouse")
    _insert_relation(mongo_db, tid, c1_id, c1_sp_id, "spouse")

    STATE.update({
        "tid": tid,
        "z_id": z_id,   # the auto-root of the tree, unrelated to G's branch
        "g_id": g_id, "g_sp_id": g_sp_id,
        "c1_id": c1_id, "c1_sp_id": c1_sp_id, "c2_id": c2_id,
        "gc1_id": gc1_id, "gc2_id": gc2_id,
    })
    return STATE


# ---------------------------------------------------------------------------
# 1. scope = descendants
# ---------------------------------------------------------------------------
class TestScopeDescendants:
    def test_claim_descendants(self, users, family_tree, mongo_db):
        payload = {"person_id": STATE["g_id"], "scope": "descendants",
                   "name": "TEST_CLAIM_DescBranch"}
        r = requests.post(f"{API}/trees/{STATE['tid']}/claim-branch",
                          json=payload, headers=auth(users["A"]["token"]))
        assert r.status_code == 200, r.text
        d = r.json()

        # ---- response shape ----
        assert d["role"] == "admin"
        assert d["plan"] == "free"
        assert d["owner_id"] == users["A"]["id"]
        assert d["id"] != STATE["tid"]
        assert d["copied"] == d["person_count"]
        # G + G_sp + C1 + C1_sp + C2 + GC1 + GC2 = 7
        assert d["person_count"] == 7, f"expected 7 got {d['person_count']}"
        new_tid = d["id"]
        new_root_id = d["root_person_id"]
        assert new_root_id, "response missing root_person_id"
        CREATED["tree_ids"].add(new_tid)
        STATE["desc_tid"] = new_tid
        STATE["desc_root_new_id"] = new_root_id

        # ---- new tree has fresh ids; claimed person marked is_root ----
        new_people = list(mongo_db.people.find({"tree_id": new_tid}, {"_id": 0}))
        assert len(new_people) == 7
        new_ids = {p["id"] for p in new_people}
        old_ids = {STATE["g_id"], STATE["g_sp_id"], STATE["c1_id"],
                   STATE["c1_sp_id"], STATE["c2_id"], STATE["gc1_id"],
                   STATE["gc2_id"]}
        assert new_ids.isdisjoint(old_ids), "new tree should have fresh ids"
        names = {p["name"] for p in new_people}
        assert names == {
            "TEST_CLAIM_G", "TEST_CLAIM_G_sp", "TEST_CLAIM_C1",
            "TEST_CLAIM_C1_sp", "TEST_CLAIM_C2",
            "TEST_CLAIM_GC1", "TEST_CLAIM_GC2",
        }
        root_doc = next(p for p in new_people if p["id"] == new_root_id)
        assert root_doc["is_root"] is True
        assert root_doc["name"] == "TEST_CLAIM_G"
        # everyone else must NOT be root
        assert sum(1 for p in new_people if p.get("is_root")) == 1

    def test_source_tree_unchanged(self, mongo_db):
        # Source people still exactly what we inserted + the auto-root Z = 8
        src_people = list(mongo_db.people.find(
            {"tree_id": STATE["tid"], "deleted_at": None}, {"_id": 0}))
        assert len(src_people) == 8
        src_rels = list(mongo_db.relations.find(
            {"tree_id": STATE["tid"], "deleted_at": None}, {"_id": 0}))
        assert len(src_rels) == 8

    def test_relations_remapped_only_when_both_endpoints_in_set(self, mongo_db):
        new_tid = STATE["desc_tid"]
        new_rels = list(mongo_db.relations.find({"tree_id": new_tid}, {"_id": 0}))
        # All 8 source relations are between people all in the descendants
        # set, so all 8 should have been copied.
        assert len(new_rels) == 8
        old_ids = {STATE["g_id"], STATE["g_sp_id"], STATE["c1_id"],
                   STATE["c1_sp_id"], STATE["c2_id"], STATE["gc1_id"],
                   STATE["gc2_id"]}
        for r in new_rels:
            assert r["tree_id"] == new_tid
            assert r["person_id"] not in old_ids
            assert r["related_person_id"] not in old_ids

    def test_caller_is_admin_of_new_tree(self, users, mongo_db):
        m = mongo_db.tree_members.find_one(
            {"tree_id": STATE["desc_tid"], "user_id": users["A"]["id"]},
            {"_id": 0})
        assert m is not None
        assert m["role"] == "admin"

    def test_new_tree_visible_in_get_trees(self, users):
        r = requests.get(f"{API}/trees", headers=auth(users["A"]["token"]))
        assert r.status_code == 200
        ids = {t["id"] for t in r.json()}
        assert STATE["desc_tid"] in ids

    def test_get_tree_returns_copied_people(self, users):
        r = requests.get(f"{API}/tree", params={"tree_id": STATE["desc_tid"]},
                         headers=auth(users["A"]["token"]))
        assert r.status_code == 200, r.text
        d = r.json()
        # /api/tree returns {people:[...], relations:[...]} or similar; we
        # tolerate either wrapper — inspect keys defensively
        people = d.get("people") if isinstance(d, dict) else d
        assert people is not None
        assert len(people) == 7


# ---------------------------------------------------------------------------
# 2. scope = children
# ---------------------------------------------------------------------------
class TestScopeChildren:
    def test_claim_children(self, users, family_tree, mongo_db):
        r = requests.post(
            f"{API}/trees/{STATE['tid']}/claim-branch",
            json={"person_id": STATE["g_id"], "scope": "children",
                  "name": "TEST_CLAIM_ChildBranch"},
            headers=auth(users["A"]["token"]))
        assert r.status_code == 200, r.text
        d = r.json()
        # G + C1 + C2 + G_sp (spouse of G) + C1_sp (spouse of C1) = 5
        # Grandchildren must NOT be included.
        assert d["person_count"] == 5, f"expected 5 got {d['person_count']}"
        STATE["child_tid"] = d["id"]
        CREATED["tree_ids"].add(d["id"])

        names = {p["name"] for p in mongo_db.people.find(
            {"tree_id": d["id"]}, {"_id": 0, "name": 1})}
        assert names == {"TEST_CLAIM_G", "TEST_CLAIM_G_sp",
                         "TEST_CLAIM_C1", "TEST_CLAIM_C1_sp", "TEST_CLAIM_C2"}
        assert "TEST_CLAIM_GC1" not in names
        assert "TEST_CLAIM_GC2" not in names

    def test_children_scope_relations_correct(self, mongo_db):
        new_tid = STATE["child_tid"]
        new_rels = list(mongo_db.relations.find({"tree_id": new_tid}, {"_id": 0}))
        # Kept: G-C1, G-C2, G_sp-C1, G_sp-C2, G-G_sp(spouse), C1-C1_sp(spouse)
        # Dropped: C1->GC1, C1->GC2  (endpoints not in copied set)
        types = sorted(r["relation_type"] for r in new_rels)
        assert types.count("parent") == 4
        assert types.count("spouse") == 2
        assert len(new_rels) == 6


# ---------------------------------------------------------------------------
# 3. scope = whole
# ---------------------------------------------------------------------------
class TestScopeWhole:
    def test_claim_whole_duplicates_full_tree(self, users, family_tree, mongo_db):
        r = requests.post(
            f"{API}/trees/{STATE['tid']}/claim-branch",
            json={"person_id": STATE["g_id"], "scope": "whole",
                  "name": "TEST_CLAIM_WholeBranch"},
            headers=auth(users["A"]["token"]))
        assert r.status_code == 200, r.text
        d = r.json()
        # 7 family + 1 auto-root Z = 8
        assert d["person_count"] == 8, f"expected 8 got {d['person_count']}"
        new_tid = d["id"]
        CREATED["tree_ids"].add(new_tid)

        new_people = list(mongo_db.people.find({"tree_id": new_tid}, {"_id": 0}))
        assert len(new_people) == 8

        # New ids only
        old_ids = {STATE["g_id"], STATE["g_sp_id"], STATE["c1_id"],
                   STATE["c1_sp_id"], STATE["c2_id"], STATE["gc1_id"],
                   STATE["gc2_id"], STATE["z_id"]}
        new_ids = {p["id"] for p in new_people}
        assert new_ids.isdisjoint(old_ids)

        # Claimed person is the only root
        roots = [p for p in new_people if p.get("is_root")]
        assert len(roots) == 1
        assert roots[0]["name"] == "TEST_CLAIM_G"
        assert roots[0]["id"] == d["root_person_id"]

        # All 8 original relations copied (endpoints of every relation are in set)
        new_rels = list(mongo_db.relations.find({"tree_id": new_tid}, {"_id": 0}))
        assert len(new_rels) == 8
        for r_ in new_rels:
            assert r_["person_id"] not in old_ids
            assert r_["related_person_id"] not in old_ids


# ---------------------------------------------------------------------------
# 4. Error cases
# ---------------------------------------------------------------------------
class TestClaimErrors:
    def test_unknown_person_id_returns_404(self, users, family_tree):
        r = requests.post(
            f"{API}/trees/{STATE['tid']}/claim-branch",
            json={"person_id": f"nope_{uuid.uuid4().hex}",
                  "scope": "descendants"},
            headers=auth(users["A"]["token"]))
        assert r.status_code == 404, r.text

    def test_non_member_gets_403(self, users, family_tree):
        r = requests.post(
            f"{API}/trees/{STATE['tid']}/claim-branch",
            json={"person_id": STATE["g_id"], "scope": "descendants"},
            headers=auth(users["B"]["token"]))
        assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# 5. Regression: Free plan 50-person limit on /people/add-relative
# ---------------------------------------------------------------------------
class TestFreePlanLimit:
    def test_add_relative_returns_402_limit_reached(self, users, mongo_db):
        # Create a dedicated tree via API (already free), then bulk-insert
        # people directly to reach exactly 50 (root counts as 1 -> need 49
        # more).
        r = requests.post(f"{API}/trees",
                          json={"name": f"TEST_CLAIM_LIMIT_{uuid.uuid4().hex[:6]}"},
                          headers=auth(users["A"]["token"]))
        assert r.status_code == 200
        tid = r.json()["id"]
        CREATED["tree_ids"].add(tid)

        root_doc = mongo_db.people.find_one({"tree_id": tid}, {"_id": 0})
        assert root_doc is not None
        CREATED["person_ids"].add(root_doc["id"])
        focus_id = root_doc["id"]

        # Fill to 50
        docs = []
        for i in range(49):
            pid = str(uuid.uuid4())
            CREATED["person_ids"].add(pid)
            docs.append({
                "id": pid, "tree_id": tid, "name": f"TEST_CLAIM_FILL_{i}",
                "email": None, "gender": None, "birth_date": None,
                "birth_place": None, "death_date": None, "photo_url": None,
                "job": None, "is_adopted": False, "notes": None,
                "is_alive": True, "is_root": False,
                "created_by": users["A"]["id"], "created_at": now_utc(),
                "deleted_at": None,
            })
        mongo_db.people.insert_many(docs)
        assert mongo_db.people.count_documents(
            {"tree_id": tid, "deleted_at": None}) == 50

        # Attempt to add another → 402
        payload = {
            "focus_id": focus_id,
            "direction": "child",
            "person": {"name": "TEST_CLAIM_OVERFLOW", "gender": "male"},
        }
        rr = requests.post(f"{API}/people/add-relative",
                           params={"tree_id": tid},
                           json=payload,
                           headers=auth(users["A"]["token"]))
        assert rr.status_code == 402, rr.text
        body = rr.json()
        assert body.get("detail", "").startswith("LIMIT_REACHED"), body
