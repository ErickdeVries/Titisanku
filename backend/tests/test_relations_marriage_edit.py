"""KETURUNANKU iteration-5 backend tests.

Focus: brand-new endpoints & behaviours from this iteration.

1. PUT /api/relations/{rel_id}: update marriage_date / divorce_date / is_divorced
   on a spouse (or 'divorced') relation.
   - is_divorced=True  -> relation_type='divorced' + divorce_date saved
   - is_divorced=False -> relation_type='spouse'   + divorce_date cleared to null
   - 400 when target relation is NOT spouse/divorced (e.g. parent)
   - 404 when unknown relation id
   - 403 for viewer role, 200 for admin/editor

2. POST /api/people/add-relative direction='child' AUTO-LINK:
   - focus has EXACTLY 1 spouse   -> child gets 2 parent relations
   - focus has 0 spouses          -> child gets 1 parent relation
   - focus has 2+ spouses         -> child gets 1 parent relation (no auto-link, ambiguous)

3. Regression: duplicate father/mother guard still returns 400
   with detail containing 'Ayah sudah ada' / 'Ibu sudah ada'.

4. Regression: DELETE /api/relations/{rel_id} still works.

Cleanup: session-scoped fixture; only docs created by this run are removed.
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


CREATED = {"user_ids": set(), "session_tokens": set(), "tree_ids": set()}


@pytest.fixture(scope="session")
def mongo_db():
    return MongoClient(MONGO_URL)[DB_NAME]


def _seed_user(db, name):
    uid = f"user_{uuid.uuid4().hex[:12]}"
    email = f"TEST_REL_{uuid.uuid4().hex[:8]}@example.com"
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


@pytest.fixture(scope="session")
def ctx(mongo_db):
    """Seed: 1 admin, 1 editor, 1 viewer. Admin creates a tree via API.
    Members: admin (auto), editor (added), viewer (added).
    Root person exists automatically."""
    admin_id, admin_tok, _ = _seed_user(mongo_db, "TEST_REL_Admin")
    editor_id, editor_tok, _ = _seed_user(mongo_db, "TEST_REL_Editor")
    viewer_id, viewer_tok, _ = _seed_user(mongo_db, "TEST_REL_Viewer")

    # Admin creates a tree via API
    r = requests.post(f"{API}/trees", json={"name": "TEST_REL_Tree"},
                      headers=auth(admin_tok))
    assert r.status_code == 200, r.text
    tree = r.json()
    tid = tree["id"]
    CREATED["tree_ids"].add(tid)
    root_id = tree.get("root_person_id")
    # If create_tree response doesn't include root_person_id explicitly, fetch
    if not root_id:
        gt = requests.get(f"{API}/tree", params={"tree_id": tid},
                          headers=auth(admin_tok)).json()
        root_id = gt["root_id"]
    # Add editor & viewer as tree_members directly (simulating post-invite)
    mongo_db.tree_members.insert_one({
        "id": str(uuid.uuid4()), "tree_id": tid, "user_id": editor_id,
        "role": "editor", "joined_at": now_utc(),
    })
    mongo_db.tree_members.insert_one({
        "id": str(uuid.uuid4()), "tree_id": tid, "user_id": viewer_id,
        "role": "viewer", "joined_at": now_utc(),
    })

    yield {
        "tid": tid,
        "root_id": root_id,
        "admin": {"id": admin_id, "token": admin_tok},
        "editor": {"id": editor_id, "token": editor_tok},
        "viewer": {"id": viewer_id, "token": viewer_tok},
    }

    # -------- Teardown: only docs we created --------
    tree_ids = list(CREATED["tree_ids"])
    user_ids = list(CREATED["user_ids"])
    tokens = list(CREATED["session_tokens"])
    if tree_ids:
        mongo_db.trees.delete_many({"id": {"$in": tree_ids}})
        mongo_db.tree_members.delete_many({"tree_id": {"$in": tree_ids}})
        mongo_db.people.delete_many({"tree_id": {"$in": tree_ids}})
        mongo_db.relations.delete_many({"tree_id": {"$in": tree_ids}})
        mongo_db.family_chat.delete_many({"tree_id": {"$in": tree_ids}})
        mongo_db.person_notes.delete_many({"tree_id": {"$in": tree_ids}})
        mongo_db.app_notifications.delete_many({"tree_id": {"$in": tree_ids}})
        mongo_db.chat_typing.delete_many({"room_id": {"$in": tree_ids}})
    mongo_db.tree_members.delete_many({"user_id": {"$in": user_ids}})
    mongo_db.user_sessions.delete_many({"session_token": {"$in": tokens}})
    mongo_db.users.delete_many({"user_id": {"$in": user_ids}})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def add_rel(ctx, direction, name, focus_id=None, **kwargs):
    payload = {
        "focus_id": focus_id or ctx["root_id"],
        "direction": direction,
        "person": {"name": name},
    }
    payload.update({k: v for k, v in kwargs.items() if k in
                    ("marriage_date", "divorce_date", "is_divorced")})
    if "gender" in kwargs:
        payload["person"]["gender"] = kwargs["gender"]
    r = requests.post(f"{API}/people/add-relative",
                      params={"tree_id": ctx["tid"]},
                      json=payload,
                      headers=auth(ctx["admin"]["token"]))
    assert r.status_code == 200, r.text
    return r.json()  # {"person": {...}, "relation_id": "..."}


# ---------------------------------------------------------------------------
# 1. PUT /api/relations/{rel_id}
# ---------------------------------------------------------------------------
class TestUpdateRelation:
    def test_editor_can_update_spouse_marriage_date(self, ctx):
        # Create a spouse relation
        res = add_rel(ctx, "spouse", "TEST_REL_Spouse1",
                      marriage_date="01/01/2020")
        rel_id = res["relation_id"]

        r = requests.put(
            f"{API}/relations/{rel_id}",
            params={"tree_id": ctx["tid"]},
            json={"marriage_date": "15/06/2021", "is_divorced": False},
            headers=auth(ctx["editor"]["token"]),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["marriage_date"] == "15/06/2021"
        assert data["relation_type"] == "spouse"
        assert data["divorce_date"] is None

    def test_set_divorced_true_sets_type_and_date(self, ctx):
        res = add_rel(ctx, "spouse", "TEST_REL_Spouse2",
                      marriage_date="10/10/2010")
        rel_id = res["relation_id"]

        r = requests.put(
            f"{API}/relations/{rel_id}",
            params={"tree_id": ctx["tid"]},
            json={
                "marriage_date": "10/10/2010",
                "divorce_date": "20/12/2022",
                "is_divorced": True,
            },
            headers=auth(ctx["admin"]["token"]),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["relation_type"] == "divorced"
        assert data["divorce_date"] == "20/12/2022"
        assert data["marriage_date"] == "10/10/2010"

    def test_flip_divorced_back_to_spouse_clears_divorce_date(self, ctx):
        # Start from a divorced relation
        res = add_rel(ctx, "spouse", "TEST_REL_Spouse3",
                      marriage_date="01/02/2003",
                      divorce_date="04/05/2006",
                      is_divorced=True)
        rel_id = res["relation_id"]
        # Verify it's divorced first
        r_pre = requests.put(
            f"{API}/relations/{rel_id}",
            params={"tree_id": ctx["tid"]},
            json={"marriage_date": "01/02/2003",
                  "divorce_date": "04/05/2006",
                  "is_divorced": True},
            headers=auth(ctx["admin"]["token"]),
        )
        assert r_pre.json()["relation_type"] == "divorced"
        # Now flip back to spouse
        r = requests.put(
            f"{API}/relations/{rel_id}",
            params={"tree_id": ctx["tid"]},
            json={"marriage_date": "01/02/2003", "is_divorced": False},
            headers=auth(ctx["admin"]["token"]),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["relation_type"] == "spouse"
        assert data["divorce_date"] is None

    def test_viewer_forbidden(self, ctx):
        res = add_rel(ctx, "spouse", "TEST_REL_Spouse4",
                      marriage_date="01/01/2000")
        rel_id = res["relation_id"]
        r = requests.put(
            f"{API}/relations/{rel_id}",
            params={"tree_id": ctx["tid"]},
            json={"marriage_date": "02/02/2002", "is_divorced": False},
            headers=auth(ctx["viewer"]["token"]),
        )
        assert r.status_code == 403, r.text

    def test_400_when_relation_not_spouse(self, ctx, mongo_db):
        # Add a father -> creates a parent relation
        # Note: this root already may have a father if run after other tests,
        # so we spawn a fresh person branch: add a new child, then add a father to that child.
        child = add_rel(ctx, "child", "TEST_REL_ChildForParent")
        father = add_rel(ctx, "father", "TEST_REL_FatherX",
                         focus_id=child["person"]["id"])
        parent_rel_id = father["relation_id"]

        r = requests.put(
            f"{API}/relations/{parent_rel_id}",
            params={"tree_id": ctx["tid"]},
            json={"marriage_date": "01/01/2000", "is_divorced": False},
            headers=auth(ctx["admin"]["token"]),
        )
        assert r.status_code == 400, r.text
        assert "spouse" in r.text.lower()

    def test_404_unknown_relation(self, ctx):
        r = requests.put(
            f"{API}/relations/does-not-exist",
            params={"tree_id": ctx["tid"]},
            json={"marriage_date": "01/01/2000", "is_divorced": False},
            headers=auth(ctx["admin"]["token"]),
        )
        assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# 2. add-relative child AUTO-LINK to focus's single spouse
# ---------------------------------------------------------------------------
class TestChildAutoLink:
    def _fetch_relations(self, ctx):
        return requests.get(f"{API}/tree", params={"tree_id": ctx["tid"]},
                            headers=auth(ctx["admin"]["token"])).json()["relations"]

    def _parents_of(self, rels, child_id):
        """Return set of person_ids that have a parent/adopted_child relation
        pointing TO child_id."""
        parents = set()
        for r in rels:
            if r.get("deleted_at"):
                continue
            if r["relation_type"] in ("parent", "adopted_child") and \
               r["related_person_id"] == child_id:
                parents.add(r["person_id"])
        return parents

    def test_child_auto_links_to_single_spouse(self, ctx):
        # Create father with exactly ONE spouse (mother), then add child.
        father = add_rel(ctx, "child", "TEST_REL_Father_AL")  # child of root
        father_id = father["person"]["id"]
        # Add mother as spouse of father
        mother = add_rel(ctx, "spouse", "TEST_REL_Mother_AL",
                         focus_id=father_id, marriage_date="01/01/2000")
        mother_id = mother["person"]["id"]
        # Add child to father (focus)
        child = add_rel(ctx, "child", "TEST_REL_Child_AL",
                        focus_id=father_id)
        child_id = child["person"]["id"]

        rels = self._fetch_relations(ctx)
        parents = self._parents_of(rels, child_id)
        assert father_id in parents, f"Father missing from parents of child: {parents}"
        assert mother_id in parents, f"Mother NOT auto-linked (parents={parents})"
        assert len(parents) == 2, f"Expected 2 parents, got {len(parents)}: {parents}"

    def test_child_zero_spouse_only_one_parent(self, ctx):
        # Create a bachelor person, then add child
        bachelor = add_rel(ctx, "child", "TEST_REL_Bachelor")
        bachelor_id = bachelor["person"]["id"]
        # No spouse added
        child = add_rel(ctx, "child", "TEST_REL_Child_Bach",
                        focus_id=bachelor_id)
        child_id = child["person"]["id"]

        rels = self._fetch_relations(ctx)
        parents = self._parents_of(rels, child_id)
        assert parents == {bachelor_id}, \
            f"Bachelor should be only parent, got {parents}"

    def test_child_two_spouses_no_auto_link(self, ctx):
        # Create person with TWO spouses -> auto-link ambiguous, child = 1 parent
        poly = add_rel(ctx, "child", "TEST_REL_Poly")
        poly_id = poly["person"]["id"]
        add_rel(ctx, "spouse", "TEST_REL_Poly_Spouse1",
                focus_id=poly_id, marriage_date="01/01/2001")
        add_rel(ctx, "spouse", "TEST_REL_Poly_Spouse2",
                focus_id=poly_id, marriage_date="01/01/2005",
                divorce_date="01/01/2010", is_divorced=True)
        child = add_rel(ctx, "child", "TEST_REL_Poly_Child",
                        focus_id=poly_id)
        child_id = child["person"]["id"]

        rels = self._fetch_relations(ctx)
        parents = self._parents_of(rels, child_id)
        assert parents == {poly_id}, \
            f"With 2 spouses, only focus should be parent, got {parents}"


# ---------------------------------------------------------------------------
# 3. Regression: duplicate father/mother guard
# ---------------------------------------------------------------------------
class TestDuplicateParentGuard:
    def test_duplicate_father_returns_400(self, ctx):
        target = add_rel(ctx, "child", "TEST_REL_DupF_Child")
        target_id = target["person"]["id"]
        add_rel(ctx, "father", "TEST_REL_DupF_Father1", focus_id=target_id)
        # Attempt to add another father
        r = requests.post(
            f"{API}/people/add-relative",
            params={"tree_id": ctx["tid"]},
            json={"focus_id": target_id, "direction": "father",
                  "person": {"name": "TEST_REL_DupF_Father2"}},
            headers=auth(ctx["admin"]["token"]),
        )
        assert r.status_code == 400, r.text
        assert "Ayah sudah ada" in r.text

    def test_duplicate_mother_returns_400(self, ctx):
        target = add_rel(ctx, "child", "TEST_REL_DupM_Child")
        target_id = target["person"]["id"]
        add_rel(ctx, "mother", "TEST_REL_DupM_Mother1", focus_id=target_id)
        r = requests.post(
            f"{API}/people/add-relative",
            params={"tree_id": ctx["tid"]},
            json={"focus_id": target_id, "direction": "mother",
                  "person": {"name": "TEST_REL_DupM_Mother2"}},
            headers=auth(ctx["admin"]["token"]),
        )
        assert r.status_code == 400, r.text
        assert "Ibu sudah ada" in r.text


# ---------------------------------------------------------------------------
# 4. Regression: DELETE /api/relations/{rel_id}
# ---------------------------------------------------------------------------
class TestDeleteRelation:
    def test_admin_can_delete_relation(self, ctx):
        res = add_rel(ctx, "spouse", "TEST_REL_ToDelete",
                      marriage_date="01/01/2000")
        rel_id = res["relation_id"]
        r = requests.delete(f"{API}/relations/{rel_id}",
                            params={"tree_id": ctx["tid"]},
                            headers=auth(ctx["admin"]["token"]))
        assert r.status_code == 200, r.text
        # 404 on second delete (already soft-deleted)
        r2 = requests.delete(f"{API}/relations/{rel_id}",
                             params={"tree_id": ctx["tid"]},
                             headers=auth(ctx["admin"]["token"]))
        assert r2.status_code == 404

    def test_viewer_cannot_delete_relation(self, ctx):
        res = add_rel(ctx, "spouse", "TEST_REL_ViewerDel",
                      marriage_date="01/01/2000")
        rel_id = res["relation_id"]
        r = requests.delete(f"{API}/relations/{rel_id}",
                            params={"tree_id": ctx["tid"]},
                            headers=auth(ctx["viewer"]["token"]))
        assert r.status_code == 403, r.text
