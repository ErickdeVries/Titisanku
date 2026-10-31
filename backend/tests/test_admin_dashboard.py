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
        doc = {
            "id": tid, "name": f"TEST_Tree_{plan}", "owner_id": super_uid,
            "plan": plan, "is_public": False, "root_person_id": None,
            "created_at": now_utc(),
        }
        if plan in ("pro", "family"):
            # Langganan aktif: /admin/finance menghitung active_subs dari sini.
            doc["upgraded_at"] = now_utc()
            doc["expires_at"] = now_utc() + timedelta(days=200)
        db.trees.insert_one(doc)
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

    # ---- Activity log rows (penanda unik agar filter bisa diuji) ----
    act_ids = [f"act_TEST_{uuid.uuid4().hex[:10]}" for _ in range(2)]
    db.activity_log.insert_one({
        "id": act_ids[0], "action": "auth.login",
        "actor_id": super_uid, "actor_email": SUPERADMIN_EMAIL,
        "actor_name": "TEST_SuperAdmin", "tree_id": None, "target": None,
        "meta": {"method": "password"}, "ip": "127.0.0.1", "created_at": now_utc(),
    })
    db.activity_log.insert_one({
        "id": act_ids[1], "action": "person.add",
        "actor_id": norm_uid, "actor_email": "TEST_norm@example.com",
        "actor_name": "TEST_Normal", "tree_id": tree_ids[0], "target": "TEST_PERSON_1",
        "meta": {"name": "TEST_Budi"}, "ip": "127.0.0.1", "created_at": now_utc(),
    })

    # ---- Error log row dengan path unik ----
    err_path = f"/api/TEST_boom_{uuid.uuid4().hex[:6]}"
    err_id = str(uuid.uuid4())
    db.error_logs.insert_one({
        "id": err_id, "path": err_path, "method": "GET", "status": 500,
        "detail": "TEST boom", "duration_ms": 42.0, "level": "error",
        "created_at": now_utc(),
    })

    ctx = {
        "super_uid": super_uid, "super_token": super_token,
        "norm_uid": norm_uid, "norm_token": norm_token,
        "tree_ids": tree_ids, "order_id": order_id,
        "act_ids": act_ids, "err_path": err_path, "err_id": err_id,
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
    db.activity_log.delete_many({"id": {"$in": act_ids}})
    db.error_logs.delete_many({"id": err_id})
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


# ===========================================================================
# /api/admin/growth
# ===========================================================================
class TestAdminGrowth:
    def test_unauthenticated_returns_401(self, admin_ctx):
        r = requests.get(f"{BASE_URL}/api/admin/growth", timeout=30)
        assert r.status_code == 401, r.text

    def test_normal_user_returns_403(self, admin_ctx):
        r = requests.get(
            f"{BASE_URL}/api/admin/growth",
            headers=_auth(admin_ctx["norm_token"]),
            timeout=30,
        )
        assert r.status_code == 403, r.text

    def test_returns_series_totals_engagement_funnel(self, admin_ctx):
        r = requests.get(
            f"{BASE_URL}/api/admin/growth",
            params={"days": 7},
            headers=_auth(admin_ctx["super_token"]),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["days"] == 7
        assert len(data["series"]) == 7
        point = data["series"][-1]
        for k in (
            "date", "users", "trees", "people", "messages",
            "paid_orders", "revenue", "active_users",
        ):
            assert k in point, f"missing '{k}' in growth series"
        for k in ("total_users", "total_trees", "paid_trees", "new_users_7d", "total_people"):
            assert k in data["totals"], f"missing '{k}' in growth totals"
        for k in ("dau", "wau", "mau", "stickiness", "returning_7d"):
            assert k in data["engagement"]
        for k in ("users", "owners", "payers", "conversion"):
            assert k in data["funnel"]

    def test_days_out_of_range_returns_422(self, admin_ctx):
        r = requests.get(
            f"{BASE_URL}/api/admin/growth",
            params={"days": 3},
            headers=_auth(admin_ctx["super_token"]),
            timeout=30,
        )
        assert r.status_code == 422, r.text


# ===========================================================================
# /api/admin/finance
# ===========================================================================
class TestAdminFinance:
    def test_unauthenticated_returns_401(self, admin_ctx):
        r = requests.get(f"{BASE_URL}/api/admin/finance", timeout=30)
        assert r.status_code == 401, r.text

    def test_normal_user_returns_403(self, admin_ctx):
        r = requests.get(
            f"{BASE_URL}/api/admin/finance",
            headers=_auth(admin_ctx["norm_token"]),
            timeout=30,
        )
        assert r.status_code == 403, r.text

    def test_revenue_and_composition(self, admin_ctx):
        r = requests.get(
            f"{BASE_URL}/api/admin/finance",
            params={"days": 30},
            headers=_auth(admin_ctx["super_token"]),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data["series"]) == 30
        # Order TEST_ORDER seeded dengan amount 149000 wajib terhitung.
        assert data["revenue"]["total"] >= 149000
        assert data["revenue"]["30d"] >= 149000
        assert data["revenue"]["avg_order_value"] > 0
        paid = next((x for x in data["by_status"] if x["status"] == "paid"), None)
        assert paid and paid["count"] >= 1, data["by_status"]
        assert any(x["plan"] == "pro" and x["count"] >= 1 for x in data["by_plan"]), data["by_plan"]
        subs = data["subscriptions"]
        for k in ("active", "expiring_30d", "paid_trees"):
            assert k in subs
        # Dua tree pro/family di-seed dengan expires_at 200 hari -> aktif.
        assert subs["active"] >= 2, subs
        order_ids = [o.get("order_id") for o in data["recent"]]
        assert admin_ctx["order_id"] in order_ids, order_ids


# ===========================================================================
# /api/admin/activity
# ===========================================================================
class TestAdminActivity:
    def test_unauthenticated_returns_401(self, admin_ctx):
        r = requests.get(f"{BASE_URL}/api/admin/activity", timeout=30)
        assert r.status_code == 401, r.text

    def test_normal_user_returns_403(self, admin_ctx):
        r = requests.get(
            f"{BASE_URL}/api/admin/activity",
            headers=_auth(admin_ctx["norm_token"]),
            timeout=30,
        )
        assert r.status_code == 403, r.text

    def test_shape_and_known_actions(self, admin_ctx):
        r = requests.get(
            f"{BASE_URL}/api/admin/activity",
            headers=_auth(admin_ctx["super_token"]),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("items", "total", "limit", "skip", "actions", "known_actions"):
            assert k in data, f"missing '{k}' in activity response"
        assert isinstance(data["items"], list) and isinstance(data["known_actions"], list)
        # Semua action yang diumumkan ke UI harus benar-benar dipancarkan kode.
        assert "admin.view" not in data["known_actions"]

    def test_filter_by_action(self, admin_ctx):
        r = requests.get(
            f"{BASE_URL}/api/admin/activity",
            params={"action": "auth.login", "days": 30},
            headers=_auth(admin_ctx["super_token"]),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert items and all(i["action"] == "auth.login" for i in items), items

    def test_filter_by_query_matches_meta_name(self, admin_ctx):
        r = requests.get(
            f"{BASE_URL}/api/admin/activity",
            params={"q": "TEST_Budi", "days": 30},
            headers=_auth(admin_ctx["super_token"]),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        ids = [i["id"] for i in r.json()["items"]]
        assert admin_ctx["act_ids"][1] in ids, ids

    def test_filter_by_tree_id(self, admin_ctx):
        r = requests.get(
            f"{BASE_URL}/api/admin/activity",
            params={"tree_id": admin_ctx["tree_ids"][0], "days": 30},
            headers=_auth(admin_ctx["super_token"]),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert items and all(i.get("tree_id") == admin_ctx["tree_ids"][0] for i in items), items

    def test_days_out_of_range_returns_422(self, admin_ctx):
        r = requests.get(
            f"{BASE_URL}/api/admin/activity",
            params={"days": 999},
            headers=_auth(admin_ctx["super_token"]),
            timeout=30,
        )
        assert r.status_code == 422, r.text


# ===========================================================================
# /api/admin/errors
# ===========================================================================
class TestAdminErrors:
    def test_unauthenticated_returns_401(self, admin_ctx):
        r = requests.get(f"{BASE_URL}/api/admin/errors", timeout=30)
        assert r.status_code == 401, r.text

    def test_normal_user_returns_403(self, admin_ctx):
        r = requests.get(
            f"{BASE_URL}/api/admin/errors",
            headers=_auth(admin_ctx["norm_token"]),
            timeout=30,
        )
        assert r.status_code == 403, r.text

    def test_shape_and_filters(self, admin_ctx):
        r = requests.get(
            f"{BASE_URL}/api/admin/errors",
            params={"path": "TEST_boom", "days": 7},
            headers=_auth(admin_ctx["super_token"]),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("items", "total", "count_24h", "by_path", "by_status"):
            assert k in data, f"missing '{k}' in errors response"
        assert data["total"] >= 1
        assert data["items"] and all("TEST_boom" in i["path"] for i in data["items"])
        assert any(g["path"] == admin_ctx["err_path"] for g in data["by_path"])

    def test_filter_by_status(self, admin_ctx):
        r = requests.get(
            f"{BASE_URL}/api/admin/errors",
            params={"status": 500, "days": 7},
            headers=_auth(admin_ctx["super_token"]),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        assert all(i["status"] == 500 for i in r.json()["items"])


# ===========================================================================
# /api/admin/trees
# ===========================================================================
class TestAdminTrees:
    def test_unauthenticated_returns_401(self, admin_ctx):
        r = requests.get(f"{BASE_URL}/api/admin/trees", timeout=30)
        assert r.status_code == 401, r.text

    def test_normal_user_returns_403(self, admin_ctx):
        r = requests.get(
            f"{BASE_URL}/api/admin/trees",
            headers=_auth(admin_ctx["norm_token"]),
            timeout=30,
        )
        assert r.status_code == 403, r.text

    def test_search_and_shape(self, admin_ctx):
        r = requests.get(
            f"{BASE_URL}/api/admin/trees",
            params={"q": "TEST_Tree_pro"},
            headers=_auth(admin_ctx["super_token"]),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("trees", "total", "plan_counts", "limit", "skip"):
            assert k in data, f"missing '{k}' in trees response"
        assert data["total"] == 1, data
        row = data["trees"][0]
        for k in (
            "id", "name", "plan", "created_at", "expires_at",
            "owner_email", "people", "members", "messages", "storage_used",
        ):
            assert k in row, f"missing '{k}' in tree row"
        assert row["plan"] == "pro"
        assert row["expires_at"] is not None
        assert isinstance(row["storage_used"], (int, float))
        assert any(p["plan"] == "pro" and p["count"] >= 1 for p in data["plan_counts"])

    def test_filter_by_plan(self, admin_ctx):
        r = requests.get(
            f"{BASE_URL}/api/admin/trees",
            params={"plan": "family"},
            headers=_auth(admin_ctx["super_token"]),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        assert all(t["plan"] == "family" for t in r.json()["trees"])


# ===========================================================================
# /api/admin/system
# ===========================================================================
class TestAdminSystem:
    def test_unauthenticated_returns_401(self, admin_ctx):
        r = requests.get(f"{BASE_URL}/api/admin/system", timeout=30)
        assert r.status_code == 401, r.text

    def test_normal_user_returns_403(self, admin_ctx):
        r = requests.get(
            f"{BASE_URL}/api/admin/system",
            headers=_auth(admin_ctx["norm_token"]),
            timeout=30,
        )
        assert r.status_code == 403, r.text

    def test_health_shape(self, admin_ctx):
        r = requests.get(
            f"{BASE_URL}/api/admin/system",
            headers=_auth(admin_ctx["super_token"]),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data["uptime_seconds"], int) and data["uptime_seconds"] >= 0
        assert data["started_at"]
        assert isinstance(data["integrations"], dict)
        for label in ("1h", "24h"):
            block = data["request_stats"][label]
            for k in ("requests", "errors", "avg_ms", "p95_ms", "slowest"):
                assert k in block, f"missing '{k}' in request_stats[{label}]"
            assert isinstance(block["requests"], int)
        for name in ("users", "trees", "people", "payment_orders", "activity_log", "error_logs"):
            assert name in data["collections"], f"missing '{name}' in collections"
        assert isinstance(data["superadmins"], list)


# ===========================================================================
# Audit trail: action yang dulu dideklarasikan tapi belum pernah ditulis
# ===========================================================================
class TestAdminActivityCoverage:
    def test_plan_expired_is_logged_on_lazy_downgrade(self, admin_ctx):
        db = admin_ctx["db"]
        tid = f"tree_TEST_exp_{uuid.uuid4().hex[:8]}"
        uid = admin_ctx["norm_uid"]
        db.trees.insert_one({
            "id": tid, "name": "TEST_Tree_expired", "owner_id": uid,
            "plan": "pro", "is_public": False, "root_person_id": None,
            "created_at": now_utc() - timedelta(days=400),
            "upgraded_at": now_utc() - timedelta(days=400),
            "expires_at": now_utc() - timedelta(days=1),
        })
        db.tree_members.insert_one({
            "id": str(uuid.uuid4()), "tree_id": tid, "user_id": uid,
            "role": "admin", "joined_at": now_utc() - timedelta(days=400),
        })
        try:
            r = requests.get(
                f"{BASE_URL}/api/trees",
                headers=_auth(admin_ctx["norm_token"]),
                timeout=30,
            )
            assert r.status_code == 200, r.text
            row = next(t for t in r.json() if t["id"] == tid)
            assert row["plan"] == "free", row
            log = db.activity_log.find_one(
                {"action": "plan.expired", "tree_id": tid}, {"_id": 0}
            )
            assert log, "plan.expired tidak tercatat"
            assert log["meta"]["from_plan"] == "pro"
            # Request kedua tidak boleh menulis log baru (modified_count == 0).
            requests.get(f"{BASE_URL}/api/trees", headers=_auth(admin_ctx["norm_token"]), timeout=30)
            assert db.activity_log.count_documents({"action": "plan.expired", "tree_id": tid}) == 1
        finally:
            db.activity_log.delete_many({"action": "plan.expired", "tree_id": tid})
            db.tree_members.delete_many({"tree_id": tid})
            db.trees.delete_many({"id": tid})

    def test_restore_writes_tree_restore_log(self, admin_ctx):
        db = admin_ctx["db"]
        tid = admin_ctx["tree_ids"][0]
        pid = f"TEST_RESTORE_{uuid.uuid4().hex[:8]}"
        try:
            r = requests.post(
                f"{BASE_URL}/api/restore",
                params={"tree_id": tid},
                json={"people": [{"id": pid, "name": "TEST Restore"}], "relations": []},
                headers=_auth(admin_ctx["super_token"]),
                timeout=30,
            )
            assert r.status_code == 200, r.text
            log = db.activity_log.find_one(
                {"action": "tree.restore", "tree_id": tid}, {"_id": 0}
            )
            assert log, "tree.restore tidak tercatat"
            assert log["meta"]["people"] == 1
        finally:
            db.activity_log.delete_many({"action": "tree.restore", "tree_id": tid})
            db.people.delete_many({"id": pid})

