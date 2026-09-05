"""KETURUNANKU backend API tests.

Covers:
- Auth (/auth/me)
- Tree with note_count
- People CRUD + add-relative
- Person notes (RBAC + persistence + notification fan-out)
- Person files (multipart -> creates person_notes entry)
- Family chat (RBAC + room_id/room_name + reply snapshot)
- Notifications (fan-out, actor exclusion, unread_chat, read-marking)
- Backup, restore, invite
"""
import io
import uuid
import requests

from conftest import auth, BASE_URL, now_utc


API = f"{BASE_URL}/api"


# ---------- Auth ----------
class TestAuth:
    def test_me_admin(self, seeded):
        r = requests.get(f"{API}/auth/me", headers=auth(seeded["admin"]["token"]))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["role"] == "admin"
        assert data["user_id"] == seeded["admin"]["id"]

    def test_me_missing_token(self):
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401

    def test_me_bad_token(self):
        r = requests.get(f"{API}/auth/me", headers={"Authorization": "Bearer NOTATOKEN"})
        assert r.status_code == 401


# ---------- Tree ----------
class TestTree:
    def test_tree_returns_root_and_note_count(self, seeded):
        r = requests.get(f"{API}/tree", headers=auth(seeded["admin"]["token"]))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["root_id"] == seeded["root_person_id"]
        assert isinstance(data["people"], list)
        assert len(data["people"]) >= 1
        for p in data["people"]:
            assert "note_count" in p
            assert isinstance(p["note_count"], int)


# ---------- People ----------
class TestPeople:
    def test_add_relative_editor(self, seeded):
        payload = {
            "focus_id": seeded["root_person_id"],
            "direction": "child",
            "person": {"name": "TEST_Child", "gender": "male", "is_adopted": False},
        }
        r = requests.post(f"{API}/people/add-relative", json=payload,
                          headers=auth(seeded["editor"]["token"]))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["person"]["name"] == "TEST_Child"
        seeded["child_id"] = data["person"]["id"]

    def test_add_relative_viewer_forbidden(self, seeded):
        payload = {
            "focus_id": seeded["root_person_id"],
            "direction": "child",
            "person": {"name": "TEST_ChildFromViewer"},
        }
        r = requests.post(f"{API}/people/add-relative", json=payload,
                          headers=auth(seeded["viewer"]["token"]))
        assert r.status_code == 403

    def test_update_person_editor(self, seeded):
        # relies on child from prior test
        assert "child_id" in seeded
        r = requests.put(
            f"{API}/people/{seeded['child_id']}",
            json={"name": "TEST_Child_Renamed", "gender": "male"},
            headers=auth(seeded["editor"]["token"]),
        )
        assert r.status_code == 200
        assert r.json()["name"] == "TEST_Child_Renamed"

    def test_delete_person_viewer_forbidden(self, seeded):
        r = requests.delete(f"{API}/people/{seeded['child_id']}",
                            headers=auth(seeded["viewer"]["token"]))
        assert r.status_code == 403

    def test_delete_root_forbidden(self, seeded):
        r = requests.delete(f"{API}/people/{seeded['root_person_id']}",
                            headers=auth(seeded["admin"]["token"]))
        assert r.status_code == 400


