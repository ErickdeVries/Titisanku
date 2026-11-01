"""Cek manual dashboard admin terhadap backend lokal + database sekali pakai.

Bukan bagian dari pytest (nama file tidak diawali `test_`). Dipakai untuk
memverifikasi bahwa endpoint /admin/* setelah optimasi agregasi masih
mengembalikan angka yang benar dan jauh lebih cepat.

Jalankan backend dulu dengan DB_NAME=titisanku_verify, lalu (dari root repo):
    python backend/scripts/manual_admin_check.py \
        --url http://127.0.0.1:8011 --db titisanku_verify --yes-wipe

PERINGATAN — skrip ini MENGHAPUS isi koleksi yang dipakai untuk seed. Pengaman:
  * `--db` wajib berakhiran `_verify` dan tidak boleh sama dengan `DB_NAME`
    aplikasi (mis. `titisanku_atlas`), jadi database produksi tidak bisa kena.
  * tanpa `--yes-wipe` skrip berhenti sebelum menyentuh database.
  * `--url` non-lokal hanya diizinkan bila `--allow-remote` diberikan.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

BACKEND_DIR = Path(__file__).resolve().parents[1]   # backend/
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
load_dotenv(BACKEND_DIR / ".env")


def mongo_target(mongo_url: str) -> str:
    """Tampilkan tujuan koneksi tanpa membocorkan kredensial."""
    rest = mongo_url.split("://", 1)[-1]
    if "@" in rest:
        rest = rest.split("@", 1)[1]
    return rest.split("/", 1)[0] or "(unknown)"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt) -> str:
    return dt.isoformat()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8011")
    ap.add_argument("--db", default="titisanku_verify")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--yes-wipe", action="store_true",
                    help="wajib: menandakan kamu sadar koleksi di --db akan dihapus")
    ap.add_argument("--allow-remote", action="store_true",
                    help="izinkan --url non-lokal (default: hanya localhost)")
    args = ap.parse_args()

    mongo_url = os.environ.get("MONGO_URL")
    if not mongo_url:
        print("MONGO_URL belum diset", file=sys.stderr)
        return 2

    app_db = os.environ.get("DB_NAME") or ""
    if app_db and args.db == app_db:
        print(f"menolak: --db {args.db} sama dengan DB_NAME aplikasi", file=sys.stderr)
        return 3
    if not args.db.endswith("_verify"):
        print(f"menolak: --db '{args.db}' harus berakhiran '_verify'", file=sys.stderr)
        return 3
    url_host = (urlparse(args.url).hostname or "").lower()
    if url_host not in LOCAL_HOSTS and not args.allow_remote:
        print(f"menolak: --url {args.url} bukan lokal (pakai --allow-remote bila yakin)",
              file=sys.stderr)
        return 3
    print(f"target mongo={mongo_target(mongo_url)} db={args.db} api={args.url}")
    if not args.yes_wipe:
        print("berhenti: tambahkan --yes-wipe untuk menghapus lalu seed ulang data uji",
              file=sys.stderr)
        return 3

    client = MongoClient(mongo_url, serverSelectionTimeoutMS=15000)
    db = client[args.db]
    if args.reset:
        client.drop_database(args.db)

    # ---------------------------------------------------------------- seed
    admin_id = "user_seed_superadmin"
    token = "tok_" + uuid.uuid4().hex
    now = now_utc()
    db.users.delete_many({"user_id": admin_id})
    db.users.insert_one({
        "user_id": admin_id, "email": "emmusic.indonesia@gmail.com",
        "name": "SEED_SuperAdmin", "role": "admin", "created_at": now - timedelta(days=40),
    })
    db.user_sessions.insert_one({
        "session_token": token, "user_id": admin_id,
        "created_at": now, "expires_at": now + timedelta(days=7),
    })

    db.trees.delete_many({})
    db.tree_members.delete_many({})
    db.people.delete_many({})
    db.family_chat.delete_many({})
    db.payment_orders.delete_many({})
    db.activity_log.delete_many({})
    db.error_logs.delete_many({})
    db.tree_usage.delete_many({})

    plans = [
        ("tree_free", "free", None),
        ("tree_pro", "pro", now + timedelta(days=10)),
        ("tree_lapsed", "family", now - timedelta(days=2)),  # kedaluwarsa -> efektif free
    ]
    for tid, plan, exp in plans:
        doc = {"id": tid, "name": f"SEED {tid}", "owner_id": admin_id, "created_at": now - timedelta(days=5)}
        if plan != "free":
            doc.update({"plan": plan, "expires_at": exp})
        db.trees.insert_one(doc)
        db.tree_members.insert_one({
            "id": str(uuid.uuid4()), "tree_id": tid, "user_id": admin_id,
            "role": "admin", "joined_at": now - timedelta(days=5),
        })

    for i in range(7):
        db.people.insert_one({
            "id": str(uuid.uuid4()), "tree_id": "tree_pro", "name": f"SEED person {i}",
            "created_by": admin_id, "created_at": now - timedelta(days=i % 3),
            "deleted_at": None, "is_root": i == 0, "photo_url": "x" if i < 2 else None,
        })
    for i in range(3):
        db.family_chat.insert_one({
            "id": str(uuid.uuid4()), "tree_id": "tree_pro", "sender_id": admin_id,
            "message": "halo", "created_at": now - timedelta(days=i), "deleted_at": None,
        })

    for i, (status, amount, days_ago) in enumerate([
        ("paid", 149000, 1), ("paid", 0, 4), ("pending", 149000, 2),
    ]):
        db.payment_orders.insert_one({
            "id": f"order_{i}", "tree_id": "tree_pro", "user_id": admin_id,
            "plan": "pro", "provider": "midtrans", "status": status, "amount": amount,
            "created_at": now - timedelta(days=days_ago),
            "paid_at": now - timedelta(days=days_ago) if status == "paid" else None,
        })

    db.activity_log.insert_many([
        {"id": str(uuid.uuid4()), "action": "auth.login", "actor_id": admin_id,
         "actor_email": "emmusic.indonesia@gmail.com", "created_at": now - timedelta(hours=2)},
        {"id": str(uuid.uuid4()), "action": "person.add", "actor_id": admin_id,
         "actor_email": "emmusic.indonesia@gmail.com", "created_at": now - timedelta(hours=1)},
    ])
    db.error_logs.insert_one({
        "id": str(uuid.uuid4()), "path": "/api/boom", "status": 500, "message": "seed error",
        "created_at": now - timedelta(hours=1),
    })
    db.tree_usage.insert_one({"tree_id": "tree_pro", "bytes": 12345})

    h = {"Authorization": f"Bearer {token}"}
    results = {}

    def call(path: str):
        t0 = time.perf_counter()
        r = requests.get(f"{args.url}/api{path}", headers=h, timeout=120)
        ms = (time.perf_counter() - t0) * 1000
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:400]}"
        return r.json(), round(ms, 1)

    overview, ms = call("/admin/overview")
    results["overview"] = (ms, {
        "total_users": overview["business"]["total_users"],
        "plans": overview["business"]["plans"],
        "funnel": overview["funnel"],
        "db_counts": overview["tech"]["db_counts"],
    })
    assert overview["business"]["plans"]["free"] == 2, overview["business"]["plans"]
    assert overview["business"]["plans"]["pro"] == 1, overview["business"]["plans"]
    assert overview["tech"]["db_counts"]["people"] == 7
    assert overview["tech"]["db_counts"]["relations"] == 0

    growth, ms = call("/admin/growth?days=7")
    growth_summary = {
        "series_last": growth["series"][-1],
        "series_people_sum": sum(p["people"] for p in growth["series"]),
        "series_messages_sum": sum(p["messages"] for p in growth["series"]),
        "series_revenue_sum": sum(p["revenue"] for p in growth["series"]),
        "totals": growth["totals"],
        "engagement": growth["engagement"],
        "funnel": growth["funnel"],
    }
    results["growth"] = (ms, growth_summary)
    assert growth_summary["series_people_sum"] == 7, growth_summary
    assert growth_summary["series_messages_sum"] == 3, growth_summary
    assert growth_summary["series_revenue_sum"] == 149000 * 2, growth_summary
    assert growth_summary["totals"]["paid_trees"] == 1, growth_summary["totals"]
    assert growth_summary["engagement"]["dau"] == 1, growth_summary["engagement"]

    finance, ms = call("/admin/finance?days=30")
    results["finance"] = (ms, {
        "revenue": finance["revenue"], "subscriptions": finance["subscriptions"],
        "recent": finance["recent"][:2], "top": finance["top_trees"],
    })
    assert finance["revenue"]["total"] == 149000 * 2, finance["revenue"]
    assert finance["recent"] and finance["recent"][0]["tree_name"] == "SEED tree_pro"
    assert finance["top_trees"] and finance["top_trees"][0]["owner_email"] == "emmusic.indonesia@gmail.com"

    trees, ms = call("/admin/trees")
    results["trees"] = (ms, {
        "total": trees["total"], "plan_counts": trees["plan_counts"],
        "trees": [{k: t[k] for k in ("name", "plan", "people", "members", "messages", "storage_used")}
                  for t in trees["trees"]],
    })
    by_name = {t["name"]: t for t in trees["trees"]}
    assert by_name["SEED tree_pro"]["people"] == 7
    assert by_name["SEED tree_pro"]["messages"] == 3
    assert by_name["SEED tree_pro"]["storage_used"] == 12345
    assert by_name["SEED tree_lapsed"]["plan"] == "free", by_name["SEED tree_lapsed"]

    users, ms = call("/admin/users")
    results["users"] = (ms, [{"email": u["email"], "tree_count": u["tree_count"]} for u in users["users"]])
    assert all(u["tree_count"] == 3 for u in users["users"])

    activity, ms = call("/admin/activity?days=30")
    results["activity"] = (ms, {"total": activity["total"], "by_action": activity.get("by_action")})

    errors, ms = call("/admin/errors?days=30")
    results["errors"] = (ms, {"total": errors["total"], "count_24h": errors["count_24h"]})

    system, ms = call("/admin/system")
    results["system"] = (ms, {"collections": system["collections"], "uptime_s": system.get("uptime_s")})
    assert system["collections"]["people"] == 7

    print(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    print("\nSemua assertion lolos.")
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
