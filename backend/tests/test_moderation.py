"""Moderasi UGC (blokir + lapor) — App Store Guideline 1.2 / Play UGC policy.

Berbeda dari suite lain yang menembak server HTTP di port 8001, modul ini
memanggil ASGI app langsung lewat httpx.ASGITransport. Alasannya: fitur
moderasi harus bisa diverifikasi tanpa menyalakan uvicorn, dan seluruh data
yang dibuat bersifat sintetis di database terpisah (nama DB berakhiran `_test`)
yang dihapus lagi di akhir.

pytest-asyncio TIDAK dipakai (tidak ada di requirements). Semua test sinkron
dan menjalankan coroutine lewat satu event loop milik fixture, sehingga motor
dan httpx memakai loop yang sama sepanjang modul.

Yang diuji:
1. POST/GET/DELETE /api/moderation/blocks — idempoten, tidak bisa blokir diri.
2. Pesan dari pengguna yang diblokir hilang dari GET /api/chat (dua arah).
3. Chat langsung tertutup setelah blokir, ruang keluarga/grup tetap jalan.
4. POST /api/moderation/reports — snapshot teks pesan disimpan walau pesan
   kemudian dihapus pengirim; laporan masuk antrean superadmin.
5. GET/PUT /api/admin/reports — hanya superadmin; status bisa diubah.
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DB = "titisanku_moderation_test"

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", TEST_DB)
os.environ.setdefault("SUPERADMIN_EMAILS", "super@test.local")

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

httpx = pytest.importorskip("httpx")
motor = pytest.importorskip("motor.motor_asyncio")

import server as backend  # noqa: E402


def now_utc():
    return datetime.now(timezone.utc)


@pytest.fixture(scope="module")
def env():
    """Loop tunggal + DB uji terpisah; `server.db` dipulihkan setelah modul."""
    from pymongo import MongoClient

    mongo_url = os.environ["MONGO_URL"]
    if "localhost" not in mongo_url and "127.0.0.1" not in mongo_url:
        pytest.skip("Test moderasi hanya jalan pada MongoDB lokal")

    try:
        sync_client = MongoClient(mongo_url, serverSelectionTimeoutMS=2000)
        sync_client.admin.command("ping")
    except Exception:
        pytest.skip("MongoDB lokal tidak tersedia")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    original = backend.db
    client_db = motor.AsyncIOMotorClient(mongo_url)[TEST_DB]
    backend.db = client_db

    transport = httpx.ASGITransport(app=backend.app)
    api = httpx.AsyncClient(transport=transport, base_url="http://testserver")

    yield {"db": client_db, "loop": loop, "api": api}

    loop.run_until_complete(api.aclose())
    backend.db = original
    sync_client.drop_database(TEST_DB)
    sync_client.close()
    loop.close()


def _seed_user(name, email=None, role="admin"):
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    email = email or f"{user_id}@test.local"
    token = uuid.uuid4().hex
    return user_id, token, email, {
        "user_id": user_id, "email": email, "name": name, "picture": None,
        "role": role, "created_at": now_utc(),
    }, {
        "session_token": token, "user_id": user_id, "created_at": now_utc(),
        "expires_at": now_utc() + timedelta(days=1),
    }


def _seed_tree(owner_id, member_ids):
    tid = f"tree_{uuid.uuid4().hex[:12]}"
    tree = {
        "id": tid, "name": "Keluarga Uji", "owner_id": owner_id, "plan": "free",
        "plan_expires_at": None, "created_at": now_utc(),
    }
    members = [
        {"id": str(uuid.uuid4()), "tree_id": tid, "user_id": uid,
         "role": "admin" if uid == owner_id else "editor", "joined_at": now_utc()}
        for uid in member_ids
    ]
    return tid, tree, members


def _seed_message(tid, room_id, sender_id, text):
    mid = str(uuid.uuid4())
    return mid, {
        "id": mid, "room_id": room_id, "tree_id": tid, "sender_id": sender_id,
        "message": text, "attachments": [], "reply_to": None, "read_by": [],
        "edited": False, "created_at": now_utc(), "deleted_at": None,
    }


@pytest.fixture(scope="module")
def ctx(env):
    """Dua pengguna dalam satu pohon + chat langsung + chat keluarga."""
    db, loop = env["db"], env["loop"]

    a_id, a_token, a_email, a_user, a_sess = _seed_user("Andi")
    b_id, b_token, b_email, b_user, b_sess = _seed_user("Budi", role="editor")
    s_id, s_token, s_email, s_user, s_sess = _seed_user("Super", email="super@test.local")

    tid, tree, members = _seed_tree(a_id, [a_id, b_id])
    direct_id = f"room_{uuid.uuid4().hex[:12]}"
    direct = {
        "id": direct_id, "type": "direct", "name": "Andi & Budi", "tree_id": tid,
        "member_ids": [a_id, b_id], "created_by": a_id, "created_at": now_utc(),
    }

    async def _insert():
        await db.users.insert_many([a_user, b_user, s_user])
        await db.user_sessions.insert_many([a_sess, b_sess, s_sess])
        await db.trees.insert_one(tree)
        await db.tree_members.insert_many(members)
        await db.chat_rooms.insert_one(direct)

    loop.run_until_complete(_insert())

    return {
        "db": db, "loop": loop, "api": env["api"], "tree_id": tid, "room_id": direct_id,
        "a": {"id": a_id, "token": a_token, "email": a_email},
        "b": {"id": b_id, "token": b_token, "email": b_email},
        "s": {"id": s_id, "token": s_token, "email": s_email},
    }


def _auth(who):
    return {"Authorization": f"Bearer {who['token']}"}


def test_block_is_idempotent_and_reversible(ctx):
    api, loop, a, b = ctx["api"], ctx["loop"], ctx["a"], ctx["b"]

    r = loop.run_until_complete(api.post("/api/moderation/blocks", json={"user_id": b["id"]}, headers=_auth(a)))
    assert r.status_code == 200, r.text

    # Idempoten: blokir dua kali tidak boleh error / membuat duplikat.
    r = loop.run_until_complete(api.post("/api/moderation/blocks", json={"user_id": b["id"]}, headers=_auth(a)))
    assert r.status_code == 200, r.text

    r = loop.run_until_complete(api.get("/api/moderation/blocks", headers=_auth(a)))
    assert r.status_code == 200
    blocks = r.json()["blocks"]
    assert [x["user_id"] for x in blocks] == [b["id"]]
    assert blocks[0]["name"] == "Budi"

    r = loop.run_until_complete(api.delete(f"/api/moderation/blocks/{b['id']}", headers=_auth(a)))
    assert r.status_code == 200
    r = loop.run_until_complete(api.get("/api/moderation/blocks", headers=_auth(a)))
    assert r.json()["blocks"] == []


def test_cannot_block_self_or_unknown_user(ctx):
    api, loop, a = ctx["api"], ctx["loop"], ctx["a"]

    r = loop.run_until_complete(api.post("/api/moderation/blocks", json={"user_id": a["id"]}, headers=_auth(a)))
    assert r.status_code == 400

    r = loop.run_until_complete(api.post("/api/moderation/blocks", json={"user_id": "user_tidak_ada"}, headers=_auth(a)))
    assert r.status_code == 404


def test_blocked_messages_hidden_both_ways(ctx):
    api, loop, db = ctx["api"], ctx["loop"], ctx["db"]
    a, b, tid, rid = ctx["a"], ctx["b"], ctx["tree_id"], ctx["room_id"]

    _, msg_a = _seed_message(tid, rid, a["id"], "halo dari Andi")
    _, msg_b = _seed_message(tid, rid, b["id"], "halo dari Budi")
    loop.run_until_complete(db.family_chat.insert_many([msg_a, msg_b]))

    # Sebelum blokir: keduanya melihat dua pesan.
    r = loop.run_until_complete(api.get(f"/api/chat?room_id={rid}", headers=_auth(a)))
    assert len(r.json()["messages"]) == 2

    r = loop.run_until_complete(api.post("/api/moderation/blocks", json={"user_id": b["id"]}, headers=_auth(a)))
    assert r.status_code == 200

    # Andi tidak lagi melihat pesan Budi...
    r = loop.run_until_complete(api.get(f"/api/chat?room_id={rid}", headers=_auth(a)))
    assert [m["message"] for m in r.json()["messages"]] == ["halo dari Andi"]

    # ...dan Budi juga tidak melihat pesan Andi (blokir berlaku dua arah).
    r = loop.run_until_complete(api.get(f"/api/chat?room_id={rid}", headers=_auth(b)))
    assert [m["message"] for m in r.json()["messages"]] == ["halo dari Budi"]

    # Riwayat di DB tetap utuh untuk kebutuhan audit.
    assert loop.run_until_complete(db.family_chat.count_documents({"room_id": rid})) == 2

    loop.run_until_complete(api.delete(f"/api/moderation/blocks/{b['id']}", headers=_auth(a)))
    r = loop.run_until_complete(api.get(f"/api/chat?room_id={rid}", headers=_auth(a)))
    assert len(r.json()["messages"]) == 2


def test_direct_chat_closed_after_block(ctx):
    api, loop, db = ctx["api"], ctx["loop"], ctx["db"]
    a, b, tid = ctx["a"], ctx["b"], ctx["tree_id"]

    direct_id = f"room_{uuid.uuid4().hex[:12]}"
    loop.run_until_complete(db.chat_rooms.insert_one({
        "id": direct_id, "type": "direct", "name": "Andi & Budi", "tree_id": tid,
        "member_ids": [a["id"], b["id"]], "created_by": a["id"], "created_at": now_utc(),
    }))

    r = loop.run_until_complete(api.post(f"/api/chat?room_id={direct_id}", json={"message": "hai"}, headers=_auth(a)))
    assert r.status_code == 200, r.text

    loop.run_until_complete(api.post("/api/moderation/blocks", json={"user_id": b["id"]}, headers=_auth(a)))

    r = loop.run_until_complete(api.post(f"/api/chat?room_id={direct_id}", json={"message": "masih?"}, headers=_auth(a)))
    assert r.status_code == 403
    assert "diblokir" in r.json()["detail"]

    # Ruang keluarga (room_id == tree_id) tetap bisa dipakai: blokir hanya
    # menyembunyikan pesan, bukan mengeluarkan orang dari pohon keluarga.
    r = loop.run_until_complete(api.post(f"/api/chat?room_id={tid}", json={"message": "info keluarga"}, headers=_auth(a)))
    assert r.status_code == 200, r.text

    loop.run_until_complete(api.delete(f"/api/moderation/blocks/{b['id']}", headers=_auth(a)))


def test_report_keeps_snapshot_and_reaches_admin(ctx):
    api, loop, db = ctx["api"], ctx["loop"], ctx["db"]
    a, b, s, tid, rid = ctx["a"], ctx["b"], ctx["s"], ctx["tree_id"], ctx["room_id"]

    mid, msg = _seed_message(tid, rid, b["id"], "pesan kasar yang dilaporkan")
    loop.run_until_complete(db.family_chat.insert_one(msg))

    r = loop.run_until_complete(api.post("/api/moderation/reports", json={
        "message_id": mid, "reason": "abuse", "detail": "menghina keluarga",
    }, headers=_auth(a)))
    assert r.status_code == 200, r.text
    report_id = r.json()["id"]

    stored = loop.run_until_complete(db.content_reports.find_one({"id": report_id}))
    assert stored["reported_user_id"] == b["id"]
    assert stored["message_snapshot"] == "pesan kasar yang dilaporkan"
    assert stored["status"] == "open"

    # Pengirim menghapus pesannya -> snapshot laporan harus tetap ada.
    loop.run_until_complete(db.family_chat.update_one({"id": mid}, {"$set": {"deleted_at": now_utc()}}))
    stored = loop.run_until_complete(db.content_reports.find_one({"id": report_id}))
    assert stored["message_snapshot"] == "pesan kasar yang dilaporkan"

    # Notifikasi masuk ke superadmin.
    notes = loop.run_until_complete(
        db.app_notifications.count_documents({"user_id": s["id"], "type": "report"})
    )
    assert notes >= 1

    # Hanya superadmin yang boleh membaca antrean.
    r = loop.run_until_complete(api.get("/api/admin/reports", headers=_auth(a)))
    assert r.status_code == 403

    r = loop.run_until_complete(api.get("/api/admin/reports", headers=_auth(s)))
    assert r.status_code == 200
    assert any(x["id"] == report_id for x in r.json()["reports"])

    r = loop.run_until_complete(api.put(f"/api/admin/reports/{report_id}", json={"status": "resolved"}, headers=_auth(s)))
    assert r.status_code == 200
    stored = loop.run_until_complete(db.content_reports.find_one({"id": report_id}))
    assert stored["status"] == "resolved"


def test_report_validation(ctx):
    api, loop, a = ctx["api"], ctx["loop"], ctx["a"]

    r = loop.run_until_complete(api.post("/api/moderation/reports", json={"reason": "   "}, headers=_auth(a)))
    assert r.status_code == 400

    r = loop.run_until_complete(api.post("/api/moderation/reports", json={
        "message_id": "tidak-ada", "reason": "spam",
    }, headers=_auth(a)))
    assert r.status_code == 404


def test_moderation_requires_auth(ctx):
    api, loop = ctx["api"], ctx["loop"]

    r = loop.run_until_complete(api.get("/api/moderation/blocks"))
    assert r.status_code == 401

    r = loop.run_until_complete(api.post("/api/moderation/reports", json={"reason": "spam"}))
    assert r.status_code == 401
