"""Backend tests for Superadmin Dashboard endpoints.

Covers:
- GET /api/admin/overview (business/funnel/features/tech shape) — 200 for superadmin, 403 non-super, 401 no auth
- GET /api/admin/users (users[] with tree_count) — 200/403/401
- GET /api/admin/feedback (feedback[]) — 200/403/401
- Metrics middleware inserts into error_logs and recent_errors surfaces in overview

Seeds users + user_sessions directly in Mongo (Google OAuth cannot be automated).
Superadmin identified by email == SUPERADMIN_EMAILS (emmusic.indonesia@gmail.com).
Cleans up ALL synthetic docs at teardown so the real first Google user still becomes admin.
"""
import os
import uuid
import secrets
from datetime import datetime, timezone, timedelta

import pytest
import requests
from pymongo import MongoClient

BASE_URL = (
    os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or os.environ.get("EXPO_BACKEND_URL")
    or "http://localhost:8001"
).rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

SUPERADMIN_EMAIL = "emmusic.indonesia@gmail.com"


def now_utc():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Fixture: seed a superadmin + a normal user with sessions; wipe on teardown.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def admin_ctx():
    c = MongoClient(MONGO_URL)
    db = c[DB_NAME]

    # NOTE: NEVER wipe whole collections here — this runs against the shared
    # dev database which may contain real user data. Only seed and later remove
    # the exact synthetic docs created by this fixture (tracked by id/uid/token).

    # ---- Seed superadmin ----
    super_uid = f"user_{uuid.uuid4().hex[:12]}"
    super_token = secrets.token_hex(16)
    db.users.insert_one({
        "user_id": super_uid,
        "email": SUPERADMIN_EMAIL,
        "name": "TEST_SuperAdmin",
        "picture": None,
        "role": "admin",
        "created_at": now_utc(),
    })
    db.user_sessions.insert_one({
        "session_token": super_token,
        "user_id": super_uid,
        "created_at": now_utc(),
        "expires_at": now_utc() + timedelta(days=7),
    })

    # ---- Seed non-superadmin (regular authenticated user) ----
    norm_uid = f"user_{uuid.uuid4().hex[:12]}"
    norm_token = secrets.token_hex(16)
    db.users.insert_one({
        "user_id": norm_uid,
        "email": f"TEST_norm_{uuid.uuid4().hex[:6]}@example.com",
        "name": "TEST_Normal",
        "picture": None,
        "role": "admin",  # tree-scoped role; superadmin check is email-only
        "created_at": now_utc(),
    })
    db.user_sessions.insert_one({
        "session_token": norm_token,
        "user_id": norm_uid,
        "created_at": now_utc(),
        "expires_at": now_utc() + timedelta(days=7),
    })

    # ---- Seed some trees so metrics have data ----
    tree_ids = []
    for plan in ["free", "free", "pro", "family"]:
        tid = f"tree_{uuid.uuid4().hex[:12]}"
        tree_ids.append(tid)
        db.trees.insert_one({
            "id": tid, "name": f"TEST_Tree_{plan}", "owner_id": super_uid,
            "plan": plan, "is_public": False, "root_person_id": None,
            "created_at": now_utc(),
        })
        db.tree_members.insert_one({
            "id": str(uuid.uuid4()), "tree_id": tid, "user_id": super_uid,
            "role": "admin", "joined_at": now_utc(),
        })

    # A paid order (in the last 30d)
    order_id = f"TEST_ORDER_{uuid.uuid4().hex[:8]}"
    db.payment_orders.insert_one({
        "order_id": order_id,
        "user_id": super_uid,
        "amount": 149000,
        "status": "paid",
        "plan": "pro",
        "paid_at": now_utc(),
        "created_at": now_utc(),
    })

    # A feedback item
    fb_id = str(uuid.uuid4())
    db.feedback.insert_one({
        "id": fb_id,
        "user_id": super_uid,
        "message": "TEST feedback",
        "created_at": now_utc(),
    })

    ctx = {
        "super_uid": super_uid, "super_token": super_token,
        "norm_uid": norm_uid, "norm_token": norm_token,
        "db": db,
    }
    yield ctx

    # ---- Teardown: remove ONLY the synthetic docs created above ----
    uids = [super_uid, norm_uid]
    db.users.delete_many({"user_id": {"$in": uids}})
    db.user_sessions.delete_many({"session_token": {"$in": [super_token, norm_token]}})
    db.trees.delete_many({"id": {"$in": tree_ids}})
    db.tree_members.delete_many({"tree_id": {"$in": tree_ids}})
    db.payment_orders.delete_many({"order_id": order_id})
    db.feedback.delete_many({"id": fb_id})
    c.close()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ===========================================================================
