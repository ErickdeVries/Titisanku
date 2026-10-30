"""Card privacy tests — per-field redaction of person records.

Rules under test (see `redact_person` in server.py):
- The record's creator (created_by) always sees everything.
- Tree admins and superadmins always see everything.
- Any other member of the tree only gets the fields the owner left visible;
  hidden sensitive fields come back as None and are listed in `redacted_fields`.
- The privacy setting must SURVIVE a normal person edit (PUT /people/{id}),
  even when the client payload omits `privacy` entirely.

Cleanup: ONLY docs created by this run are removed. Never delete_many({}).
All docs use the TEST_ prefix so they are easy to spot (and wipe safely).
"""
import os
import secrets
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

BASE_URL = (
    os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or os.environ.get("EXPO_BACKEND_URL")
    or "http://localhost:8001"
).rstrip("/")
API = f"{BASE_URL}/api"

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

SENSITIVE = ["birth_date", "birth_place", "job", "death_date", "notes"]


def now_utc():
    return datetime.now(timezone.utc)


def auth(token):
    return {"Authorization": f"Bearer {token}"}


CREATED = {"user_ids": set(), "session_tokens": set(), "tree_ids": set()}


@pytest.fixture(scope="session")
def mongo_db():
    return MongoClient(MONGO_URL)[DB_NAME]


