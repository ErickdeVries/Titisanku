"""Perbaiki pohon "yatim" (orphan) — pohon yang orangnya masih ada tapi dokumen
`trees`-nya kehilangan `owner_id`/`tree_members`, sehingga tidak muncul di
`GET /trees` dan tampak seperti "data hilang" di aplikasi.

Kasus yang ditangani (lihat insiden 2026-11-01):
  * `trees` hanya berisi `{id, name}` karena koleksi `trees`/`users` pernah
    ditimpa, sementara `people` + `relations` tetap utuh.
  * Akibatnya `list_trees()` (yang membaca `tree_members`) tidak menemukan
    pohon tsb dan aplikasi hanya menampilkan pohon baru yang kosong.

Skrip ini TIDAK menghapus apa pun. Yang dilakukan (dengan `--apply`):
  1. Menulis backup dokumen terdampak ke `backups/repair_orphan_<ts>.json`.
  2. Melengkapi dokumen `trees`: owner_id, plan, root_person_id, created_at,
     is_public, demo.
  3. Menambahkan baris `tree_members` (role admin) untuk pemilik.
  4. Memetakan ulang `created_by` pada people/relations dari user lama yang
     sudah tidak ada di koleksi `users` ke pemilik yang baru, supaya aturan
     "pemilik catatan" (card privacy, izin edit) kembali berlaku.

Pemakaian (dari root repo):
    python backend/scripts/repair_orphan_tree.py --email <email>            # dry-run
    python backend/scripts/repair_orphan_tree.py --email <email> --apply    # tulis

Pengaman:
  * default = dry-run; hanya mencetak rencana perubahan.
  * `--apply` ke cluster Mongo NON-lokal (mis. Atlas produksi) wajib ditambah
    `--yes-remote`, supaya tidak ada penulisan produksi tanpa niat eksplisit.
  * backup dokumen terdampak selalu ditulis ke `backups/` sebelum menulis.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

BACKEND_DIR = Path(__file__).resolve().parents[1]   # backend/
ROOT = Path(__file__).resolve().parents[2]          # root repo
BACKUP_DIR = ROOT / "backups"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def mongo_target(mongo_url: str) -> str:
    """Tampilkan tujuan koneksi tanpa membocorkan kredensial."""
    rest = mongo_url.split("://", 1)[-1]
    if "@" in rest:
        rest = rest.split("@", 1)[1]
    return rest.split("/", 1)[0] or "(unknown)"


def is_local(mongo_url: str) -> bool:
    host = mongo_target(mongo_url).split(":", 1)[0].lower()
    return host in LOCAL_HOSTS


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso(dt) -> str | None:
    return dt.isoformat() if isinstance(dt, datetime) else dt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", required=True, help="email pemilik pohon (akun yang dipakai di aplikasi)")
    ap.add_argument("--db", default=None, help="nama database (default: DB_NAME di env)")
    ap.add_argument("--apply", action="store_true", help="tulis perubahan (default: hanya dry-run)")
    ap.add_argument(
        "--yes-remote",
        action="store_true",
        help="wajib bila --apply menargetkan Mongo non-lokal (mis. Atlas produksi)",
    )
    args = ap.parse_args()

    load_dotenv(BACKEND_DIR / ".env")
    mongo_url = os.environ.get("MONGO_URL")
    if not mongo_url:
        print("MONGO_URL belum diset", file=sys.stderr)
        return 2
    db_name = args.db or os.environ.get("DB_NAME")
    if not db_name:
        print("nama database tidak diketahui (set --db atau DB_NAME)", file=sys.stderr)
        return 2

    target = mongo_target(mongo_url)
    print(f"target mongo={target} db={db_name} mode={'APPLY' if args.apply else 'dry-run'}")
    if args.apply and not is_local(mongo_url) and not args.yes_remote:
        print(
            "menolak menulis ke Mongo non-lokal tanpa --yes-remote "
            f"(target={target} db={db_name})",
            file=sys.stderr,
        )
        return 3

    client = MongoClient(mongo_url, serverSelectionTimeoutMS=15000)
    db = client[db_name]

    user = db.users.find_one({"email": args.email}, {"_id": 0})
    if not user:
        print(f"user {args.email} tidak ditemukan di db {db_name}", file=sys.stderr)
        return 2
    owner_id = user["user_id"]
    print(f"db={db_name} owner={owner_id} ({user.get('email')})")

    known_users = {u["user_id"] for u in db.users.find({}, {"_id": 0, "user_id": 1})}

    candidates = []
    for tree in db.trees.find({}):
        tid = tree.get("id")
        if not tid:
            continue
        people = db.people.count_documents({"tree_id": tid})
        members = db.tree_members.count_documents({"tree_id": tid})
        owner = tree.get("owner_id")
        tree_owner_valid = bool(owner) and owner in known_users
        if people == 0:
            continue
        # "Yatim": tidak ada anggota sama sekali, atau dokumen pohon tidak punya
        # owner yang valid padahal orangnya banyak.
        if members == 0 or not tree_owner_valid:
            candidates.append((tree, people, members, tree_owner_valid))

    if not candidates:
        print("tidak ada pohon yatim — data sudah konsisten")
        client.close()
        return 0

    changes: list[dict] = []
    backups: list[dict] = []

    for tree, people, members, tree_owner_valid in candidates:
        tid = tree["id"]
        root = db.people.find_one(
            {"tree_id": tid, "is_root": True, "deleted_at": None}, {"_id": 0, "id": 1}
        ) or db.people.find_one({"tree_id": tid, "deleted_at": None}, {"_id": 0, "id": 1})
        first = db.people.find_one(
            {"tree_id": tid}, {"_id": 0, "created_at": 1}, sort=[("created_at", 1)]
        )
        created_at = iso((first or {}).get("created_at")) or now_utc().isoformat()

        legacy_ids = set()
        for row in db.people.find({"tree_id": tid}, {"_id": 0, "created_by": 1}):
            if row.get("created_by"):
                legacy_ids.add(row["created_by"])
        for row in db.relations.find({"tree_id": tid}, {"_id": 0, "created_by": 1}):
            if row.get("created_by"):
                legacy_ids.add(row["created_by"])
        legacy_ids -= known_users

        tree_set = {
            "owner_id": owner_id,
            "plan": tree.get("plan") or "free",
            "is_public": bool(tree.get("is_public", False)),
            "demo": bool(tree.get("demo", False)),
            "created_at": tree.get("created_at") or created_at,
            "root_person_id": tree.get("root_person_id") or (root or {}).get("id"),
            "updated_at": now_utc().isoformat(),
        }
        changes.append({
            "tree_id": tid,
            "name": tree.get("name"),
            "people": people,
            "members_before": members,
            "tree_set": tree_set,
            "add_member": True,
            "remap_created_by": sorted(legacy_ids),
        })

        backups.append({
            "tree": {k: iso(v) for k, v in tree.items() if k != "_id"},
            "tree_members": [ {k: iso(v) for k, v in m.items() if k != "_id"}
                              for m in db.tree_members.find({"tree_id": tid}) ],
            "people": [ {k: iso(v) for k, v in p.items() if k != "_id"}
                        for p in db.people.find({"tree_id": tid}) ],
            "relations": [ {k: iso(v) for k, v in r.items() if k != "_id"}
                           for r in db.relations.find({"tree_id": tid}) ],
        })

    print(json.dumps(changes, indent=2, ensure_ascii=False))

    if not args.apply:
        print("\nDRY-RUN: tidak ada yang ditulis. Jalankan ulang dengan --apply.")
        client.close()
        return 0

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = now_utc().strftime("%Y%m%d_%H%M%S")
    out = BACKUP_DIR / f"repair_orphan_{stamp}.json"
    out.write_text(json.dumps(backups, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"backup ditulis: {out}")

    for ch in changes:
        tid = ch["tree_id"]
        db.trees.update_one({"id": tid}, {"$set": ch["tree_set"]})
        if not db.tree_members.find_one({"tree_id": tid, "user_id": owner_id}):
            db.tree_members.insert_one({
                "id": str(uuid.uuid4()),
                "tree_id": tid,
                "user_id": owner_id,
                "role": "admin",
                "joined_at": ch["tree_set"]["created_at"],
            })
        for legacy in ch["remap_created_by"]:
            db.people.update_many(
                {"tree_id": tid, "created_by": legacy}, {"$set": {"created_by": owner_id}}
            )
            db.relations.update_many(
                {"tree_id": tid, "created_by": legacy}, {"$set": {"created_by": owner_id}}
            )
        print(f"OK {tid} '{ch['name']}' -> owner {owner_id}, "
              f"{ch['people']} orang, created_by dirapikan: {ch['remap_created_by']}")

    # Verifikasi akhir
    print("\nVERIFIKASI:")
    for m in db.tree_members.find({"user_id": owner_id}, {"_id": 0}):
        n = db.people.count_documents({"tree_id": m["tree_id"], "deleted_at": None})
        t = db.trees.find_one({"id": m["tree_id"]}, {"_id": 0, "name": 1}) or {}
        print(f"  {m['tree_id']} '{t.get('name')}' role={m['role']} orang={n}")
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