# /api/admin/overview
# ===========================================================================
class TestAdminOverview:
    def test_unauthenticated_returns_401(self, admin_ctx):
        r = requests.get(f"{BASE_URL}/api/admin/overview", timeout=30)
        assert r.status_code == 401, r.text

    def test_non_superadmin_returns_403(self, admin_ctx):
        r = requests.get(
            f"{BASE_URL}/api/admin/overview",
            headers=_auth(admin_ctx["norm_token"]),
            timeout=30,
        )
        assert r.status_code == 403, r.text

    def test_superadmin_returns_business_shape(self, admin_ctx):
        r = requests.get(
            f"{BASE_URL}/api/admin/overview",
            headers=_auth(admin_ctx["super_token"]),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # top-level keys
        for k in ["business", "funnel", "features", "tech"]:
            assert k in data, f"missing '{k}' in overview"

        b = data["business"]
        for k in [
            "total_users", "new_users_7d", "active_users_7d", "total_trees",
            "plans", "revenue_total", "revenue_30d", "paid_count",
        ]:
            assert k in b, f"missing business.{k}"
        assert isinstance(b["total_users"], int) and b["total_users"] >= 2
        assert isinstance(b["plans"], dict)
        for pk in ["free", "pro", "family"]:
            assert pk in b["plans"], f"missing plans.{pk}"
        assert b["plans"]["free"] >= 2
        assert b["plans"]["pro"] >= 1
        assert b["plans"]["family"] >= 1
        assert b["paid_count"] >= 1
        assert b["revenue_total"] >= 149000
        assert b["revenue_30d"] >= 149000

    def test_superadmin_funnel_and_features_are_arrays(self, admin_ctx):
        r = requests.get(
            f"{BASE_URL}/api/admin/overview",
            headers=_auth(admin_ctx["super_token"]),
            timeout=30,
        )
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data["funnel"], list) and len(data["funnel"]) == 3
        steps = [f["step"] for f in data["funnel"]]
        assert steps == ["Daftar", "Buat Pohon", "Upgrade"]
        for item in data["funnel"]:
            assert "count" in item and isinstance(item["count"], int)

        assert isinstance(data["features"], list) and len(data["features"]) >= 3
        # sorted desc by count
        counts = [f["count"] for f in data["features"]]
        assert counts == sorted(counts, reverse=True)

    def test_superadmin_tech_shape(self, admin_ctx):
        r = requests.get(
            f"{BASE_URL}/api/admin/overview",
            headers=_auth(admin_ctx["super_token"]),
            timeout=30,
        )
        assert r.status_code == 200
        tech = r.json()["tech"]
        for k in ["avg_response_ms", "requests_1h", "errors_24h", "db_counts", "recent_errors"]:
            assert k in tech, f"missing tech.{k}"
        assert isinstance(tech["db_counts"], dict)
        for k in ["users", "trees", "people", "relations", "messages", "feedback"]:
            assert k in tech["db_counts"], f"missing tech.db_counts.{k}"
        assert isinstance(tech["recent_errors"], list)
        # after hitting overview at least twice, req_1h > 0
        assert tech["requests_1h"] >= 1


# ===========================================================================
# /api/admin/users
# ===========================================================================
class TestAdminUsers:
    def test_unauthenticated_returns_401(self, admin_ctx):
        r = requests.get(f"{BASE_URL}/api/admin/users", timeout=30)
        assert r.status_code == 401, r.text

    def test_non_superadmin_returns_403(self, admin_ctx):
        r = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers=_auth(admin_ctx["norm_token"]),
            timeout=30,
        )
        assert r.status_code == 403, r.text

    def test_superadmin_returns_users_with_tree_count(self, admin_ctx):
        r = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers=_auth(admin_ctx["super_token"]),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "users" in data
        assert isinstance(data["users"], list)
        assert len(data["users"]) >= 2  # super + norm
        for u in data["users"]:
            assert "user_id" in u
            assert "email" in u
            assert "tree_count" in u
            assert isinstance(u["tree_count"], int)
        # superadmin should have 4 trees seeded
        super_row = next(u for u in data["users"] if u["email"] == SUPERADMIN_EMAIL)
        assert super_row["tree_count"] == 4


# ===========================================================================
# /api/admin/feedback
# ===========================================================================
class TestAdminFeedback:
    def test_unauthenticated_returns_401(self, admin_ctx):
        r = requests.get(f"{BASE_URL}/api/admin/feedback", timeout=30)
        assert r.status_code == 401, r.text

    def test_non_superadmin_returns_403(self, admin_ctx):
        r = requests.get(
            f"{BASE_URL}/api/admin/feedback",
            headers=_auth(admin_ctx["norm_token"]),
            timeout=30,
        )
        assert r.status_code == 403, r.text

    def test_superadmin_returns_feedback_list(self, admin_ctx):
        r = requests.get(
            f"{BASE_URL}/api/admin/feedback",
            headers=_auth(admin_ctx["super_token"]),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "feedback" in data and isinstance(data["feedback"], list)
        assert len(data["feedback"]) >= 1
        item = data["feedback"][0]
        assert "message" in item


# ===========================================================================
# Metrics middleware: error_logs capture + surfaces in overview.recent_errors
# ===========================================================================
class TestMetricsMiddleware:
    def test_error_logs_capture_and_recent_errors_returned(self, admin_ctx):
        db = admin_ctx["db"]
        # Insert a synthetic error_log directly (middleware writes here too on 5xx)
        eid = str(uuid.uuid4())
        db.error_logs.insert_one({
            "id": eid,
            "path": "/api/test/synthetic",
            "method": "GET",
            "status": 500,
            "detail": "TEST synthetic error",
            "created_at": now_utc(),
        })
        r = requests.get(
            f"{BASE_URL}/api/admin/overview",
            headers=_auth(admin_ctx["super_token"]),
            timeout=30,
        )
        assert r.status_code == 200
        tech = r.json()["tech"]
        assert tech["errors_24h"] >= 1
        assert isinstance(tech["recent_errors"], list) and len(tech["recent_errors"]) >= 1
        # Our synthetic error should be present
        ids = [e.get("id") for e in tech["recent_errors"]]
        assert eid in ids, f"synthetic error not in recent_errors: {ids}"
