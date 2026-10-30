"""
Isolated backend tests for iteration 13:
- Chat photo upload (POST /api/upload with image + POST /api/chat with attachments)
- In-app Notification Inbox (GET /api/notifications, POST /api/notifications/read)
- Emergent-managed Push Notification relay (POST /api/register-push)
- Chat push integration is NON-BLOCKING (send_chat still returns 200 even if push relay fails)
- @mention creates 'mention' app_notification for the mentioned user

CRITICAL DATA SAFETY:
- All synthetic ids/emails prefixed with `TESTPUSH_`.
- We NEVER call delete_many({}) on any shared collection.
- Teardown deletes ONLY the exact synthetic docs by id.
- Real trees (tree_87087dfe29e9, tree_6ce491402c6a) are NOT touched.
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

BASE_URL = (
    os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or os.environ.get("EXPO_BACKEND_URL")
    or "http://localhost:8001"
).rstrip("/")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

PREFIX = "TESTPUSH_"


def now_utc():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Isolated synthetic seed
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def seeded():
    c = MongoClient(MONGO_URL)
    db = c[DB_NAME]

    admin_id = f"{PREFIX}user_admin_{uuid.uuid4().hex[:8]}"
    editor_id = f"{PREFIX}user_editor_{uuid.uuid4().hex[:8]}"
    viewer_id = f"{PREFIX}user_viewer_{uuid.uuid4().hex[:8]}"
    admin_email = f"{PREFIX}admin_{uuid.uuid4().hex[:6]}@example.com"
    editor_email = f"{PREFIX}editor_{uuid.uuid4().hex[:6]}@example.com"
    viewer_email = f"{PREFIX}viewer_{uuid.uuid4().hex[:6]}@example.com"

    tree_id = f"{PREFIX}tree_{uuid.uuid4().hex[:8]}"
    admin_token = f"{PREFIX}tok_admin_{secrets.token_hex(8)}"
    editor_token = f"{PREFIX}tok_editor_{secrets.token_hex(8)}"
    viewer_token = f"{PREFIX}tok_viewer_{secrets.token_hex(8)}"

    # Users
    users = [
        {"user_id": admin_id, "email": admin_email, "name": f"{PREFIX}Admin", "picture": None, "role": "admin", "created_at": now_utc()},
        {"user_id": editor_id, "email": editor_email, "name": f"{PREFIX}Editor", "picture": None, "role": "viewer", "created_at": now_utc()},
        {"user_id": viewer_id, "email": viewer_email, "name": f"{PREFIX}Viewer", "picture": None, "role": "viewer", "created_at": now_utc()},
    ]
    db.users.insert_many(users)

    # Sessions
    sess = [
        {"session_token": admin_token, "user_id": admin_id, "created_at": now_utc(), "expires_at": now_utc() + timedelta(days=7)},
        {"session_token": editor_token, "user_id": editor_id, "created_at": now_utc(), "expires_at": now_utc() + timedelta(days=7)},
        {"session_token": viewer_token, "user_id": viewer_id, "created_at": now_utc(), "expires_at": now_utc() + timedelta(days=7)},
    ]
    db.user_sessions.insert_many(sess)

    # Tree
    db.trees.insert_one({
        "id": tree_id,
        "name": f"{PREFIX}Tree",
        "owner_id": admin_id,
        "plan": "free",
        "is_public": False,
        "root_person_id": None,
        "created_at": now_utc(),
    })
    # Tree members (per-tree roles)
    tm_ids = []
    for uid, role in [(admin_id, "admin"), (editor_id, "editor"), (viewer_id, "viewer")]:
        _id = f"{PREFIX}tm_{uuid.uuid4().hex[:8]}"
        tm_ids.append(_id)
        db.tree_members.insert_one({
            "id": _id, "tree_id": tree_id, "user_id": uid, "role": role, "joined_at": now_utc(),
        })

    ctx = {
        "tree_id": tree_id,
        "admin": {"id": admin_id, "token": admin_token, "email": admin_email},
        "editor": {"id": editor_id, "token": editor_token, "email": editor_email},
        "viewer": {"id": viewer_id, "token": viewer_token, "email": viewer_email},
        "user_ids": [admin_id, editor_id, viewer_id],
        "tokens": [admin_token, editor_token, viewer_token],
        "emails": [admin_email, editor_email, viewer_email],
        "tm_ids": tm_ids,
    }

    yield ctx

    # ---- Teardown: delete ONLY our synthetic docs by exact id ----
    db.users.delete_many({"user_id": {"$in": ctx["user_ids"]}})
    db.user_sessions.delete_many({"session_token": {"$in": ctx["tokens"]}})
    db.trees.delete_one({"id": tree_id})
    db.tree_members.delete_many({"id": {"$in": tm_ids}})
    # Anything created BY the test in these collections is scoped to our synthetic tree_id
    db.family_chat.delete_many({"tree_id": tree_id})
    db.app_notifications.delete_many({"tree_id": tree_id})
    db.app_notifications.delete_many({"user_id": {"$in": ctx["user_ids"]}})
    db.chat_rooms.delete_many({"tree_id": tree_id})
    db.chat_typing.delete_many({"user_id": {"$in": ctx["user_ids"]}})
    db.chat_mutes.delete_many({"user_id": {"$in": ctx["user_ids"]}})


def auth(tok):
    return {"Authorization": f"Bearer {tok}"}


# 1x1 PNG (valid image bytes)
PNG_1PX = bytes.fromhex(
    "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4"
    "890000000D49444154789C6360000002000001E221BC330000000049454E44AE426082"
)


# ---------------------------------------------------------------------------
# register-push
# ---------------------------------------------------------------------------
class TestRegisterPush:
    def test_unauth_returns_401(self):
        r = requests.post(
            f"{BASE_URL}/api/register-push",
            json={"platform": "ios", "device_token": "abc123"},
            timeout=15,
        )
        assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"

    def test_auth_route_registered_not_404(self, seeded):
        r = requests.post(
            f"{BASE_URL}/api/register-push",
            json={"platform": "ios", "device_token": f"{PREFIX}devicetoken"},
            headers=auth(seeded["admin"]["token"]),
            timeout=20,
        )
        # Route MUST be registered. With placeholder key it's expected to be 500/502.
        # 201 is also acceptable if the upstream accepts placeholder.
        assert r.status_code != 404, f"register-push route should be registered, got 404: {r.text}"
        assert r.status_code in (201, 500, 502), f"Unexpected status {r.status_code}: {r.text}"


# ---------------------------------------------------------------------------
# Upload + Chat photo flow
# ---------------------------------------------------------------------------
class TestUploadAndChatPhoto:
    def test_upload_image_returns_path_and_url(self, seeded):
        r = requests.post(
            f"{BASE_URL}/api/upload",
            params={"tree_id": seeded["tree_id"]},
            headers=auth(seeded["admin"]["token"]),
            files={"file": ("test.png", io.BytesIO(PNG_1PX), "image/png")},
            timeout=60,
        )
        assert r.status_code == 200, f"Upload failed: {r.status_code} {r.text}"
        data = r.json()
        assert "path" in data and data["path"], data
        # `path` selalu path API yang bisa dipakai ulang oleh klien; `url` boleh
        # berupa URL absolut (Firebase Storage) atau path relatif /api/files/.
        assert data["path"].startswith("/api/files/"), data
        assert "url" in data and data["url"], data
        assert data["url"].startswith(("http://", "https://", "/api/files/")), data
        # Save for chat test
        pytest.uploaded_path = data["path"]

    def test_chat_with_attachments_returns_200(self, seeded):
        path = getattr(pytest, "uploaded_path", f"{PREFIX}fake/path.jpg")
        r = requests.post(
            f"{BASE_URL}/api/chat",
            params={"tree_id": seeded["tree_id"], "room_id": seeded["tree_id"]},
            headers=auth(seeded["admin"]["token"]),
            json={"message": "TESTPUSH photo", "attachments": [path]},
            timeout=30,
        )
        assert r.status_code == 200, f"chat send failed: {r.status_code} {r.text}"
        msg = r.json()
        assert msg.get("attachments") == [path]
        assert msg.get("sender_id") == seeded["admin"]["id"]

    def test_send_chat_is_non_blocking_when_push_fails(self, seeded):
        """Push relay uses EMERGENT_PUSH_KEY=placeholder → upstream fails.
        Chat send MUST still return 200 (regression check)."""
        r = requests.post(
            f"{BASE_URL}/api/chat",
            params={"tree_id": seeded["tree_id"], "room_id": seeded["tree_id"]},
            headers=auth(seeded["editor"]["token"]),
            json={"message": "TESTPUSH regression non-blocking"},
            timeout=30,
        )
        assert r.status_code == 200, f"send_chat should not fail when push fails: {r.status_code} {r.text}"


# ---------------------------------------------------------------------------
# Notifications inbox
# ---------------------------------------------------------------------------
class TestNotificationsInbox:
    def test_get_notifications_shape(self, seeded):
        r = requests.get(
            f"{BASE_URL}/api/notifications",
            headers=auth(seeded["editor"]["token"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert set(["unread", "unread_chat", "items"]).issubset(d.keys()), d
        assert isinstance(d["items"], list)
        assert isinstance(d["unread"], int)
        assert isinstance(d["unread_chat"], int)

    def test_editor_received_chat_notification_from_admin(self, seeded):
        # Admin already sent a chat message in TestUploadAndChatPhoto; editor should see a
        # 'chat' notification created.
        r = requests.get(
            f"{BASE_URL}/api/notifications",
            headers=auth(seeded["editor"]["token"]),
            timeout=15,
        )
        d = r.json()
        chat_items = [i for i in d["items"] if i.get("type") == "chat" and i.get("tree_id") == seeded["tree_id"]]
        assert len(chat_items) >= 1, f"editor should have >=1 chat notification, got {d}"
        assert d["unread_chat"] >= 1

    def test_mark_read_type_chat_zeroes_unread_chat(self, seeded):
        r = requests.post(
            f"{BASE_URL}/api/notifications/read",
            params={"type": "chat"},
            headers=auth(seeded["editor"]["token"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        # Verify via GET
        r2 = requests.get(
            f"{BASE_URL}/api/notifications",
            headers=auth(seeded["editor"]["token"]),
            timeout=15,
        )
        d = r2.json()
        assert d["unread_chat"] == 0, f"unread_chat should be 0 after read, got {d['unread_chat']}"


# ---------------------------------------------------------------------------
# @mention creates notification
# ---------------------------------------------------------------------------
class TestMentionNotification:
    def test_mention_creates_mention_notification(self, seeded):
        # Admin mentions editor2 (use viewer id here – mention target)
        target_uid = seeded["viewer"]["id"]
        r = requests.post(
            f"{BASE_URL}/api/chat",
            params={"tree_id": seeded["tree_id"], "room_id": seeded["tree_id"]},
            headers=auth(seeded["admin"]["token"]),
            json={"message": f"TESTPUSH @mention hi", "mentions": [target_uid]},
            timeout=30,
        )
        assert r.status_code == 200, f"chat with mention failed: {r.status_code} {r.text}"

        # Verify mention notification exists for the target user
        r2 = requests.get(
            f"{BASE_URL}/api/notifications",
            headers=auth(seeded["viewer"]["token"]),
            timeout=15,
        )
        assert r2.status_code == 200, r2.text
        d = r2.json()
        mentions = [i for i in d["items"] if i.get("type") == "mention" and i.get("tree_id") == seeded["tree_id"]]
        assert len(mentions) >= 1, f"expected a mention notification, got items={d['items']}"
        assert "menyebut" in (mentions[0].get("body") or "").lower() or "@" in (mentions[0].get("body") or "")
