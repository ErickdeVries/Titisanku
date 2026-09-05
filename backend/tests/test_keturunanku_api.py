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

from conftest import auth, BASE_URL


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