# ---------- Person notes ----------
class TestPersonNotes:
    def test_viewer_cannot_add_note(self, seeded):
        r = requests.post(
            f"{API}/people/{seeded['root_person_id']}/notes",
            json={"note_text": "TEST viewer attempt"},
            headers=auth(seeded["viewer"]["token"]),
        )
        assert r.status_code == 403

    def test_editor_add_note_and_notification_fanout(self, seeded, mongo_db):
        # Clear notifications so we can assert fan-out precisely
        mongo_db.app_notifications.delete_many({})
        r = requests.post(
            f"{API}/people/{seeded['root_person_id']}/notes",
            json={"note_text": "TEST note by editor"},
            headers=auth(seeded["editor"]["token"]),
        )
        assert r.status_code == 200, r.text
        note = r.json()
        assert note["author_name"].startswith("TEST_editor") or "editor" in note["author_name"]
        assert note["note_text"] == "TEST note by editor"
        assert note["person_id"] == seeded["root_person_id"]

        # Fan-out: admin + editor2 receive; the actor (editor) does NOT
        notif_ids = list(mongo_db.app_notifications.find({"type": "note"}))
        recipients = {n["user_id"] for n in notif_ids}
        assert seeded["admin"]["id"] in recipients
        assert seeded["editor2"]["id"] in recipients
        assert seeded["editor"]["id"] not in recipients  # actor excluded
        assert seeded["viewer"]["id"] not in recipients  # viewer not in fan-out

    def test_list_notes_returns_author_name(self, seeded):
        r = requests.get(
            f"{API}/people/{seeded['root_person_id']}/notes",
            headers=auth(seeded["viewer"]["token"]),  # viewer can read
        )
        assert r.status_code == 200, r.text
        notes = r.json()
        assert isinstance(notes, list) and len(notes) >= 1
        assert "author_name" in notes[0]

    def test_tree_note_count_reflects_notes(self, seeded):
        r = requests.get(f"{API}/tree", headers=auth(seeded["admin"]["token"]))
        assert r.status_code == 200
        for p in r.json()["people"]:
            if p["id"] == seeded["root_person_id"]:
                assert p["note_count"] >= 1
                return
        raise AssertionError("Root person not found in tree")


