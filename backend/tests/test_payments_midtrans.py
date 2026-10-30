"""
Backend tests for Midtrans Snap payment endpoints in KETURUNANKU.

Endpoints under test:
  POST /api/payments/snap
  POST /api/payments/notification
  GET  /api/payments/status/{order_id}

Notes:
  - Live PRODUCTION Midtrans keys are configured in backend/.env.
  - We hit the real /payments/snap only MINIMALLY: exactly ONCE for plan=pro and
    ONCE for plan=family — enough to check API integration + payment_orders doc,
    without spamming the merchant.
  - Notification signature test uses a locally-seeded synthetic pending order
    tied to a synthetic tree so no real user tree is affected.
  - Everything is TEST_/KTR-TEST- prefixed and cleaned up afterwards.
    Never delete_many({}).
"""
import os
import uuid
import hashlib
import secrets
from datetime import datetime, timezone, timedelta

import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv


# Ensure MIDTRANS_SERVER_KEY is loaded from backend/.env
_env_candidates = [
    os.path.join(os.path.dirname(__file__), "..", ".env"),
    "backend/.env",
    "/app/backend/.env",
]
for _p in _env_candidates:
    if os.path.exists(_p):
        load_dotenv(_p)
        break

BASE_URL = (
    os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or os.environ.get("EXPO_BACKEND_URL")
    or "http://localhost:8001"
).rstrip("/")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
MIDTRANS_SERVER_KEY = os.environ.get("MIDTRANS_SERVER_KEY", "")


def now_utc():
    return datetime.now(timezone.utc)


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------
# Session-scope fixture: seed synthetic users, tree, tree_members
# --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def pay_ctx():
    db = MongoClient(MONGO_URL)[DB_NAME]

    # Track what we seed so teardown can remove only these docs.
    seeded_user_ids = []
    seeded_tokens = []
    seeded_tree_ids = []
    seeded_member_ids = []
    seeded_order_ids = []

    def mk_user(role_label):
        uid = f"user_TEST_{uuid.uuid4().hex[:10]}"
        email = f"TEST_{role_label}_{uuid.uuid4().hex[:6]}@example.com"
        tok = secrets.token_hex(20)
        db.users.insert_one({
            "user_id": uid,
            "email": email,
            "name": f"TEST_{role_label}",
            "picture": None,
            "role": "viewer",  # global role is unused per-tree
            "created_at": now_utc(),
        })
        db.user_sessions.insert_one({
            "session_token": tok,
            "user_id": uid,
            "created_at": now_utc(),
            "expires_at": now_utc() + timedelta(days=7),
        })
        seeded_user_ids.append(uid)
        seeded_tokens.append(tok)
        return uid, tok

    admin_id, admin_tok = mk_user("admin")
    editor_id, editor_tok = mk_user("editor")
    viewer_id, viewer_tok = mk_user("viewer")
    other_id, other_tok = mk_user("other")  # for status 404 test

    tree_id = f"tree_TEST_{uuid.uuid4().hex[:10]}"
    db.trees.insert_one({
        "id": tree_id,
        "name": "TEST_Pay_Tree",
        "owner_id": admin_id,
        "plan": "free",
        "is_public": False,
        "root_person_id": None,
        "created_at": now_utc(),
    })
    seeded_tree_ids.append(tree_id)

    for uid, role in [(admin_id, "admin"), (editor_id, "editor"), (viewer_id, "viewer")]:
        mid = str(uuid.uuid4())
        db.tree_members.insert_one({
            "id": mid,
            "tree_id": tree_id,
            "user_id": uid,
            "role": role,
            "joined_at": now_utc(),
        })
        seeded_member_ids.append(mid)

    ctx = {
        "db": db,
        "tree_id": tree_id,
        "admin_id": admin_id, "admin_tok": admin_tok,
        "editor_id": editor_id, "editor_tok": editor_tok,
        "viewer_id": viewer_id, "viewer_tok": viewer_tok,
        "other_id": other_id, "other_tok": other_tok,
        "seeded_order_ids": seeded_order_ids,
    }
    yield ctx

    # -------- Teardown: precise deletion (never delete_many({})) ------------
    if seeded_user_ids:
        db.users.delete_many({"user_id": {"$in": seeded_user_ids}})
    if seeded_tokens:
        db.user_sessions.delete_many({"session_token": {"$in": seeded_tokens}})
    if seeded_tree_ids:
        db.trees.delete_many({"id": {"$in": seeded_tree_ids}})
    if seeded_member_ids:
        db.tree_members.delete_many({"id": {"$in": seeded_member_ids}})
    if seeded_order_ids:
        db.payment_orders.delete_many({"order_id": {"$in": seeded_order_ids}})


