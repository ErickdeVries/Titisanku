"""KETURUNANKU backend tests — Iteration 9.

New feature coverage:
1. DELETE /api/trees/{tid} — OWNER only; full cascade cleanup of tree +
   tree_members + people + relations + chat_rooms + family_chat + chat_mutes.
   - Non-owner tree member -> 403; unknown tree -> 404.
2. PUT /api/chat/rooms/{room_id} {name, member_ids} — group rename + REPLACE
   members. Creator + caller always retained; invalid ids filtered.
   Only creator OR tree admin/editor participant may update (others 403).
   404 if the room is not a group / doesn't exist.
3. POST /api/chat/rooms/{room_id}/mute {muted:true/false} — upsert / delete a
   chat_mutes doc for the caller+room. Works for family (room_id==tree_id),
   group, and direct.
4. MUTE effect on notifications: muted user does NOT get app_notifications
   docs when a message is sent to that room (other participants still do).
5. GET /api/chat/rooms — each room includes 'muted' boolean.
   GET /api/chat?room_id= returns 'muted' and 'can_manage'.
6. Regression — sending/reading messages, unread counts, deceased-sender 403
   still work after these changes.

CRITICAL: shared preview DB contains real data. We ONLY create + delete our
own synthetic docs (TEST_ITER9_ prefix + tracked ids). Never delete_many({}).
DELETE-tree tests target trees WE seed only.
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

PREFIX = "TEST_ITER9"


def now_utc():
    return datetime.now(timezone.utc)


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# All ids we touch — cleaned up on module teardown. Never delete_many({}).
CREATED = {
    "user_ids": set(),
    "session_tokens": set(),
    "tree_ids": set(),
    "person_ids": set(),
    "chat_room_ids": set(),
}


@pytest.fixture(scope="module")
def db():
    c = MongoClient(MONGO_URL)
    return c[DB_NAME]


def _seed_user(db, label, email_hint=None):
    uid = f"user_{uuid.uuid4().hex[:12]}"
    email = email_hint or f"{PREFIX}_{label}_{uuid.uuid4().hex[:6]}@example.com"
    token = secrets.token_hex(16)
    db.users.insert_one({
        "user_id": uid,
        "email": email,
        "name": f"{PREFIX}_{label}_{uid[-4:]}",
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


def _seed_tree(db, owner_id, name):
    tid = f"tree_{uuid.uuid4().hex[:12]}"
    db.trees.insert_one({
        "id": tid,
        "name": name,
        "owner_id": owner_id,
        "plan": "free",
        "is_public": False,
        "root_person_id": None,
        "created_at": now_utc(),
    })
    CREATED["tree_ids"].add(tid)
    return tid


def _add_member(db, tid, user_id, role):
    db.tree_members.insert_one({
        "id": str(uuid.uuid4()),
        "tree_id": tid,
        "user_id": user_id,
        "role": role,
        "joined_at": now_utc(),
    })


def _insert_person(db, tid, name, email=None, is_alive=True, death_date=None):
    pid = str(uuid.uuid4())
    db.people.insert_one({
        "id": pid,
        "tree_id": tid,
        "name": name,
        "email": email,
        "gender": None,
        "death_date": death_date,
        "is_alive": is_alive,
        "is_root": False,
        "created_by": None,
        "created_at": now_utc(),
        "deleted_at": None,
    })
    CREATED["person_ids"].add(pid)
    return pid


def _insert_relation(db, tid, a, b, kind):
    rid = str(uuid.uuid4())
    db.relations.insert_one({
        "id": rid, "tree_id": tid, "a": a, "b": b, "type": kind,
        "created_at": now_utc(),
    })
    return rid


# ---------------------------------------------------------------------------
# Fixtures — main context with 2 trees
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def ctx(db):
    """
    T_MAIN (persisted for whole module):
      A(admin+OWNER), B(editor), C(viewer), D(editor deceased-linked), E(viewer)
    Used for group + mute + regression tests.
    """
    A_id, A_tok, A_email = _seed_user(db, "A")
    B_id, B_tok, B_email = _seed_user(db, "B")
    C_id, C_tok, C_email = _seed_user(db, "C")
    D_id, D_tok, D_email = _seed_user(db, "D")
    E_id, E_tok, E_email = _seed_user(db, "E")

    T = _seed_tree(db, A_id, f"{PREFIX}_MainTree")
    _add_member(db, T, A_id, "admin")
    _add_member(db, T, B_id, "editor")
    _add_member(db, T, C_id, "viewer")
    _add_member(db, T, D_id, "editor")
    _add_member(db, T, E_id, "viewer")

    _insert_person(db, T, f"{PREFIX}_PersonA", email=A_email, is_alive=True)
    _insert_person(db, T, f"{PREFIX}_PersonD", email=D_email,
                   is_alive=False, death_date="2020-05-10")

    yield {
        "T": T,
        "A": {"id": A_id, "token": A_tok, "email": A_email},
        "B": {"id": B_id, "token": B_tok, "email": B_email},
        "C": {"id": C_id, "token": C_tok, "email": C_email},
        "D": {"id": D_id, "token": D_tok, "email": D_email},
        "E": {"id": E_id, "token": E_tok, "email": E_email},
    }

    # ------------- Teardown: ONLY our synthetic docs -------------
    tree_ids = list(CREATED["tree_ids"])
    user_ids = list(CREATED["user_ids"])
    tokens = list(CREATED["session_tokens"])
    person_ids = list(CREATED["person_ids"])
    chat_room_ids = list(CREATED["chat_room_ids"])

    if tree_ids:
        rooms_in_trees = list(db.chat_rooms.find({"tree_id": {"$in": tree_ids}}, {"id": 1}))
        for r in rooms_in_trees:
            chat_room_ids.append(r["id"])
        db.chat_rooms.delete_many({"tree_id": {"$in": tree_ids}})
        db.family_chat.delete_many({"tree_id": {"$in": tree_ids}})
        db.chat_typing.delete_many({"room_id": {"$in": tree_ids + chat_room_ids}})
        db.chat_mutes.delete_many({"room_id": {"$in": tree_ids + chat_room_ids}})
        db.app_notifications.delete_many({"tree_id": {"$in": tree_ids}})
        db.people.delete_many({"tree_id": {"$in": tree_ids}})
        db.relations.delete_many({"tree_id": {"$in": tree_ids}})
        db.tree_members.delete_many({"tree_id": {"$in": tree_ids}})
        db.person_notes.delete_many({"tree_id": {"$in": tree_ids}})
        db.join_requests.delete_many({"tree_id": {"$in": tree_ids}})
        db.tree_invites.delete_many({"tree_id": {"$in": tree_ids}})
        db.trees.delete_many({"id": {"$in": tree_ids}})

    if chat_room_ids:
        db.chat_rooms.delete_many({"id": {"$in": chat_room_ids}})
        db.chat_mutes.delete_many({"room_id": {"$in": chat_room_ids}})
    if person_ids:
        db.people.delete_many({"id": {"$in": person_ids}})

    if user_ids:
        db.tree_members.delete_many({"user_id": {"$in": user_ids}})
        db.user_sessions.delete_many({"session_token": {"$in": tokens}})
        db.app_notifications.delete_many({"user_id": {"$in": user_ids}})
        db.chat_mutes.delete_many({"user_id": {"$in": user_ids}})
        db.users.delete_many({"user_id": {"$in": user_ids}})


# ============================================================================
# 1. DELETE /api/trees/{tid}
# ============================================================================
class TestDeleteTree:
    """DELETE /api/trees/{tid} — owner-only + full cascade cleanup."""

    def test_delete_unknown_tree_returns_404(self, ctx):
        r = requests.delete(f"{API}/trees/nonexistent_{uuid.uuid4().hex[:8]}",
                            headers=auth(ctx["A"]["token"]))
        assert r.status_code == 404, r.text

    def test_non_owner_member_gets_403(self, db, ctx):
        """A joined admin/editor who is NOT the owner cannot delete."""
        # Seed a throwaway tree owned by A, invite B as admin
        owner_id, owner_tok, _ = _seed_user(db, "OWNER1")
        member_id, member_tok, _ = _seed_user(db, "MEMBER1")
        tid = _seed_tree(db, owner_id, f"{PREFIX}_403Tree")
        _add_member(db, tid, owner_id, "admin")
        _add_member(db, tid, member_id, "admin")  # admin role but NOT owner
        r = requests.delete(f"{API}/trees/{tid}",
                            headers=auth(member_tok))
        assert r.status_code == 403, r.text
        # cleanup — owner deletes for us
        requests.delete(f"{API}/trees/{tid}", headers=auth(owner_tok))

    def test_owner_delete_full_cascade(self, db):
        """Owner can delete; verify tree + tree_members + people + relations +
        chat_rooms + family_chat + chat_mutes are all gone."""
        owner_id, owner_tok, owner_email = _seed_user(db, "OWNER2")
        buddy_id, buddy_tok, buddy_email = _seed_user(db, "BUDDY")

        tid = _seed_tree(db, owner_id, f"{PREFIX}_CascadeTree")
        _add_member(db, tid, owner_id, "admin")
        _add_member(db, tid, buddy_id, "editor")

        # Seed synthetic data in every cascade collection
        p1 = _insert_person(db, tid, f"{PREFIX}_CascP1", email=owner_email)
        p2 = _insert_person(db, tid, f"{PREFIX}_CascP2", email=buddy_email)
        _insert_relation(db, tid, p1, p2, "spouse")

        db.person_notes.insert_one({
            "id": str(uuid.uuid4()), "tree_id": tid, "person_id": p1,
            "author_id": owner_id, "body": "n", "created_at": now_utc(),
            "deleted_at": None,
        })
        db.app_notifications.insert_one({
            "id": str(uuid.uuid4()), "user_id": buddy_id, "tree_id": tid,
            "type": "chat", "title": "t", "body": "b", "read": False,
            "created_at": now_utc(),
        })
        db.join_requests.insert_one({
            "id": str(uuid.uuid4()), "tree_id": tid, "user_id": buddy_id,
            "status": "pending", "created_at": now_utc(),
        })
        db.tree_invites.insert_one({
            "id": str(uuid.uuid4()), "tree_id": tid,
            "code": f"{PREFIX}_{uuid.uuid4().hex[:6]}", "role": "editor",
            "created_at": now_utc(),
        })

        # Create a group + a family-room chat message via API
        rg = requests.post(f"{API}/chat/group?tree_id={tid}",
                           headers=auth(owner_tok),
                           json={"name": f"{PREFIX}_CascGroup",
                                 "member_ids": [buddy_id]})
        assert rg.status_code == 200, rg.text
        gid = rg.json()["id"]
        CREATED["chat_room_ids"].add(gid)

        # send a family-room message
        rm1 = requests.post(f"{API}/chat?tree_id={tid}&room_id={tid}",
                            headers=auth(owner_tok),
                            json={"message": "hi fam"})
        assert rm1.status_code == 200, rm1.text
        # send a group message
        rm2 = requests.post(f"{API}/chat?tree_id={tid}&room_id={gid}",
                            headers=auth(owner_tok),
                            json={"message": "hi group"})
        assert rm2.status_code == 200, rm2.text

        # mute the family room + group room for buddy (creates chat_mutes docs)
        rmu1 = requests.post(f"{API}/chat/rooms/{tid}/mute?tree_id={tid}",
                             headers=auth(buddy_tok), json={"muted": True})
        assert rmu1.status_code == 200, rmu1.text
        rmu2 = requests.post(f"{API}/chat/rooms/{gid}/mute?tree_id={tid}",
                             headers=auth(buddy_tok), json={"muted": True})
        assert rmu2.status_code == 200, rmu2.text

        # sanity: mutes exist
        assert db.chat_mutes.count_documents({"room_id": {"$in": [tid, gid]}}) == 2

        chat_typing_doc_id = str(uuid.uuid4())
        db.chat_typing.insert_one({
            "id": chat_typing_doc_id, "user_id": owner_id, "name": "x",
            "room_id": tid, "updated_at": now_utc(),
        })

        # ---- DELETE by owner ----
        r = requests.delete(f"{API}/trees/{tid}", headers=auth(owner_tok))
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True}

        # ---- Verify cascade ----
        assert db.trees.count_documents({"id": tid}) == 0
        assert db.tree_members.count_documents({"tree_id": tid}) == 0
        assert db.people.count_documents({"tree_id": tid}) == 0
        assert db.relations.count_documents({"tree_id": tid}) == 0
        assert db.person_notes.count_documents({"tree_id": tid}) == 0
        assert db.app_notifications.count_documents({"tree_id": tid}) == 0
        assert db.join_requests.count_documents({"tree_id": tid}) == 0
        assert db.tree_invites.count_documents({"tree_id": tid}) == 0
        assert db.chat_rooms.count_documents({"tree_id": tid}) == 0
        assert db.family_chat.count_documents({"tree_id": tid}) == 0
        assert db.chat_typing.count_documents({"room_id": {"$in": [tid, gid]}}) == 0
        assert db.chat_mutes.count_documents({"room_id": {"$in": [tid, gid]}}) == 0

        # Confirm 404 after delete
        r2 = requests.delete(f"{API}/trees/{tid}", headers=auth(owner_tok))
        assert r2.status_code == 404, r2.text


# ============================================================================
# 2. PUT /api/chat/rooms/{room_id} — group management
# ============================================================================
class TestManageGroup:
    """PUT /api/chat/rooms/{room_id} — rename + replace members with rules."""

    @pytest.fixture(scope="class")
    def group(self, ctx):
        """B (editor) creates a group with A, C, D initially (creator=B)."""
        r = requests.post(f"{API}/chat/group?tree_id={ctx['T']}",
                          headers=auth(ctx["B"]["token"]),
                          json={"name": f"{PREFIX}_MgmtGroup",
                                "member_ids": [ctx["A"]["id"], ctx["C"]["id"],
                                               ctx["D"]["id"]]})
        assert r.status_code == 200, r.text
        gid = r.json()["id"]
        CREATED["chat_room_ids"].add(gid)
        return gid

    def test_creator_can_rename_and_replace_members(self, ctx, group):
        # Creator B renames + replaces members. New set: [E]. Filter includes
        # invalid id "bogus". Result must retain creator B AND caller B (same),
        # plus valid E; bogus filtered.
        r = requests.put(f"{API}/chat/rooms/{group}?tree_id={ctx['T']}",
                         headers=auth(ctx["B"]["token"]),
                         json={"name": f"{PREFIX}_Renamed",
                               "member_ids": [ctx["E"]["id"], "bogus_id_x"]})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["name"] == f"{PREFIX}_Renamed"
        mids = set(data["member_ids"])
        assert ctx["B"]["id"] in mids, "creator must be retained"
        assert ctx["E"]["id"] in mids, "valid new member must be added"
        assert "bogus_id_x" not in mids, "invalid ids must be filtered"

    def test_tree_admin_can_manage_even_if_not_creator(self, ctx, group):
        """Tree admin A is not creator (B is) but must be allowed to manage.
        However admin also needs to be a group member. So after previous test
        group members = {B, E}. A is NOT in group -> should 403 first."""
        r_not_mem = requests.put(f"{API}/chat/rooms/{group}?tree_id={ctx['T']}",
                                 headers=auth(ctx["A"]["token"]),
                                 json={"name": f"{PREFIX}_ByAdmin"})
        # A is admin of the tree but not member of the group -> 403 per code
        assert r_not_mem.status_code == 403, r_not_mem.text

        # Add A back as a member first (via creator B)
        r_add = requests.put(f"{API}/chat/rooms/{group}?tree_id={ctx['T']}",
                             headers=auth(ctx["B"]["token"]),
                             json={"member_ids": [ctx["A"]["id"],
                                                  ctx["E"]["id"]]})
        assert r_add.status_code == 200
        mids = set(r_add.json()["member_ids"])
        assert ctx["A"]["id"] in mids and ctx["B"]["id"] in mids

        # Now A (tree admin + group member, non-creator) can manage
        r_ok = requests.put(f"{API}/chat/rooms/{group}?tree_id={ctx['T']}",
                            headers=auth(ctx["A"]["token"]),
                            json={"name": f"{PREFIX}_ByAdmin"})
        assert r_ok.status_code == 200, r_ok.text
        assert r_ok.json()["name"] == f"{PREFIX}_ByAdmin"

    def test_non_manager_member_cannot_update(self, ctx, group):
        """C (viewer role in tree) added as a member cannot manage."""
        # Ensure C is a member (creator B adds C)
        requests.put(f"{API}/chat/rooms/{group}?tree_id={ctx['T']}",
                     headers=auth(ctx["B"]["token"]),
                     json={"member_ids": [ctx["A"]["id"], ctx["C"]["id"]]})
        r = requests.put(f"{API}/chat/rooms/{group}?tree_id={ctx['T']}",
                         headers=auth(ctx["C"]["token"]),
                         json={"name": f"{PREFIX}_HackAttempt"})
        assert r.status_code == 403, r.text

    def test_404_for_unknown_or_non_group(self, ctx):
        r = requests.put(f"{API}/chat/rooms/nonexistent_x?tree_id={ctx['T']}",
                         headers=auth(ctx["A"]["token"]),
                         json={"name": "x"})
        assert r.status_code == 404, r.text

        # Non-group: direct room
        rd = requests.post(f"{API}/chat/direct?tree_id={ctx['T']}",
                           headers=auth(ctx["A"]["token"]),
                           json={"user_id": ctx["B"]["id"]})
        assert rd.status_code == 200, rd.text
        did = rd.json()["id"]
        CREATED["chat_room_ids"].add(did)

        r404 = requests.put(f"{API}/chat/rooms/{did}?tree_id={ctx['T']}",
                            headers=auth(ctx["A"]["token"]),
                            json={"name": "x"})
        assert r404.status_code == 404, r404.text


# ============================================================================
# 3. POST /api/chat/rooms/{room_id}/mute — mute/unmute per room
# ============================================================================
class TestMuteRoom:
    """Mute upserts; unmute deletes; family / group / direct all supported."""

    def test_mute_family_room(self, db, ctx):
        r = requests.post(f"{API}/chat/rooms/{ctx['T']}/mute?tree_id={ctx['T']}",
                          headers=auth(ctx["E"]["token"]),
                          json={"muted": True})
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True, "muted": True}
        doc = db.chat_mutes.find_one({"user_id": ctx["E"]["id"],
                                      "room_id": ctx["T"]})
        assert doc is not None

        # Unmute -> deletes doc
        r2 = requests.post(f"{API}/chat/rooms/{ctx['T']}/mute?tree_id={ctx['T']}",
                           headers=auth(ctx["E"]["token"]),
                           json={"muted": False})
        assert r2.status_code == 200, r2.text
        assert r2.json() == {"ok": True, "muted": False}
        doc2 = db.chat_mutes.find_one({"user_id": ctx["E"]["id"],
                                       "room_id": ctx["T"]})
        assert doc2 is None

    def test_mute_group_room(self, db, ctx):
        rg = requests.post(f"{API}/chat/group?tree_id={ctx['T']}",
                           headers=auth(ctx["A"]["token"]),
                           json={"name": f"{PREFIX}_MuteGroup",
                                 "member_ids": [ctx["B"]["id"]]})
        assert rg.status_code == 200, rg.text
        gid = rg.json()["id"]
        CREATED["chat_room_ids"].add(gid)

        r = requests.post(f"{API}/chat/rooms/{gid}/mute?tree_id={ctx['T']}",
                          headers=auth(ctx["B"]["token"]),
                          json={"muted": True})
        assert r.status_code == 200 and r.json()["muted"] is True
        assert db.chat_mutes.find_one({"user_id": ctx["B"]["id"],
                                       "room_id": gid}) is not None

    def test_mute_direct_room(self, db, ctx):
        rd = requests.post(f"{API}/chat/direct?tree_id={ctx['T']}",
                           headers=auth(ctx["A"]["token"]),
                           json={"user_id": ctx["E"]["id"]})
        assert rd.status_code == 200
        did = rd.json()["id"]
        CREATED["chat_room_ids"].add(did)

        r = requests.post(f"{API}/chat/rooms/{did}/mute?tree_id={ctx['T']}",
                          headers=auth(ctx["E"]["token"]),
                          json={"muted": True})
        assert r.status_code == 200 and r.json()["muted"] is True
        assert db.chat_mutes.find_one({"user_id": ctx["E"]["id"],
                                       "room_id": did}) is not None

    def test_mute_upsert_idempotent(self, db, ctx):
        """Muting an already-muted room should NOT create duplicate docs."""
        # E is already muted on the direct room from previous test if class
        # order held. To be safe, create a fresh state.
        rd = requests.post(f"{API}/chat/direct?tree_id={ctx['T']}",
                           headers=auth(ctx["A"]["token"]),
                           json={"user_id": ctx["C"]["id"]})
        did = rd.json()["id"]
        CREATED["chat_room_ids"].add(did)
        for _ in range(3):
            r = requests.post(f"{API}/chat/rooms/{did}/mute?tree_id={ctx['T']}",
                              headers=auth(ctx["C"]["token"]),
                              json={"muted": True})
            assert r.status_code == 200
        n = db.chat_mutes.count_documents({"user_id": ctx["C"]["id"],
                                           "room_id": did})
        assert n == 1


# ============================================================================
# 4. Mute suppresses app_notifications on message send
# ============================================================================
class TestMuteBlocksNotifications:
    def test_muted_user_gets_no_notification(self, db, ctx):
        # Fresh group A + B + E
        rg = requests.post(f"{API}/chat/group?tree_id={ctx['T']}",
                           headers=auth(ctx["A"]["token"]),
                           json={"name": f"{PREFIX}_NotifGroup",
                                 "member_ids": [ctx["B"]["id"], ctx["E"]["id"]]})
        assert rg.status_code == 200, rg.text
        gid = rg.json()["id"]
        CREATED["chat_room_ids"].add(gid)

        # B mutes the group; E does not
        r_mute = requests.post(f"{API}/chat/rooms/{gid}/mute?tree_id={ctx['T']}",
                               headers=auth(ctx["B"]["token"]),
                               json={"muted": True})
        assert r_mute.status_code == 200

        # Clear any pre-existing notifications for B/E on this tree (SCOPED)
        db.app_notifications.delete_many({
            "user_id": {"$in": [ctx["B"]["id"], ctx["E"]["id"]]},
            "tree_id": ctx["T"],
        })

        # A sends a message to the group
        r_send = requests.post(
            f"{API}/chat?tree_id={ctx['T']}&room_id={gid}",
            headers=auth(ctx["A"]["token"]),
            json={"message": f"{PREFIX}_notif_ping"})
        assert r_send.status_code == 200, r_send.text

        # B (muted) should have NO chat notification for this tree
        b_notifs = list(db.app_notifications.find({
            "user_id": ctx["B"]["id"], "tree_id": ctx["T"], "type": "chat",
        }))
        e_notifs = list(db.app_notifications.find({
            "user_id": ctx["E"]["id"], "tree_id": ctx["T"], "type": "chat",
        }))
        assert len(b_notifs) == 0, f"muted user B should NOT have notifications, got {b_notifs}"
        assert len(e_notifs) >= 1, "non-muted user E should have received the notification"


# ============================================================================
# 5. GET rooms / GET chat surface muted + can_manage
# ============================================================================
class TestMutedAndCanManageSurfaced:
    def test_list_rooms_includes_muted_flag(self, db, ctx):
        # Family room: mute for A
        requests.post(f"{API}/chat/rooms/{ctx['T']}/mute?tree_id={ctx['T']}",
                      headers=auth(ctx["A"]["token"]),
                      json={"muted": True})
        r = requests.get(f"{API}/chat/rooms?tree_id={ctx['T']}",
                         headers=auth(ctx["A"]["token"]))
        assert r.status_code == 200, r.text
        rooms = r.json()["rooms"]
        fam = next((x for x in rooms if x["type"] == "family"), None)
        assert fam is not None
        assert fam.get("muted") is True

        # unmute for cleanliness
        requests.post(f"{API}/chat/rooms/{ctx['T']}/mute?tree_id={ctx['T']}",
                      headers=auth(ctx["A"]["token"]),
                      json={"muted": False})
        r2 = requests.get(f"{API}/chat/rooms?tree_id={ctx['T']}",
                          headers=auth(ctx["A"]["token"]))
        fam2 = next((x for x in r2.json()["rooms"] if x["type"] == "family"), None)
        assert fam2.get("muted") is False

    def test_get_chat_includes_muted_and_can_manage(self, ctx):
        # A group created by B; A is tree admin -> can_manage should be True
        rg = requests.post(f"{API}/chat/group?tree_id={ctx['T']}",
                           headers=auth(ctx["B"]["token"]),
                           json={"name": f"{PREFIX}_CanManage",
                                 "member_ids": [ctx["A"]["id"]]})
        gid = rg.json()["id"]
        CREATED["chat_room_ids"].add(gid)

        # A: admin -> can_manage True
        rA = requests.get(f"{API}/chat?tree_id={ctx['T']}&room_id={gid}",
                          headers=auth(ctx["A"]["token"]))
        assert rA.status_code == 200, rA.text
        dA = rA.json()
        assert "muted" in dA and dA["muted"] is False
        assert dA.get("can_manage") is True

        # B: creator -> can_manage True
        rB = requests.get(f"{API}/chat?tree_id={ctx['T']}&room_id={gid}",
                          headers=auth(ctx["B"]["token"]))
        assert rB.json().get("can_manage") is True

        # Family room: can_manage should be False (not a group)
        rFam = requests.get(f"{API}/chat?tree_id={ctx['T']}&room_id={ctx['T']}",
                            headers=auth(ctx["A"]["token"]))
        assert rFam.status_code == 200
        assert rFam.json().get("can_manage") is False


# ============================================================================
# 6. Regression — messaging + unread + deceased still work
# ============================================================================
class TestRegression:
    def test_send_read_and_unread_counts(self, ctx):
        # A sends 2 messages in family room; E's unread should be >= 2
        for i in range(2):
            r = requests.post(f"{API}/chat?tree_id={ctx['T']}&room_id={ctx['T']}",
                              headers=auth(ctx["A"]["token"]),
                              json={"message": f"{PREFIX}_reg_{i}"})
            assert r.status_code == 200, r.text

        # E: family room unread should be > 0
        r_list = requests.get(f"{API}/chat/rooms?tree_id={ctx['T']}",
                              headers=auth(ctx["E"]["token"]))
        rooms = r_list.json()["rooms"]
        fam = next(x for x in rooms if x["type"] == "family")
        assert fam["unread"] >= 2, f"expected unread>=2 got {fam['unread']}"

        # E opens the family room -> unread resets
        r_open = requests.get(f"{API}/chat?tree_id={ctx['T']}&room_id={ctx['T']}",
                              headers=auth(ctx["E"]["token"]))
        assert r_open.status_code == 200
        assert any((PREFIX in m.get("message", "")) for m in r_open.json()["messages"])

        r_list2 = requests.get(f"{API}/chat/rooms?tree_id={ctx['T']}",
                               headers=auth(ctx["E"]["token"]))
        fam2 = next(x for x in r_list2.json()["rooms"] if x["type"] == "family")
        assert fam2["unread"] == 0

    def test_deceased_sender_still_blocked(self, ctx):
        """D is linked to a person with is_alive=False -> 403 with 'meninggal'."""
        r = requests.post(f"{API}/chat?tree_id={ctx['T']}&room_id={ctx['T']}",
                          headers=auth(ctx["D"]["token"]),
                          json={"message": f"{PREFIX}_from_deceased"})
        assert r.status_code == 403, r.text
        assert "meninggal" in r.text.lower()