def _seed_user(db, name="TEST_PRIV_User"):
    uid = f"user_{uuid.uuid4().hex[:12]}"
    token = secrets.token_hex(16)
    db.users.insert_one({
        "user_id": uid,
        "email": f"TEST_PRIV_{uuid.uuid4().hex[:8]}@example.com",
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
    return uid, token


@pytest.fixture(scope="session")
def users(mongo_db):
    """Three synthetic users with no tree membership at start."""
    a_id, a_tok = _seed_user(mongo_db, "TEST_PRIV_Owner")
    b_id, b_tok = _seed_user(mongo_db, "TEST_PRIV_Other")
    c_id, c_tok = _seed_user(mongo_db, "TEST_PRIV_Other2")
    yield {
        "owner": {"id": a_id, "token": a_tok},
        "other": {"id": b_id, "token": b_tok},
        "other2": {"id": c_id, "token": c_tok},
    }
    tree_ids = list(CREATED["tree_ids"])
    user_ids = list(CREATED["user_ids"])
    tokens = list(CREATED["session_tokens"])

    if tree_ids:
        # Auto-created trees owned by our users (cleanup by owner below too).
        for coll in ("trees", "tree_members", "people", "relations",
                     "family_chat", "person_notes", "app_notifications"):
            key = "id" if coll == "trees" else "tree_id"
            mongo_db[coll].delete_many({key: {"$in": tree_ids}})
        mongo_db["family_chat"].delete_many({"room_id": {"$in": tree_ids}})
        mongo_db["chat_typing"].delete_many({"room_id": {"$in": tree_ids}})

    auto = [t["id"] for t in mongo_db.trees.find({"owner_id": {"$in": user_ids}}, {"id": 1})]
    if auto:
        for coll in ("trees", "tree_members", "people", "relations",
                     "family_chat", "person_notes", "app_notifications"):
            key = "id" if coll == "trees" else "tree_id"
            mongo_db[coll].delete_many({key: {"$in": auto}})

    mongo_db.tree_members.delete_many({"user_id": {"$in": user_ids}})
    mongo_db.user_sessions.delete_many({"session_token": {"$in": tokens}})
    mongo_db.users.delete_many({"user_id": {"$in": user_ids}})


@pytest.fixture(scope="session")
def tree(users):
    """Owner creates a tree (becomes admin). Returns tree_id + owner person id."""
    r = requests.post(
        f"{API}/trees",
        json={"name": f"TEST_PRIV_Tree_{uuid.uuid4().hex[:6]}"},
        headers=auth(users["owner"]["token"]),
        timeout=20,
    )
    assert r.status_code in (200, 201), r.text
    data = r.json()
    tree_id = data.get("id") or data.get("tree", {}).get("id") or data.get("tree_id")
    assert tree_id, f"no tree id in response: {data}"
    CREATED["tree_ids"].add(tree_id)

    # The creator's root person (auto-created) — fill in sensitive fields.
    g = requests.get(f"{API}/tree", params={"tree_id": tree_id},
                     headers=auth(users["owner"]["token"]), timeout=20)
    assert g.status_code == 200, g.text
    people = g.json()["people"]
    assert people, "owner tree has no root person"
    person_id = people[0]["id"]

    requests.put(
        f"{API}/people/{person_id}",
        params={"tree_id": tree_id},
        json={
            "name": "TEST_PRIV_Subject",
            "birth_date": "1950-01-02",
            "birth_place": "Bandung",
            "job": "Guru",
            "notes": "catatan rahasia",
            "is_alive": True,
        },
        headers=auth(users["owner"]["token"]),
        timeout=20,
    )
    return {"tree_id": tree_id, "person_id": person_id}


@pytest.fixture(scope="session")
def joined(mongo_db, users, tree):
    """Add `other` + `other2` as viewers of the owner's tree."""
    for key in ("other", "other2"):
        mongo_db.tree_members.insert_one({
            "tree_id": tree["tree_id"],
            "user_id": users[key]["id"],
            "name": f"TEST_PRIV_{key}",
            "email": None,
            "role": "viewer",
            "joined_at": now_utc(),
        })
    return tree


class TestPrivacyRedaction:
    def test_owner_sees_all_fields(self, users, tree):
        r = requests.get(f"{API}/people/{tree['person_id']}", params={"tree_id": tree["tree_id"]},
                         headers=auth(users["owner"]["token"]), timeout=20)
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["birth_place"] == "Bandung"
        assert p["job"] == "Guru"
        assert not p.get("redacted_fields")

    def test_owner_can_hide_fields(self, users, tree):
        r = requests.put(
            f"{API}/people/{tree['person_id']}/privacy",
            params={"tree_id": tree["tree_id"]},
            json={"birth_place": True, "job": True, "notes": True},
            headers=auth(users["owner"]["token"]), timeout=20,
        )
        assert r.status_code == 200, r.text
        assert r.json()["privacy"]["birth_place"]["hidden"] is True

    def test_other_member_gets_redacted(self, users, joined):
        tid, pid = joined["tree_id"], joined["person_id"]
        r = requests.get(f"{API}/people/{pid}", params={"tree_id": tid},
                         headers=auth(users["other"]["token"]), timeout=20)
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["birth_place"] is None, "hidden field leaked via GET /people/{id}"
        assert p["job"] is None, "hidden field leaked via GET /people/{id}"
        assert p["notes"] is None, "hidden field leaked via GET /people/{id}"
        assert set(p.get("redacted_fields", [])) >= {"birth_place", "job", "notes"}
        # Visible field must still come through.
        assert p["birth_date"] == "1950-01-02"

    def test_other_member_tree_list_redacted(self, users, joined):
        r = requests.get(f"{API}/tree", params={"tree_id": joined["tree_id"]},
                         headers=auth(users["other"]["token"]), timeout=20)
        assert r.status_code == 200, r.text
        p = next(x for x in r.json()["people"] if x["id"] == joined["person_id"])
        assert p["job"] is None, "hidden field leaked via GET /tree"
        assert "job" in p.get("redacted_fields", [])

    def test_admin_still_sees_everything(self, users, joined):
        # The owner is the tree admin.
        r = requests.get(f"{API}/tree", params={"tree_id": joined["tree_id"]},
                         headers=auth(users["owner"]["token"]), timeout=20)
        p = next(x for x in r.json()["people"] if x["id"] == joined["person_id"])
        assert p["job"] == "Guru"
        assert p["birth_place"] == "Bandung"

    def test_privacy_survives_normal_edit(self, users, joined):
        """REGRESSION: editing a person must not silently wipe the privacy map.

        The app's edit form (frontend save()) sends no `privacy` key. The
        backend used to `$set` the whole model_dump(), turning `privacy` into
        None and un-hiding fields for every other member.
        """
        tid, pid = joined["tree_id"], joined["person_id"]
        # Set the privacy map explicitly instead of relying on another test
        # having run first (pytest does not guarantee test ordering).
        pr = requests.put(
            f"{API}/people/{pid}/privacy",
            params={"tree_id": tid},
            json={"birth_place": True, "job": True, "notes": True},
            headers=auth(users["owner"]["token"]), timeout=20,
        )
        assert pr.status_code == 200, pr.text

        r = requests.put(
            f"{API}/people/{pid}",
            params={"tree_id": tid},
            json={"name": "TEST_PRIV_Subject", "birth_date": "1950-01-02",
                  "job": "Guru", "birth_place": "Bandung", "notes": "catatan rahasia"},
            headers=auth(users["owner"]["token"]), timeout=20,
        )
        assert r.status_code == 200, r.text

        # Owner must still have the privacy map intact...
        r2 = requests.get(f"{API}/people/{pid}", params={"tree_id": tid},
                          headers=auth(users["owner"]["token"]), timeout=20)
        assert (r2.json().get("privacy") or {}).get("job", {}).get("hidden") is True, \
            "privacy was wiped by a normal edit"

        # ...and other members must still see it redacted.
        r3 = requests.get(f"{API}/people/{pid}", params={"tree_id": tid},
                          headers=auth(users["other"]["token"]), timeout=20)
        assert r3.json()["job"] is None, \
            "privacy wiped by edit -> hidden field became visible to other members"

    def test_non_owner_cannot_change_privacy(self, users, joined):
        r = requests.put(
            f"{API}/people/{joined['person_id']}/privacy",
            params={"tree_id": joined["tree_id"]},
            json={"job": False},
            headers=auth(users["other"]["token"]), timeout=20,
        )
        assert r.status_code == 403, f"viewer was able to change privacy: {r.status_code} {r.text}"

    def test_owner_can_unhide(self, users, joined):
        r = requests.put(
            f"{API}/people/{joined['person_id']}/privacy",
            params={"tree_id": joined["tree_id"]},
            json={"job": False, "birth_place": False, "notes": False},
            headers=auth(users["owner"]["token"]), timeout=20,
        )
        assert r.status_code == 200, r.text
        r2 = requests.get(f"{API}/people/{joined['person_id']}", params={"tree_id": joined["tree_id"]},
                          headers=auth(users["other"]["token"]), timeout=20)
        assert r2.json()["job"] == "Guru", "unhide did not take effect"


class TestSelectiveDisclosure:
    """A hidden field can be opened to specific members via an allow-list."""

    def _hide_from_all_but(self, users, joined, allow_ids):
        r = requests.put(
            f"{API}/people/{joined['person_id']}/privacy",
            params={"tree_id": joined["tree_id"]},
            json={"job": {"hidden": True, "allow": allow_ids}},
            headers=auth(users["owner"]["token"]), timeout=20,
        )
        assert r.status_code == 200, r.text
        return r.json()

    def _job_as(self, users, joined, who):
        r = requests.get(
            f"{API}/people/{joined['person_id']}",
            params={"tree_id": joined["tree_id"]},
            headers=auth(users[who]["token"]), timeout=20,
        )
        assert r.status_code == 200, r.text
        return r.json()["job"]

    def test_allowlisted_member_sees_field(self, users, joined):
        self._hide_from_all_but(users, joined, [users["other"]["id"]])
        assert self._job_as(users, joined, "other") == "Guru", \
            "allow-listed member should see the field"
        assert self._job_as(users, joined, "other2") is None, \
            "non-allow-listed member must still be redacted"

    def test_owner_still_sees_field(self, users, joined):
        self._hide_from_all_but(users, joined, [users["other"]["id"]])
        assert self._job_as(users, joined, "owner") == "Guru"

    def test_removing_from_allow_list_rehides(self, users, joined):
        self._hide_from_all_but(users, joined, [users["other"]["id"]])
        assert self._job_as(users, joined, "other") == "Guru"
        self._hide_from_all_but(users, joined, [])
        assert self._job_as(users, joined, "other") is None

    def test_non_member_cannot_be_allowlisted(self, users, joined, mongo_db):
        """A user outside the tree must never be granted access."""
        stranger = _seed_user(mongo_db, "TEST_PRIV_Stranger")
        out = self._hide_from_all_but(users, joined, [stranger[0]])
        assert out["privacy"]["job"]["allow"] == [], \
            "allow-list must only contain members of the tree"

    def test_privacy_map_is_normalised_for_everyone(self, users, joined):
        """Clients always get the object shape, never legacy bare booleans."""
        r = requests.put(
            f"{API}/people/{joined['person_id']}/privacy",
            params={"tree_id": joined["tree_id"]},
            json={"notes": True},
            headers=auth(users["owner"]["token"]), timeout=20,
        )
        assert r.status_code == 200, r.text
        for who in ("owner", "other"):
            g = requests.get(
                f"{API}/people/{joined['person_id']}",
                params={"tree_id": joined["tree_id"]},
                headers=auth(users[who]["token"]), timeout=20,
            ).json()
            assert isinstance(g["privacy"]["notes"], dict), \
                f"{who} received a legacy boolean privacy entry: {g['privacy']}"
            assert g["privacy"]["notes"]["hidden"] is True