# ---------------------------------------------------------------------------
# Config sanity
# ---------------------------------------------------------------------------
requires_midtrans = pytest.mark.skipif(
    not MIDTRANS_SERVER_KEY,
    reason=(
        "MIDTRANS_SERVER_KEY tidak di-set. Test Snap memanggil API Midtrans "
        "sungguhan, jadi tidak boleh dijalankan palsu/offline."
    ),
)


def test_midtrans_server_key_loaded():
    """Kredensial untuk test Snap. Tanpa key, test Snap di-skip (bukan gagal),
    sehingga CI lokal tanpa kredensial tetap hijau dan tidak membuat transaksi
    sungguhan. Test webhook di bawah tidak butuh key asli karena memakai
    tanda tangan yang dihitung lokal."""
    if not MIDTRANS_SERVER_KEY:
        pytest.skip("MIDTRANS_SERVER_KEY tidak di-set: test Snap dilewati")
    assert len(MIDTRANS_SERVER_KEY) > 5


# ---------------------------------------------------------------------------
# POST /payments/snap  — auth / role / plan validation
# ---------------------------------------------------------------------------
def test_snap_editor_forbidden(pay_ctx):
    r = requests.post(
        f"{BASE_URL}/api/payments/snap",
        params={"tree_id": pay_ctx["tree_id"]},
        headers=auth(pay_ctx["editor_tok"]),
        json={"plan": "pro"},
        timeout=30,
    )
    assert r.status_code == 403, r.text


def test_snap_viewer_forbidden(pay_ctx):
    r = requests.post(
        f"{BASE_URL}/api/payments/snap",
        params={"tree_id": pay_ctx["tree_id"]},
        headers=auth(pay_ctx["viewer_tok"]),
        json={"plan": "pro"},
        timeout=30,
    )
    assert r.status_code == 403, r.text


def test_snap_invalid_plan_400(pay_ctx):
    r = requests.post(
        f"{BASE_URL}/api/payments/snap",
        params={"tree_id": pay_ctx["tree_id"]},
        headers=auth(pay_ctx["admin_tok"]),
        json={"plan": "gold"},
        timeout=30,
    )
    assert r.status_code == 400, r.text