# ---------- Person files ----------
class TestPersonFiles:
    def test_viewer_cannot_upload_file(self, seeded):
        r = requests.post(
            f"{API}/people/{seeded['root_person_id']}/files",
            files={"file": ("test.txt", io.BytesIO(b"hi"), "text/plain")},
            headers=auth(seeded["viewer"]["token"]),
        )
        assert r.status_code == 403

    def test_editor_upload_creates_note_with_attachment(self, seeded):
        r = requests.post(
            f"{API}/people/{seeded['root_person_id']}/files",
            files={"file": ("TEST_file.txt", io.BytesIO(b"hello world"), "text/plain")},
            headers=auth(seeded["editor"]["token"]),
        )
        # Storage backend may be unreachable — surface that clearly
        if r.status_code >= 500:
            import pytest
            pytest.skip(f"Object storage unavailable (status={r.status_code}): {r.text[:200]}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["attachments"] and len(data["attachments"]) == 1
        assert data["person_id"] == seeded["root_person_id"]


# ---------- Family chat ----------
class TestChat:
    def test_get_chat_room_id_and_name(self, seeded):
        r = requests.get(f"{API}/chat", headers=auth(seeded["viewer"]["token"]))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["room_id"] == seeded["admin"]["id"]  # room_id == admin user_id
        assert data["room_name"] == seeded["admin"]["name"]  # room_name == admin name
        assert isinstance(data["messages"], list)

    def test_viewer_cannot_send(self, seeded):
        r = requests.post(f"{API}/chat", json={"message": "TEST from viewer"},
                          headers=auth(seeded["viewer"]["token"]))
        assert r.status_code == 403

    def test_admin_and_editor_can_send(self, seeded, mongo_db):
        mongo_db.app_notifications.delete_many({"type": "chat"})
        # admin sends
        r1 = requests.post(f"{API}/chat", json={"message": "TEST admin msg"},
                           headers=auth(seeded["admin"]["token"]))
        assert r1.status_code == 200, r1.text
        seeded["admin_msg_id"] = r1.json()["id"]
        # editor sends
        r2 = requests.post(f"{API}/chat", json={"message": "TEST editor msg"},
                           headers=auth(seeded["editor"]["token"]))
        assert r2.status_code == 200

        # Notification fan-out on chat:
        recipients = {n["user_id"] for n in mongo_db.app_notifications.find({"type": "chat"})}
        # From admin's post: editor & editor2 notified (admin excluded)
        # From editor's post: admin & editor2 notified (editor excluded)
        assert seeded["editor2"]["id"] in recipients
        assert seeded["admin"]["id"] in recipients  # notified for editor's post
        assert seeded["editor"]["id"] in recipients  # notified for admin's post
        # Viewer should not receive chat notifications (only admin/editor)
        assert seeded["viewer"]["id"] not in recipients

    def test_empty_message_rejected(self, seeded):
        r = requests.post(f"{API}/chat", json={"message": "  ", "attachments": []},
                          headers=auth(seeded["editor"]["token"]))
        assert r.status_code == 400

    def test_reply_snapshot(self, seeded):
        assert "admin_msg_id" in seeded
        r = requests.post(
            f"{API}/chat",
            json={"message": "TEST reply", "reply_to": seeded["admin_msg_id"]},
            headers=auth(seeded["editor"]["token"]),
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["reply_to"] is not None
        assert data["reply_to"]["sender_name"] == seeded["admin"]["name"]
        assert data["reply_to"]["message"] == "TEST admin msg"

    def test_chat_get_enriches_sender(self, seeded):
        r = requests.get(f"{API}/chat", headers=auth(seeded["admin"]["token"]))
        assert r.status_code == 200
        msgs = r.json()["messages"]
        assert len(msgs) >= 2
        for m in msgs:
            assert "sender_name" in m
            assert "sender_picture" in m


# ---------- Notifications ----------
class TestNotifications:
    def test_editor_has_unread_chat(self, seeded):
        r = requests.get(f"{API}/notifications", headers=auth(seeded["editor"]["token"]))
        assert r.status_code == 200
        data = r.json()
        assert data["unread"] >= 1
        # editor received chat notif from admin's post
        assert data["unread_chat"] >= 1
        assert isinstance(data["items"], list)

    def test_mark_chat_read(self, seeded):
        r = requests.post(f"{API}/notifications/read?type=chat",
                          headers=auth(seeded["editor"]["token"]))
        assert r.status_code == 200
        r2 = requests.get(f"{API}/notifications", headers=auth(seeded["editor"]["token"]))
        data = r2.json()
        assert data["unread_chat"] == 0
        # Non-chat unread (e.g. 'note') may remain

    def test_viewer_has_no_notifications(self, seeded):
        r = requests.get(f"{API}/notifications", headers=auth(seeded["viewer"]["token"]))
        assert r.status_code == 200
        data = r.json()
        assert data["unread"] == 0


# ---------- Backup / Restore / Invite ----------
class TestBackupInvite:
    def test_backup_admin_only(self, seeded):
        r = requests.get(f"{API}/backup", headers=auth(seeded["editor"]["token"]))
        assert r.status_code == 403
        r2 = requests.get(f"{API}/backup", headers=auth(seeded["admin"]["token"]))
        assert r2.status_code == 200
        data = r2.json()
        assert "people" in data and "relations" in data and "users" in data

    def test_restore_admin(self, seeded, mongo_db):
        # Get current backup, then restore it (no-op essentially)
        b = requests.get(f"{API}/backup", headers=auth(seeded["admin"]["token"])).json()
        r = requests.post(f"{API}/restore",
                          json={"people": b["people"], "relations": b["relations"]},
                          headers=auth(seeded["admin"]["token"]))
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_invite_admin_only(self, seeded):
        r = requests.post(f"{API}/invite",
                          json={"email": "delivered@resend.dev"},
                          headers=auth(seeded["viewer"]["token"]))
        assert r.status_code == 403
        r2 = requests.post(f"{API}/invite",
                           json={"email": "delivered@resend.dev"},
                           headers=auth(seeded["admin"]["token"]))
        assert r2.status_code == 200, r2.text
        data = r2.json()
        assert "code" in data and len(data["code"]) >= 6


# ---------- NEW FEATURES: Chat filters (is_alive annotation, room_name, members, counts) ----------
class TestChatFilters:
    """New in this iteration: sender_is_alive/sender_person_id via email-join,
    alive_count, total_count, room_name (=admin.name), members(admin+editors)."""

    def test_chat_annotates_sender_is_alive_and_person_id(self, seeded, mongo_db):
        # Ensure at least one message from admin (alive) and one from editor2 (dead by seeding)
        mongo_db.family_chat.delete_many({})
        r_admin = requests.post(f"{API}/chat", json={"message": "TEST alive admin"},
                                headers=auth(seeded["admin"]["token"]))
        assert r_admin.status_code == 200, r_admin.text
        r_ed2 = requests.post(f"{API}/chat", json={"message": "TEST dead editor2"},
                              headers=auth(seeded["editor2"]["token"]))
        assert r_ed2.status_code == 200, r_ed2.text

        r = requests.get(f"{API}/chat", headers=auth(seeded["admin"]["token"]))
        assert r.status_code == 200
        data = r.json()
        # room_name = admin.name; members includes admin + both editors (not viewer)
        assert data["room_name"] == seeded["admin"]["name"]
        member_ids = {m["user_id"] for m in data["members"]}
        assert seeded["admin"]["id"] in member_ids
        assert seeded["editor"]["id"] in member_ids
        assert seeded["editor2"]["id"] in member_ids
        assert seeded["viewer"]["id"] not in member_ids

        # total_count >= 3 (root + editor + editor2 seeded); alive_count = total - 1 (editor2 dead)
        assert data["total_count"] >= 3
        assert data["alive_count"] == data["total_count"] - 1

        # per-message annotation
        by_sender = {m["sender_id"]: m for m in data["messages"]}
        assert by_sender[seeded["admin"]["id"]]["sender_is_alive"] is True
        assert by_sender[seeded["admin"]["id"]]["sender_person_id"] == seeded["root_person_id"]
        assert by_sender[seeded["editor2"]["id"]]["sender_is_alive"] is False
        assert by_sender[seeded["editor2"]["id"]]["sender_person_id"] == seeded["editor2"]["person_id"]


# ---------- NEW FEATURES: Read receipts ----------
class TestReadReceipts:
    def test_read_by_populated_when_other_user_fetches(self, seeded, mongo_db):
        mongo_db.family_chat.delete_many({})
        r = requests.post(f"{API}/chat", json={"message": "TEST read receipt"},
                          headers=auth(seeded["admin"]["token"]))
        assert r.status_code == 200
        msg_id = r.json()["id"]

        # editor fetches chat -> should mark admin's message as read by editor
        r_get = requests.get(f"{API}/chat", headers=auth(seeded["editor"]["token"]))
        assert r_get.status_code == 200

        # Now admin fetches — should see editor's user_id in own message read_by
        r_admin = requests.get(f"{API}/chat", headers=auth(seeded["admin"]["token"]))
        assert r_admin.status_code == 200
        msgs = {m["id"]: m for m in r_admin.json()["messages"]}
        assert msg_id in msgs
        assert seeded["editor"]["id"] in msgs[msg_id]["read_by"]

    def test_read_by_does_not_include_self(self, seeded, mongo_db):
        mongo_db.family_chat.delete_many({})
        r = requests.post(f"{API}/chat", json={"message": "TEST self read"},
                          headers=auth(seeded["admin"]["token"]))
        msg_id = r.json()["id"]
        # Admin re-fetches; should not add self to read_by
        r_admin = requests.get(f"{API}/chat", headers=auth(seeded["admin"]["token"]))
        msgs = {m["id"]: m for m in r_admin.json()["messages"]}
        assert seeded["admin"]["id"] not in msgs[msg_id]["read_by"]


# ---------- NEW FEATURES: Mentions ----------
class TestMentions:
    def test_mention_creates_notification(self, seeded, mongo_db):
        mongo_db.app_notifications.delete_many({"type": "mention"})
        r = requests.post(
            f"{API}/chat",
            json={"message": "TEST @editor2", "mentions": [seeded["editor2"]["id"]]},
            headers=auth(seeded["admin"]["token"]),
        )
        assert r.status_code == 200, r.text
        notifs = list(mongo_db.app_notifications.find({"type": "mention"}))
        assert len(notifs) == 1
        assert notifs[0]["user_id"] == seeded["editor2"]["id"]

        # GET /notifications for editor2 shows the mention
        r2 = requests.get(f"{API}/notifications", headers=auth(seeded["editor2"]["token"]))
        assert r2.status_code == 200
        types = [n["type"] for n in r2.json()["items"]]
        assert "mention" in types

    def test_mention_self_ignored_and_normal_fanout_still_works(self, seeded, mongo_db):
        mongo_db.app_notifications.delete_many({})
        r = requests.post(
            f"{API}/chat",
            json={"message": "TEST self mention", "mentions": [seeded["admin"]["id"]]},
            headers=auth(seeded["admin"]["token"]),
        )
        assert r.status_code == 200
        # No mention notification for self
        assert mongo_db.app_notifications.count_documents(
            {"type": "mention", "user_id": seeded["admin"]["id"]}
        ) == 0
        # Chat fan-out to editors still happens
        chat_recipients = {
            n["user_id"]
            for n in mongo_db.app_notifications.find({"type": "chat"})
        }
        assert seeded["editor"]["id"] in chat_recipients
        assert seeded["editor2"]["id"] in chat_recipients


# ---------- NEW FEATURES: DELETE /api/notes/{id} ----------
class TestDeleteNote:
    def _create_note(self, seeded, token):
        r = requests.post(
            f"{API}/people/{seeded['root_person_id']}/notes",
            json={"note_text": "TEST delete me"},
            headers=auth(token),
        )
        assert r.status_code == 200, r.text
        return r.json()["id"]

    def test_author_can_delete(self, seeded):
        note_id = self._create_note(seeded, seeded["editor"]["token"])
        r = requests.delete(f"{API}/notes/{note_id}", headers=auth(seeded["editor"]["token"]))
        assert r.status_code == 200
        # 404 on delete again
        r2 = requests.delete(f"{API}/notes/{note_id}", headers=auth(seeded["editor"]["token"]))
        assert r2.status_code == 404

    def test_non_author_non_admin_forbidden(self, seeded):
        note_id = self._create_note(seeded, seeded["editor"]["token"])
        # editor2 is neither author nor admin
        r = requests.delete(f"{API}/notes/{note_id}", headers=auth(seeded["editor2"]["token"]))
        assert r.status_code == 403

    def test_admin_can_delete_anyones_note(self, seeded):
        note_id = self._create_note(seeded, seeded["editor"]["token"])
        r = requests.delete(f"{API}/notes/{note_id}", headers=auth(seeded["admin"]["token"]))
        assert r.status_code == 200

    def test_delete_missing_returns_404(self, seeded):
        r = requests.delete(f"{API}/notes/does-not-exist", headers=auth(seeded["admin"]["token"]))
        assert r.status_code == 404


# ---------- NEW FEATURES: is_alive auto + override ----------
class TestIsAlive:
    def test_put_person_death_date_auto_is_alive_false(self, seeded):
        # create a person via add-relative
        r = requests.post(
            f"{API}/people/add-relative",
            json={
                "focus_id": seeded["root_person_id"],
                "direction": "child",
                "person": {"name": "TEST_IA_Child"},
            },
            headers=auth(seeded["admin"]["token"]),
        )
        assert r.status_code == 200
        pid = r.json()["person"]["id"]

        r2 = requests.put(
            f"{API}/people/{pid}",
            json={"name": "TEST_IA_Child", "death_date": "2010-05-05"},
            headers=auth(seeded["admin"]["token"]),
        )
        assert r2.status_code == 200
        assert r2.json()["is_alive"] is False

    def test_put_person_explicit_is_alive_override(self, seeded):
        r = requests.post(
            f"{API}/people/add-relative",
            json={
                "focus_id": seeded["root_person_id"],
                "direction": "child",
                "person": {"name": "TEST_IA_Override"},
            },
            headers=auth(seeded["admin"]["token"]),
        )
        assert r.status_code == 200
        pid = r.json()["person"]["id"]

        r2 = requests.put(
            f"{API}/people/{pid}",
            json={
                "name": "TEST_IA_Override",
                "death_date": "2010-05-05",
                "is_alive": True,  # override: keep alive despite death_date
            },
            headers=auth(seeded["admin"]["token"]),
        )
        assert r2.status_code == 200
        assert r2.json()["is_alive"] is True

    def test_add_relative_death_date_sets_is_alive_false(self, seeded):
        r = requests.post(
            f"{API}/people/add-relative",
            json={
                "focus_id": seeded["root_person_id"],
                "direction": "child",
                "person": {"name": "TEST_IA_Dead", "death_date": "2000-01-01"},
            },
            headers=auth(seeded["admin"]["token"]),
        )
        assert r.status_code == 200
        person = r.json()["person"]
        assert person["is_alive"] is False

    def test_tree_returns_is_alive_per_person(self, seeded):
        r = requests.get(f"{API}/tree", headers=auth(seeded["admin"]["token"]))
        assert r.status_code == 200
        for p in r.json()["people"]:
            assert "is_alive" in p
            assert isinstance(p["is_alive"], bool)
        # editor2's seeded person should be is_alive=False
        by_id = {p["id"]: p for p in r.json()["people"]}
        assert by_id[seeded["editor2"]["person_id"]]["is_alive"] is False
        assert by_id[seeded["editor"]["person_id"]]["is_alive"] is True


# ---------- REPORTED BUG: Persistence across write endpoints (Create -> GET) ----------
class TestPersistence:
    """Reported bug: 'preview cannot save input data'. Verify each write endpoint
    persists AND survives a subsequent GET (i.e., data actually stored in DB)."""

    def test_add_relative_persists_in_tree(self, seeded):
        unique = f"TEST_Persist_{uuid.uuid4().hex[:6]}"
        r = requests.post(
            f"{API}/people/add-relative",
            json={
                "focus_id": seeded["root_person_id"],
                "direction": "child",
                "person": {"name": unique, "gender": "male"},
            },
            headers=auth(seeded["admin"]["token"]),
        )
        assert r.status_code == 200, r.text
        new_id = r.json()["person"]["id"]
        # GET /tree must contain the new person
        tree = requests.get(f"{API}/tree", headers=auth(seeded["admin"]["token"])).json()
        names = {p["id"]: p["name"] for p in tree["people"]}
        assert new_id in names
        assert names[new_id] == unique
        # relation persisted too
        rel_ids = {r_["person_id"] for r_ in tree["relations"]}
        rel_ids |= {r_["related_person_id"] for r_ in tree["relations"]}
        assert new_id in rel_ids

    def test_update_person_persists(self, seeded):
        r = requests.post(
            f"{API}/people/add-relative",
            json={
                "focus_id": seeded["root_person_id"],
                "direction": "child",
                "person": {"name": "TEST_ToUpdate"},
            },
            headers=auth(seeded["admin"]["token"]),
        )
        pid = r.json()["person"]["id"]
        new_name = f"TEST_Updated_{uuid.uuid4().hex[:6]}"
        r2 = requests.put(
            f"{API}/people/{pid}",
            json={"name": new_name, "gender": "female", "birth_place": "Jakarta"},
            headers=auth(seeded["admin"]["token"]),
        )
        assert r2.status_code == 200
        # GET back
        r3 = requests.get(f"{API}/people/{pid}", headers=auth(seeded["admin"]["token"]))
        assert r3.status_code == 200
        got = r3.json()
        assert got["name"] == new_name
        assert got["gender"] == "female"
        assert got["birth_place"] == "Jakarta"

    def test_note_persists_in_list(self, seeded):
        text = f"TEST_Persist_Note_{uuid.uuid4().hex[:6]}"
        r = requests.post(
            f"{API}/people/{seeded['root_person_id']}/notes",
            json={"note_text": text},
            headers=auth(seeded["admin"]["token"]),
        )
        assert r.status_code == 200
        note_id = r.json()["id"]
        r2 = requests.get(
            f"{API}/people/{seeded['root_person_id']}/notes",
            headers=auth(seeded["admin"]["token"]),
        )
        assert r2.status_code == 200
        found = [n for n in r2.json() if n["id"] == note_id]
        assert found and found[0]["note_text"] == text

    def test_chat_message_persists(self, seeded, mongo_db):
        mongo_db.family_chat.delete_many({})
        text = f"TEST_Persist_Chat_{uuid.uuid4().hex[:6]}"
        r = requests.post(
            f"{API}/chat",
            json={"message": text},
            headers=auth(seeded["admin"]["token"]),
        )
        assert r.status_code == 200
        msg_id = r.json()["id"]
        r2 = requests.get(f"{API}/chat", headers=auth(seeded["admin"]["token"]))
        assert r2.status_code == 200
        ids = [m["id"] for m in r2.json()["messages"]]
        assert msg_id in ids


# ---------- NEW FEATURES: DELETE /api/chat/{id} ----------
class TestDeleteChat:
    def _send(self, seeded, token, text="TEST delete-chat"):
        r = requests.post(f"{API}/chat", json={"message": text}, headers=auth(token))
        assert r.status_code == 200, r.text
        return r.json()["id"]

    def test_sender_can_delete_own(self, seeded, mongo_db):
        mongo_db.family_chat.delete_many({})
        mid = self._send(seeded, seeded["editor"]["token"], "TEST own-msg")
        r = requests.delete(f"{API}/chat/{mid}", headers=auth(seeded["editor"]["token"]))
        assert r.status_code == 200
        # GET no longer contains it
        got = requests.get(f"{API}/chat", headers=auth(seeded["admin"]["token"])).json()
        assert mid not in [m["id"] for m in got["messages"]]

    def test_admin_can_delete_any(self, seeded, mongo_db):
        mongo_db.family_chat.delete_many({})
        mid = self._send(seeded, seeded["editor"]["token"], "TEST admin-delete")
        r = requests.delete(f"{API}/chat/{mid}", headers=auth(seeded["admin"]["token"]))
        assert r.status_code == 200
        got = requests.get(f"{API}/chat", headers=auth(seeded["admin"]["token"])).json()
        assert mid not in [m["id"] for m in got["messages"]]

    def test_non_sender_non_admin_forbidden(self, seeded, mongo_db):
        mongo_db.family_chat.delete_many({})
        mid = self._send(seeded, seeded["editor"]["token"], "TEST forbidden-delete")
        r = requests.delete(f"{API}/chat/{mid}", headers=auth(seeded["editor2"]["token"]))
        assert r.status_code == 403
        # Still present in GET
        got = requests.get(f"{API}/chat", headers=auth(seeded["admin"]["token"])).json()
        assert mid in [m["id"] for m in got["messages"]]

    def test_delete_nonexistent_returns_404(self, seeded):
        r = requests.delete(f"{API}/chat/does-not-exist", headers=auth(seeded["admin"]["token"]))
        assert r.status_code == 404

    def test_delete_already_deleted_returns_404(self, seeded, mongo_db):
        mongo_db.family_chat.delete_many({})
        mid = self._send(seeded, seeded["editor"]["token"], "TEST double-delete")
        r1 = requests.delete(f"{API}/chat/{mid}", headers=auth(seeded["editor"]["token"]))
        assert r1.status_code == 200
        r2 = requests.delete(f"{API}/chat/{mid}", headers=auth(seeded["admin"]["token"]))
        assert r2.status_code == 404


# ---------- NEW FEATURES: POST /api/chat/typing ----------
class TestChatTyping:
    def test_viewer_forbidden(self, seeded):
        r = requests.post(f"{API}/chat/typing", headers=auth(seeded["viewer"]["token"]))
        assert r.status_code == 403

    def test_editor_typing_appears_for_other_users_not_self(self, seeded, mongo_db):
        mongo_db.chat_typing.delete_many({})
        # editor marks typing
        r = requests.post(f"{API}/chat/typing", headers=auth(seeded["editor"]["token"]))
        assert r.status_code == 200
        # Admin (other user) should see editor in typing
        got_admin = requests.get(f"{API}/chat", headers=auth(seeded["admin"]["token"])).json()
        assert "typing" in got_admin
        # editor's name — look up from users collection
        editor_doc = mongo_db.users.find_one({"user_id": seeded["editor"]["id"]})
        assert editor_doc["name"] in got_admin["typing"]
        # Caller (editor) should NOT see own name in typing
        got_self = requests.get(f"{API}/chat", headers=auth(seeded["editor"]["token"])).json()
        assert editor_doc["name"] not in got_self["typing"]

    def test_admin_typing_visible_to_editor(self, seeded, mongo_db):
        mongo_db.chat_typing.delete_many({})
        r = requests.post(f"{API}/chat/typing", headers=auth(seeded["admin"]["token"]))
        assert r.status_code == 200
        got = requests.get(f"{API}/chat", headers=auth(seeded["editor"]["token"])).json()
        assert seeded["admin"]["name"] in got["typing"]

    def test_typing_expires_after_6s(self, seeded, mongo_db):
        # Insert a stale typing doc (updated 10s ago) and verify it's NOT returned
        from datetime import timedelta
        mongo_db.chat_typing.delete_many({})
        room = seeded["admin"]["id"]
        stale_time = now_utc() - timedelta(seconds=10)
        mongo_db.chat_typing.insert_one({
            "user_id": seeded["editor2"]["id"],
            "name": "TEST_StaleTyper",
            "room_id": room,
            "updated_at": stale_time,
        })
        got = requests.get(f"{API}/chat", headers=auth(seeded["admin"]["token"])).json()
        assert "TEST_StaleTyper" not in got["typing"]
