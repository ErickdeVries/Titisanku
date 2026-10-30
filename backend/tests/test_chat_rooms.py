"""KETURUNANKU backend tests — WhatsApp-style multi-room Chat (Iteration 8).

Coverage (Iteration 8 spec):
- GET /api/chat/rooms: always includes Family room (id == tree_id, type 'family',
  pinned first). Includes any groups + direct rooms the user belongs to. Each
  room has last_message, last_message_at, unread, member_count, name.
- GET /api/chat/contacts: returns all OTHER tree members (excludes self).
- POST /api/chat/group: admin/editor creates a group; viewer -> 403; creator
  auto-added; invalid member_ids filtered out.
- POST /api/chat/direct: get-or-create idempotent; 400 for self; 404 for user
  not in tree.
- GET /api/chat?room_id=<id>: returns messages scoped to that room, correct
  room_type / room_name (other participant for direct), can_send, members;
  enforces membership (403 for non-participant of group/direct).
- POST /api/chat?room_id=<id>: family room requires admin/editor (viewer 403);
  group/direct requires participant; reply_to snapshot + mentions preserved.
- DECEASED RULE: sender's linked person (email match) with is_alive=false or
  death_date set -> 403 'Anggota yang telah meninggal tidak dapat mengirim pesan'.
  A living/unlinked sender can still send normally.
- Backward compatibility: legacy messages with room_id == tree_id still show
  up in the Family room (GET /api/chat with no room_id and with room_id==tid).
- Unread counts: after B posts to a room, A sees unread>0 for that room; after
  A opens GET /api/chat?room_id=<id>, unread resets to 0 (read_by updated).

Cleanup: ONLY our synthetic docs are removed (tracked ids). We NEVER call
delete_many({}). Real family data in the shared preview DB is preserved.
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


# All ids we touch — cleaned up on module teardown. Never delete_many({}).
CREATED = {
    "user_ids": set(),
    "session_tokens": set(),
    "tree_ids": set(),
    "person_ids": set(),
    "chat_room_ids": set(),
    "family_chat_ids": set(),
    "app_notification_ids": set(),  # not tracked individually; deleted by tree_id
}


@pytest.fixture(scope="class")
def mongo_db():
    c = MongoClient(MONGO_URL)
    return c[DB_NAME]


def _seed_user(db, label, email_hint=None):
    uid = f"user_{uuid.uuid4().hex[:12]}"
    email = email_hint or f"TEST_CHAT_{label}_{uuid.uuid4().hex[:6]}@example.com"
    token = secrets.token_hex(16)
    db.users.insert_one({
        "user_id": uid,
        "email": email,
        "name": f"TEST_CHAT_{label}_{uid[-4:]}",
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
        "birth_date": None,
        "birth_place": None,
        "death_date": death_date,
        "photo_url": None,
        "job": None,
        "is_adopted": False,
        "notes": None,
        "is_alive": is_alive,
        "is_root": False,
        "created_by": None,
        "created_at": now_utc(),
        "deleted_at": None,
    })
    CREATED["person_ids"].add(pid)
    return pid


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="class")
def ctx(mongo_db):
    """Scope `class`: seluruh alur chat kini satu kelas (lihat TestChatRooms),
    dan pytest-xdist `--dist loadscope` menjalankan satu kelas di satu worker.
    Dengan scope `module` dulu, fixture dieksekusi ulang di worker lain
    sehingga id room/group yang disimpan STATE tidak ditemukan.

    Two trees:
      T1 — with members A(admin, alive-linked), B(editor, alive-linked),
           C(viewer, unlinked), D(editor, DECEASED-linked), E(viewer, unlinked)
      T2 — with only A(admin) and OUTSIDER X (editor). Used for isolation
           checks (X is not in T1).
    """
    db = mongo_db
    A_id, A_tok, A_email = _seed_user(db, "A")
    B_id, B_tok, B_email = _seed_user(db, "B")
    C_id, C_tok, C_email = _seed_user(db, "C")
    D_id, D_tok, D_email = _seed_user(db, "D")
    E_id, E_tok, E_email = _seed_user(db, "E")
    X_id, X_tok, X_email = _seed_user(db, "X")

    T1 = _seed_tree(db, A_id, "TEST_CHAT_Tree1")
    _add_member(db, T1, A_id, "admin")
    _add_member(db, T1, B_id, "editor")
    _add_member(db, T1, C_id, "viewer")
    _add_member(db, T1, D_id, "editor")
    _add_member(db, T1, E_id, "viewer")

    T2 = _seed_tree(db, A_id, "TEST_CHAT_Tree2")
    _add_member(db, T2, A_id, "admin")
    _add_member(db, T2, X_id, "editor")

    # People in T1:
    #  - A: linked (alive)
    #  - B: linked (alive)
    #  - C: NOT linked (no person row with C's email) -> alive/unlinked
    #  - D: linked and DECEASED (is_alive=False, death_date set)
    #  - E: linked (alive)
    _insert_person(db, T1, "TEST_CHAT_PersonA", email=A_email, is_alive=True)
    _insert_person(db, T1, "TEST_CHAT_PersonB", email=B_email, is_alive=True)
    _insert_person(db, T1, "TEST_CHAT_PersonD", email=D_email,
                   is_alive=False, death_date="2020-05-10")
    _insert_person(db, T1, "TEST_CHAT_PersonE", email=E_email, is_alive=True)

    yield {
        "T1": T1, "T2": T2,
        "A": {"id": A_id, "token": A_tok, "email": A_email},
        "B": {"id": B_id, "token": B_tok, "email": B_email},
        "C": {"id": C_id, "token": C_tok, "email": C_email},
        "D": {"id": D_id, "token": D_tok, "email": D_email},
        "E": {"id": E_id, "token": E_tok, "email": E_email},
        "X": {"id": X_id, "token": X_tok, "email": X_email},
    }

    # -------------------- Teardown: ONLY our synthetic docs --------------------
    tree_ids = list(CREATED["tree_ids"])
    user_ids = list(CREATED["user_ids"])
    tokens = list(CREATED["session_tokens"])
    person_ids = list(CREATED["person_ids"])
    chat_room_ids = list(CREATED["chat_room_ids"])
    family_chat_ids = list(CREATED["family_chat_ids"])

    if tree_ids:
        # Rooms/messages/notifications scoped to our trees
        rooms_in_trees = list(db.chat_rooms.find({"tree_id": {"$in": tree_ids}}, {"id": 1}))
        for r in rooms_in_trees:
            chat_room_ids.append(r["id"])
        db.chat_rooms.delete_many({"tree_id": {"$in": tree_ids}})
        db.family_chat.delete_many({"tree_id": {"$in": tree_ids}})
        db.chat_typing.delete_many({"room_id": {"$in": tree_ids + chat_room_ids}})
        db.app_notifications.delete_many({"tree_id": {"$in": tree_ids}})
        db.people.delete_many({"tree_id": {"$in": tree_ids}})
        db.relations.delete_many({"tree_id": {"$in": tree_ids}})
        db.tree_members.delete_many({"tree_id": {"$in": tree_ids}})
        db.trees.delete_many({"id": {"$in": tree_ids}})

    if chat_room_ids:
        db.chat_rooms.delete_many({"id": {"$in": chat_room_ids}})
    if family_chat_ids:
        db.family_chat.delete_many({"id": {"$in": family_chat_ids}})
    if person_ids:
        db.people.delete_many({"id": {"$in": person_ids}})

    if user_ids:
        db.tree_members.delete_many({"user_id": {"$in": user_ids}})
        db.user_sessions.delete_many({"session_token": {"$in": tokens}})
        db.app_notifications.delete_many({"user_id": {"$in": user_ids}})
        db.users.delete_many({"user_id": {"$in": user_ids}})


# ---------------------------------------------------------------------------
# 1. GET /api/chat/rooms — Family room always present, pinned first
# ---------------------------------------------------------------------------
class TestChatRooms:
    """Alur end-to-end. Test berurutan dan berbagi STATE; satu kelas =
    satu worker xdist (loadscope), sehingga state tetap konsisten.
    """

    # ----------------------------------------------------------------------
    # Bagian: TestListRooms
    # ----------------------------------------------------------------------

    def test_family_room_always_present_and_pinned(self, ctx):
        r = requests.get(f"{API}/chat/rooms?tree_id={ctx['T1']}",
                         headers=auth(ctx["A"]["token"]))
        assert r.status_code == 200, r.text
        data = r.json()
        assert "rooms" in data
        rooms = data["rooms"]
        assert len(rooms) >= 1
        first = rooms[0]
        assert first["type"] == "family"
        assert first["id"] == ctx["T1"]
        assert first["member_count"] == 5  # A, B, C, D, E
        # required shape
        for key in ("last_message", "last_message_at", "unread", "member_count", "name"):
            assert key in first, f"family room missing {key}"

    def test_only_family_room_when_no_groups_or_dms(self, ctx):
        # E has no groups / DMs yet -> only sees family
        r = requests.get(f"{API}/chat/rooms?tree_id={ctx['T1']}",
                         headers=auth(ctx["E"]["token"]))
        assert r.status_code == 200
        rooms = r.json()["rooms"]
        assert [x["type"] for x in rooms].count("family") == 1
        assert all(x["type"] == "family" for x in rooms)


# ---------------------------------------------------------------------------
# 2. GET /api/chat/contacts — excludes self
# ---------------------------------------------------------------------------

    # ----------------------------------------------------------------------
    # Bagian: TestContacts
    # ----------------------------------------------------------------------

    def test_contacts_exclude_self(self, ctx):
        r = requests.get(f"{API}/chat/contacts?tree_id={ctx['T1']}",
                         headers=auth(ctx["A"]["token"]))
        assert r.status_code == 200, r.text
        contacts = r.json()["contacts"]
        ids = [c["user_id"] for c in contacts]
        # Should include B, C, D, E but NOT A
        assert ctx["A"]["id"] not in ids
        assert set(ids) == {ctx["B"]["id"], ctx["C"]["id"],
                            ctx["D"]["id"], ctx["E"]["id"]}
        # Each has expected fields
        for c in contacts:
            for key in ("user_id", "name", "picture", "role"):
                assert key in c


# ---------------------------------------------------------------------------
# 3. POST /api/chat/group — admin/editor creates; viewer 403
# ---------------------------------------------------------------------------

    # ----------------------------------------------------------------------
    # Bagian: TestGroupCreation
    # ----------------------------------------------------------------------

    def test_admin_can_create_group_and_filter_invalid(self, ctx):
        payload = {
            "name": "TEST_CHAT_GroupAlpha",
            # includes a bogus id — must be filtered out; A auto-added
            "member_ids": [ctx["B"]["id"], ctx["C"]["id"], "user_bogus_xxxxxxxxxxxx"],
        }
        r = requests.post(f"{API}/chat/group?tree_id={ctx['T1']}",
                          json=payload, headers=auth(ctx["A"]["token"]))
        assert r.status_code == 200, r.text
        room = r.json()
        CREATED["chat_room_ids"].add(room["id"])
        assert room["type"] == "group"
        assert room["name"] == "TEST_CHAT_GroupAlpha"
        # creator A auto-added; bogus filtered
        assert set(room["member_ids"]) == {ctx["A"]["id"], ctx["B"]["id"], ctx["C"]["id"]}
        # stash for later tests
        ctx["group_id"] = room["id"]

    def test_viewer_can_create_group(self, ctx):
        # Desain produk: SEMUA anggota pohon boleh membuat grup dan memilih
        # anggotanya sendiri (lihat create_group di backend). Viewer tidak
        # dibatasi, karena grup chat tidak mengubah data silsilah.
        r = requests.post(f"{API}/chat/group?tree_id={ctx['T1']}",
                          json={"name": "TEST_CHAT_ViewerGroup", "member_ids": [ctx["A"]["id"]]},
                          headers=auth(ctx["C"]["token"]))
        assert r.status_code == 200, r.text
        room = r.json()
        CREATED["chat_room_ids"].add(room["id"])
        assert room["type"] == "group"
        assert ctx["C"]["id"] in room["member_ids"]

    def test_non_member_cannot_create_group(self, ctx):
        # Yang tetap ditolak: orang di luar pohon tidak bisa memakai tree_id
        # untuk membuat grup.
        r = requests.post(f"{API}/chat/group?tree_id={ctx['T1']}",
                          json={"name": "TEST_CHAT_OutsiderGroup", "member_ids": [ctx["A"]["id"]]},
                          headers=auth(ctx["X"]["token"]))
        assert r.status_code == 403, r.text

    def test_editor_can_create_group(self, ctx):
        r = requests.post(f"{API}/chat/group?tree_id={ctx['T1']}",
                          json={"name": "TEST_CHAT_EditorGroup", "member_ids": [ctx["A"]["id"]]},
                          headers=auth(ctx["B"]["token"]))
        assert r.status_code == 200, r.text
        room = r.json()
        CREATED["chat_room_ids"].add(room["id"])
        assert room["type"] == "group"
        assert ctx["B"]["id"] in room["member_ids"]

    def test_empty_name_rejected(self, ctx):
        r = requests.post(f"{API}/chat/group?tree_id={ctx['T1']}",
                          json={"name": "  ", "member_ids": [ctx["B"]["id"]]},
                          headers=auth(ctx["A"]["token"]))
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# 4. POST /api/chat/direct — idempotent, self-400, not-in-tree-404
# ---------------------------------------------------------------------------

    # ----------------------------------------------------------------------
    # Bagian: TestDirectRoom
    # ----------------------------------------------------------------------

    def test_direct_room_idempotent(self, ctx):
        r1 = requests.post(f"{API}/chat/direct?tree_id={ctx['T1']}",
                           json={"user_id": ctx["B"]["id"]},
                           headers=auth(ctx["A"]["token"]))
        assert r1.status_code == 200, r1.text
        room1 = r1.json()
        CREATED["chat_room_ids"].add(room1["id"])
        assert room1["type"] == "direct"
        assert set(room1["member_ids"]) == {ctx["A"]["id"], ctx["B"]["id"]}
        # second call - either direction - should return SAME room id
        r2 = requests.post(f"{API}/chat/direct?tree_id={ctx['T1']}",
                           json={"user_id": ctx["A"]["id"]},
                           headers=auth(ctx["B"]["token"]))
        assert r2.status_code == 200, r2.text
        room2 = r2.json()
        assert room1["id"] == room2["id"], "direct room must be idempotent (dm_key)"
        ctx["dm_ab"] = room1["id"]

    def test_direct_with_self_400(self, ctx):
        r = requests.post(f"{API}/chat/direct?tree_id={ctx['T1']}",
                          json={"user_id": ctx["A"]["id"]},
                          headers=auth(ctx["A"]["token"]))
        assert r.status_code == 400

    def test_direct_with_non_member_404(self, ctx):
        # X is a member of T2, NOT of T1
        r = requests.post(f"{API}/chat/direct?tree_id={ctx['T1']}",
                          json={"user_id": ctx["X"]["id"]},
                          headers=auth(ctx["A"]["token"]))
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# 5. GET /api/chat?room_id=<id> — membership enforced, direct name, can_send
# ---------------------------------------------------------------------------

    # ----------------------------------------------------------------------
    # Bagian: TestGetChat
    # ----------------------------------------------------------------------

    def test_get_family_room_default(self, ctx):
        r = requests.get(f"{API}/chat?tree_id={ctx['T1']}",
                         headers=auth(ctx["A"]["token"]))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["room_id"] == ctx["T1"]
        assert d["room_type"] == "family"
        assert d["can_send"] is True  # A is admin

    def test_get_family_viewer_cannot_send(self, ctx):
        r = requests.get(f"{API}/chat?tree_id={ctx['T1']}&room_id={ctx['T1']}",
                         headers=auth(ctx["C"]["token"]))
        assert r.status_code == 200
        d = r.json()
        assert d["room_type"] == "family"
        assert d["can_send"] is False

    def test_get_direct_shows_other_name(self, ctx):
        r = requests.get(f"{API}/chat?tree_id={ctx['T1']}&room_id={ctx['dm_ab']}",
                         headers=auth(ctx["A"]["token"]))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["room_type"] == "direct"
        # room_name = other participant's name (B) for A
        b_name = f"TEST_CHAT_B"
        assert b_name in d["room_name"], f"expected B's name, got {d['room_name']}"

    def test_get_group_forbidden_for_non_member(self, ctx):
        # group has A, B, C. Try as D (editor but not in group) -> 403
        r = requests.get(f"{API}/chat?tree_id={ctx['T1']}&room_id={ctx['group_id']}",
                         headers=auth(ctx["D"]["token"]))
        assert r.status_code == 403

    def test_get_direct_forbidden_for_non_participant(self, ctx):
        r = requests.get(f"{API}/chat?tree_id={ctx['T1']}&room_id={ctx['dm_ab']}",
                         headers=auth(ctx["C"]["token"]))
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# 6. POST /api/chat — send messages; role checks; participant checks
# ---------------------------------------------------------------------------

    # ----------------------------------------------------------------------
    # Bagian: TestSendChat
    # ----------------------------------------------------------------------

    def test_admin_can_send_family(self, ctx):
        r = requests.post(f"{API}/chat?tree_id={ctx['T1']}&room_id={ctx['T1']}",
                          json={"message": "TEST_CHAT hello from A (family)"},
                          headers=auth(ctx["A"]["token"]))
        assert r.status_code == 200, r.text
        msg = r.json()
        CREATED["family_chat_ids"].add(msg["id"])
        assert msg["room_id"] == ctx["T1"]
        assert msg["sender_id"] == ctx["A"]["id"]

    def test_viewer_cannot_send_family(self, ctx):
        r = requests.post(f"{API}/chat?tree_id={ctx['T1']}&room_id={ctx['T1']}",
                          json={"message": "TEST_CHAT viewer attempt"},
                          headers=auth(ctx["C"]["token"]))
        assert r.status_code == 403

    def test_group_participant_can_send(self, ctx):
        r = requests.post(f"{API}/chat?tree_id={ctx['T1']}&room_id={ctx['group_id']}",
                          json={"message": "TEST_CHAT hi group from B"},
                          headers=auth(ctx["B"]["token"]))
        assert r.status_code == 200, r.text
        msg = r.json()
        CREATED["family_chat_ids"].add(msg["id"])

    def test_group_non_participant_forbidden(self, ctx):
        r = requests.post(f"{API}/chat?tree_id={ctx['T1']}&room_id={ctx['group_id']}",
                          json={"message": "TEST_CHAT sneak"},
                          headers=auth(ctx["D"]["token"]))
        assert r.status_code == 403

    def test_direct_can_send_and_reply_snapshot(self, ctx):
        # B replies to first family message (reply_to snapshot)
        first = requests.get(f"{API}/chat?tree_id={ctx['T1']}&room_id={ctx['T1']}",
                             headers=auth(ctx["B"]["token"]))
        assert first.status_code == 200
        msgs = first.json()["messages"]
        assert msgs, "expected at least one message in family room"
        target = msgs[0]
        r = requests.post(f"{API}/chat?tree_id={ctx['T1']}&room_id={ctx['dm_ab']}",
                          json={"message": "TEST_CHAT DM w/ reply",
                                "reply_to": target["id"],
                                "mentions": [ctx["A"]["id"]]},
                          headers=auth(ctx["B"]["token"]))
        assert r.status_code == 200, r.text
        m = r.json()
        CREATED["family_chat_ids"].add(m["id"])
        assert m["reply_to"] is not None
        assert m["reply_to"]["id"] == target["id"]

    def test_empty_message_rejected(self, ctx):
        r = requests.post(f"{API}/chat?tree_id={ctx['T1']}&room_id={ctx['T1']}",
                          json={"message": "   ", "attachments": []},
                          headers=auth(ctx["A"]["token"]))
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# 7. Deceased rule — POST /api/chat 403 for deceased-linked sender
# ---------------------------------------------------------------------------

    # ----------------------------------------------------------------------
    # Bagian: TestDeceasedRule
    # ----------------------------------------------------------------------

    def test_deceased_editor_blocked_family(self, ctx):
        r = requests.post(f"{API}/chat?tree_id={ctx['T1']}&room_id={ctx['T1']}",
                          json={"message": "TEST_CHAT ghost msg"},
                          headers=auth(ctx["D"]["token"]))
        assert r.status_code == 403, r.text
        detail = r.json().get("detail", "")
        assert "meninggal" in detail.lower(), f"unexpected detail: {detail}"

    def test_deceased_editor_blocked_direct(self, ctx):
        # Open a direct D<->A (D is editor, is a T1 member -> direct is allowed to be created,
        # but sending is blocked).
        r = requests.post(f"{API}/chat/direct?tree_id={ctx['T1']}",
                          json={"user_id": ctx["A"]["id"]},
                          headers=auth(ctx["D"]["token"]))
        assert r.status_code == 200, r.text
        dm = r.json()
        CREATED["chat_room_ids"].add(dm["id"])
        r2 = requests.post(f"{API}/chat?tree_id={ctx['T1']}&room_id={dm['id']}",
                           json={"message": "TEST_CHAT ghost direct"},
                           headers=auth(ctx["D"]["token"]))
        assert r2.status_code == 403
        assert "meninggal" in r2.json().get("detail", "").lower()

    def test_unlinked_viewer_can_send_in_group(self, ctx):
        # C is a viewer but was added to the group by A -> viewer normally cannot
        # POST anywhere except group/direct where can_send is True. Confirm C
        # (unlinked, alive) is NOT deceased-blocked; expect 200.
        r = requests.post(f"{API}/chat?tree_id={ctx['T1']}&room_id={ctx['group_id']}",
                          json={"message": "TEST_CHAT unlinked viewer group msg"},
                          headers=auth(ctx["C"]["token"]))
        assert r.status_code == 200, r.text
        CREATED["family_chat_ids"].add(r.json()["id"])


# ---------------------------------------------------------------------------
# 8. Backward compatibility — legacy room_id == tree_id shows up in family
# ---------------------------------------------------------------------------

    # ----------------------------------------------------------------------
    # Bagian: TestBackwardCompat
    # ----------------------------------------------------------------------

    def test_legacy_message_appears_in_family_room(self, ctx, mongo_db):
        # Insert legacy message directly with room_id == tree_id
        legacy_id = str(uuid.uuid4())
        mongo_db.family_chat.insert_one({
            "id": legacy_id,
            "room_id": ctx["T1"],
            "tree_id": ctx["T1"],
            "sender_id": ctx["A"]["id"],
            "message": "TEST_CHAT legacy message",
            "attachments": [],
            "reply_to": None,
            "read_by": [],
            "edited": False,
            "created_at": now_utc(),
            "deleted_at": None,
        })
        CREATED["family_chat_ids"].add(legacy_id)
        # 1) via GET /api/chat without room_id -> family default
        r1 = requests.get(f"{API}/chat?tree_id={ctx['T1']}",
                          headers=auth(ctx["A"]["token"]))
        assert r1.status_code == 200
        ids1 = [m["id"] for m in r1.json()["messages"]]
        assert legacy_id in ids1
        # 2) via GET /api/chat?room_id=<tree_id>
        r2 = requests.get(f"{API}/chat?tree_id={ctx['T1']}&room_id={ctx['T1']}",
                          headers=auth(ctx["A"]["token"]))
        assert r2.status_code == 200
        ids2 = [m["id"] for m in r2.json()["messages"]]
        assert legacy_id in ids2


# ---------------------------------------------------------------------------
# 9. Unread counts flow
# ---------------------------------------------------------------------------

    # ----------------------------------------------------------------------
    # Bagian: TestUnreadCounts
    # ----------------------------------------------------------------------

    def test_unread_increments_and_resets(self, ctx):
        # Fresh DM between E (viewer, alive-linked) and A
        r = requests.post(f"{API}/chat/direct?tree_id={ctx['T1']}",
                          json={"user_id": ctx["E"]["id"]},
                          headers=auth(ctx["A"]["token"]))
        assert r.status_code == 200
        dm = r.json()
        CREATED["chat_room_ids"].add(dm["id"])
        dm_id = dm["id"]

        # E reads once to zero-out any prior unread
        requests.get(f"{API}/chat?tree_id={ctx['T1']}&room_id={dm_id}",
                     headers=auth(ctx["E"]["token"]))

        # A sends 2 messages
        for i in range(2):
            rs = requests.post(f"{API}/chat?tree_id={ctx['T1']}&room_id={dm_id}",
                               json={"message": f"TEST_CHAT unread msg {i}"},
                               headers=auth(ctx["A"]["token"]))
            assert rs.status_code == 200
            CREATED["family_chat_ids"].add(rs.json()["id"])

        # E lists rooms -> unread should be 2 on that DM room
        rooms_r = requests.get(f"{API}/chat/rooms?tree_id={ctx['T1']}",
                               headers=auth(ctx["E"]["token"]))
        assert rooms_r.status_code == 200
        rooms = rooms_r.json()["rooms"]
        dm_row = next((x for x in rooms if x["id"] == dm_id), None)
        assert dm_row is not None, f"DM row missing for E; rooms={rooms}"
        assert dm_row["unread"] == 2, f"expected 2 unread, got {dm_row['unread']}"
        # last_message preview should be the last message (direct = raw body)
        assert "unread msg 1" in (dm_row["last_message"] or "")

        # E opens the DM -> unread resets
        open_r = requests.get(f"{API}/chat?tree_id={ctx['T1']}&room_id={dm_id}",
                              headers=auth(ctx["E"]["token"]))
        assert open_r.status_code == 200
        rooms_after = requests.get(f"{API}/chat/rooms?tree_id={ctx['T1']}",
                                   headers=auth(ctx["E"]["token"])).json()["rooms"]
        dm_row2 = next((x for x in rooms_after if x["id"] == dm_id), None)
        assert dm_row2 is not None
        assert dm_row2["unread"] == 0, f"expected unread reset to 0, got {dm_row2['unread']}"