# ---------------------------------------------------------------------------
# POST /payments/snap  — LIVE call (once for pro, once for family)
# ---------------------------------------------------------------------------
@requires_midtrans
def test_snap_admin_creates_pro_order(pay_ctx):
    r = requests.post(
        f"{BASE_URL}/api/payments/snap",
        params={"tree_id": pay_ctx["tree_id"]},
        headers=auth(pay_ctx["admin_tok"]),
        json={"plan": "pro"},
        timeout=45,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert set(["order_id", "token", "redirect_url", "amount", "plan"]).issubset(data.keys())
    assert data["plan"] == "pro"
    assert data["amount"] == 149000
    assert data["order_id"].startswith("KTR-")
    assert isinstance(data["token"], str) and len(data["token"]) > 5
    assert isinstance(data["redirect_url"], str)
    # sandbox uses app.sandbox.midtrans.com, production uses app.midtrans.com
    assert any(
        host in data["redirect_url"]
        for host in ("app.sandbox.midtrans.com", "app.midtrans.com")
    ), f"redirect_url={data['redirect_url']}"

    order = pay_ctx["db"].payment_orders.find_one({"order_id": data["order_id"]})
    assert order is not None, "payment_orders row not created"
    assert order["status"] == "pending"
    assert order["amount"] == 149000
    assert order["plan"] == "pro"
    assert order["tree_id"] == pay_ctx["tree_id"]
    assert order["user_id"] == pay_ctx["admin_id"]
    pay_ctx["seeded_order_ids"].append(data["order_id"])
    pay_ctx["_pro_order_id"] = data["order_id"]  # for later status test


@requires_midtrans
def test_snap_admin_creates_family_order_amount_199000(pay_ctx):
    r = requests.post(
        f"{BASE_URL}/api/payments/snap",
        params={"tree_id": pay_ctx["tree_id"]},
        headers=auth(pay_ctx["admin_tok"]),
        json={"plan": "family"},
        timeout=45,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["plan"] == "family"
    assert data["amount"] == 199000
    order = pay_ctx["db"].payment_orders.find_one({"order_id": data["order_id"]})
    assert order["amount"] == 199000
    assert order["plan"] == "family"
    assert order["status"] == "pending"
    pay_ctx["seeded_order_ids"].append(data["order_id"])


# ---------------------------------------------------------------------------
# POST /payments/notification  — signature verification + activation
# ---------------------------------------------------------------------------
def _seed_pending_order(db, seeded_order_ids, tree_id, user_id, plan="pro", amount=149000):
    order_id = f"KTR-TEST-{uuid.uuid4().hex[:10]}"
    db.payment_orders.insert_one({
        "order_id": order_id,
        "user_id": user_id,
        "tree_id": tree_id,
        "plan": plan,
        "amount": amount,
        "status": "pending",
        "created_at": now_utc(),
    })
    seeded_order_ids.append(order_id)
    return order_id


def _sign(order_id, status_code, gross_amount):
    raw = f"{order_id}{status_code}{gross_amount}{MIDTRANS_SERVER_KEY}"
    return hashlib.sha512(raw.encode()).hexdigest()


def test_notification_valid_signature_settlement_activates(pay_ctx):
    db = pay_ctx["db"]
    # Reset tree plan to free
    db.trees.update_one({"id": pay_ctx["tree_id"]}, {"$set": {"plan": "free"}})
    order_id = _seed_pending_order(db, pay_ctx["seeded_order_ids"], pay_ctx["tree_id"], pay_ctx["admin_id"], "pro", 149000)

    gross = "149000.00"
    status_code = "200"
    sig = _sign(order_id, status_code, gross)
    payload = {
        "order_id": order_id,
        "status_code": status_code,
        "gross_amount": gross,
        "signature_key": sig,
        "transaction_status": "settlement",
        "fraud_status": "accept",
    }
    r = requests.post(f"{BASE_URL}/api/payments/notification", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}

    order = db.payment_orders.find_one({"order_id": order_id})
    assert order["status"] == "paid"
    tree = db.trees.find_one({"id": pay_ctx["tree_id"]})
    assert tree["plan"] == "pro"


def test_notification_invalid_signature_403(pay_ctx):
    db = pay_ctx["db"]
    order_id = _seed_pending_order(db, pay_ctx["seeded_order_ids"], pay_ctx["tree_id"], pay_ctx["admin_id"], "pro", 149000)
    payload = {
        "order_id": order_id,
        "status_code": "200",
        "gross_amount": "149000.00",
        "signature_key": "deadbeef" * 8,  # bogus
        "transaction_status": "settlement",
        "fraud_status": "accept",
    }
    r = requests.post(f"{BASE_URL}/api/payments/notification", json=payload, timeout=30)
    assert r.status_code == 403, r.text
    # order should stay pending
    order = db.payment_orders.find_one({"order_id": order_id})
    assert order["status"] == "pending"


def test_notification_cancel_marks_failed_no_plan_change(pay_ctx):
    db = pay_ctx["db"]
    # Force tree plan to free before this scenario
    db.trees.update_one({"id": pay_ctx["tree_id"]}, {"$set": {"plan": "free"}})
    order_id = _seed_pending_order(db, pay_ctx["seeded_order_ids"], pay_ctx["tree_id"], pay_ctx["admin_id"], "family", 199000)
    gross = "199000.00"
    status_code = "202"
    sig = _sign(order_id, status_code, gross)
    payload = {
        "order_id": order_id,
        "status_code": status_code,
        "gross_amount": gross,
        "signature_key": sig,
        "transaction_status": "cancel",
    }
    r = requests.post(f"{BASE_URL}/api/payments/notification", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    order = db.payment_orders.find_one({"order_id": order_id})
    assert order["status"] == "failed"
    tree = db.trees.find_one({"id": pay_ctx["tree_id"]})
    assert tree["plan"] == "free", "Cancelled payment must not upgrade tree plan"


def test_notification_idempotent_on_paid(pay_ctx):
    """Sending settlement again for an already-paid order should not error nor double-apply."""
    db = pay_ctx["db"]
    order_id = _seed_pending_order(db, pay_ctx["seeded_order_ids"], pay_ctx["tree_id"], pay_ctx["admin_id"], "pro", 149000)
    # First activation
    gross = "149000.00"
    status_code = "200"
    sig = _sign(order_id, status_code, gross)
    payload = {
        "order_id": order_id, "status_code": status_code, "gross_amount": gross,
        "signature_key": sig, "transaction_status": "settlement", "fraud_status": "accept",
    }
    r1 = requests.post(f"{BASE_URL}/api/payments/notification", json=payload, timeout=30)
    assert r1.status_code == 200
    order = db.payment_orders.find_one({"order_id": order_id})
    assert order["status"] == "paid"
    paid_at_1 = order.get("paid_at")

    # Replay
    r2 = requests.post(f"{BASE_URL}/api/payments/notification", json=payload, timeout=30)
    assert r2.status_code == 200, r2.text
    order2 = db.payment_orders.find_one({"order_id": order_id})
    assert order2["status"] == "paid"
    # paid_at should not be updated (idempotent) — _activate_order returns early
    assert order2.get("paid_at") == paid_at_1, "paid_at changed on replay — activation not idempotent"


# ---------------------------------------------------------------------------
# GET /payments/status/{order_id}
# ---------------------------------------------------------------------------
def test_status_unknown_order_404(pay_ctx):
    r = requests.get(
        f"{BASE_URL}/api/payments/status/KTR-TEST-doesnotexist-{uuid.uuid4().hex[:6]}",
        headers=auth(pay_ctx["admin_tok"]),
        timeout=30,
    )
    assert r.status_code == 404, r.text


def test_status_other_user_404(pay_ctx):
    db = pay_ctx["db"]
    order_id = _seed_pending_order(db, pay_ctx["seeded_order_ids"], pay_ctx["tree_id"], pay_ctx["admin_id"], "pro", 149000)
    # Mark it paid so no outbound Midtrans call happens (avoids hitting live API needlessly).
    db.payment_orders.update_one({"order_id": order_id}, {"$set": {"status": "paid"}})
    r = requests.get(
        f"{BASE_URL}/api/payments/status/{order_id}",
        headers=auth(pay_ctx["other_tok"]),
        timeout=30,
    )
    assert r.status_code == 404, r.text


def test_status_paid_returns_without_midtrans_call(pay_ctx):
    db = pay_ctx["db"]
    order_id = _seed_pending_order(db, pay_ctx["seeded_order_ids"], pay_ctx["tree_id"], pay_ctx["admin_id"], "pro", 149000)
    db.payment_orders.update_one({"order_id": order_id}, {"$set": {"status": "paid"}})
    r = requests.get(
        f"{BASE_URL}/api/payments/status/{order_id}",
        headers=auth(pay_ctx["admin_tok"]),
        timeout=30,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data == {"status": "paid", "plan": "pro"}


def test_status_owner_gets_status(pay_ctx):
    db = pay_ctx["db"]
    order_id = _seed_pending_order(db, pay_ctx["seeded_order_ids"], pay_ctx["tree_id"], pay_ctx["admin_id"], "family", 199000)
    # Force to paid to skip live Midtrans lookup
    db.payment_orders.update_one({"order_id": order_id}, {"$set": {"status": "paid"}})
    r = requests.get(
        f"{BASE_URL}/api/payments/status/{order_id}",
        headers=auth(pay_ctx["admin_tok"]),
        timeout=30,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["plan"] == "family"
    assert data["status"] == "paid"
