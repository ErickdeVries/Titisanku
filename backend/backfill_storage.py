"""Backfill kuota penyimpanan per pohon (sekali jalan).

Latar belakang
--------------
Sejak kuota penyimpanan berbasis byte diperkenalkan, setiap upload menambah
`tree_usage.bytes`. Pohon yang sudah berisi foto SEBELUM fitur itu aktif tidak
punya catatan ukuran sama sekali, sehingga kuotanya tampak kosong (0 byte) dan
bisa melampaui batas tanpa terdeteksi.

Skrip ini menghitung ulang pemakaian nyata setiap pohon dari metadata Firebase
Storage (ukuran file dibaca tanpa mengunduh isinya), lalu menulis hasilnya ke
koleksi `tree_usage`.

Sumber file yang dihitung
-------------------------
1. `person_notes.attachments`  - file yang dilampirkan pada catatan orang
2. `people.gallery[].path`     - foto galeri
3. `family_chat.attachments`   - foto yang dikirim di chat keluarga

Path yang sama bisa muncul lebih dari sekali (mis. diunggah lalu dipakai di
beberapa tempat). Skrip menghitung setiap path HANYA SEKALI agar hasilnya sama
dengan biaya penyimpanan yang sebenarnya, bukan jumlah referensinya.

Cara pakai
----------
    # Pratinjau (tidak menulis apa pun)
    python backend/backfill_storage.py

    # Tulis hasilnya
    python backend/backfill_storage.py --apply

    # Hanya pohon tertentu
    python backend/backfill_storage.py --apply --tree <tree_id>

    # Lewati pengecekan file di storage (hanya untuk uji coba DB)
    python backend/backfill_storage.py --dry-run --no-verify

Skrip aman dijalankan berulang: hasilnya ditimpa (set), bukan ditambahkan, jadi
tidak akan menghitung ganda walau dijalankan dua kali.
"""

import argparse
import asyncio
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import server  # noqa: E402


def _norm(path):
    """Samakan bentuk path agar path yang sama tidak dihitung dua kali."""
    if not path or not isinstance(path, str):
        return None
    p = path.strip()
    if not p:
        return None
    # File bisa tersimpan sebagai "/api/files/<path>" atau URL penuh.
    if p.startswith("/api/files/"):
        p = p[len("/api/files/"):]
    p = p.split("?")[0]
    if p.startswith("http://") or p.startswith("https://"):
        # URL publik Firebase: .../o/<urlencoded-path>?...
        marker = "/o/"
        if marker in p:
            from urllib.parse import unquote

            p = unquote(p.split(marker, 1)[1])
        else:
            return None
    return p.lstrip("/")


async def collect_paths(db, tree_ids):
    """Kumpulkan semua path file per tree_id (tanpa duplikat)."""
    paths = defaultdict(set)

    async for note in db.person_notes.find(
        {"deleted_at": None}, {"_id": 0, "tree_id": 1, "attachments": 1}
    ):
        for a in note.get("attachments") or []:
            n = _norm(a)
            if n:
                paths[note.get("tree_id")].add(n)

    async for person in db.people.find(
        {"deleted_at": None}, {"_id": 0, "tree_id": 1, "gallery": 1}
    ):
        for g in person.get("gallery") or []:
            n = _norm((g or {}).get("path"))
            if n:
                paths[person.get("tree_id")].add(n)

    async for msg in db.family_chat.find(
        {"deleted_at": None}, {"_id": 0, "tree_id": 1, "attachments": 1}
    ):
        for a in msg.get("attachments") or []:
            n = _norm(a)
            if n:
                paths[msg.get("tree_id")].add(n)

    if tree_ids is not None:
        paths = {t: v for t, v in paths.items() if t in tree_ids}
    return paths


async def size_of(path, cache):
    """Ukuran file, atau None bila file benar-benar tidak ada.

    Error KONFIGURASI (kredensial storage belum diset) sengaja tidak ditelan:
    kalau ditelan, skrip akan melaporkan "file tidak ditemukan" untuk semua
    pohon dan hasil backfill jadi 0 MB yang menyesatkan.
    """
    if path in cache:
        return cache[path]
    try:
        size = await server.run_in_threadpool(server.object_size, path)
    except FileNotFoundError:
        size = None
    except server.integrations.IntegrationError:
        raise
    except Exception as e:
        raise RuntimeError(f"Gagal membaca ukuran {path}: {e}") from e
    cache[path] = size
    return size


async def main():
    ap = argparse.ArgumentParser(description="Backfill kuota penyimpanan per pohon.")
    ap.add_argument("--apply", action="store_true", help="Tulis hasil ke database (default: pratinjau).")
    ap.add_argument("--tree", help="Proses satu tree_id saja.")
    ap.add_argument("--no-verify", action="store_true", help="Jangan cek ukuran ke storage (hanya hitung referensi).")
    args = ap.parse_args()
    apply = args.apply and not args.no_verify

    tree_filter = {args.tree} if args.tree else None

    if not args.no_verify:
        # Gagal cepat bila storage belum dikonfigurasi, alih-alih melaporkan
        # semua file "tidak ditemukan" dan menghasilkan 0 MB.
        try:
            await server.run_in_threadpool(server.object_size, "__connectivity_check__")
        except server.integrations.IntegrationError as e:
            print("GAGAL: penyimpanan (Firebase Storage) belum dikonfigurasi.")
            print(f"  {e}")
            print("\nSet FIREBASE_SERVICE_ACCOUNT_JSON di backend/.env lalu jalankan ulang.")
            sys.exit(2)
        except FileNotFoundError:
            pass  # terhubung; objek uji memang tidak ada
        except Exception as e:
            print(f"GAGAL: tidak dapat menghubungi penyimpanan: {e}")
            sys.exit(2)

    # server.db sudah siap pakai setelah modul diimpor (env sudah dimuat
    # lewat load_dotenv di server.py), jadi tidak perlu connect manual.
    db = server.db
    print("Mengumpulkan daftar file per pohon...")
    paths = await collect_paths(db, tree_filter)
    total_files = sum(len(v) for v in paths.values())
    print(f"  {len(paths)} pohon, {total_files} file unik\n")

    cache = {}
    grand_total = 0
    rows = []

    for tree_id, file_paths in sorted(paths.items()):
        total = 0
        missing = 0
        for p in sorted(file_paths):
            size = await size_of(p, cache)
            if size is None:
                missing += 1
                continue
            total += size

        tree = await db.trees.find_one({"id": tree_id}, {"_id": 0, "id": 1, "name": 1, "plan": 1, "expires_at": 1})
        name = (tree or {}).get("name", "(pohon terhapus)")
        plan = server.effective_plan(tree or {})
        lim = server.storage_limit(plan)
        over = ""
        if lim is not None and total > lim:
            over = f"  !! MELEBIHI KUOTA {plan.upper()} ({server.fmt_size(lim)})"
        grand_total += total
        rows.append((tree_id, name, plan, len(file_paths), missing, total, over))
        shown = server.fmt_size(total) if total else "0 MB"
        print(f"  {name[:32]:32s} [{plan:6s}] {len(file_paths):4d} file  {shown:>9s}{over}")
        if missing:
            print(f"       {missing} path tidak ditemukan di storage (dilewati)")

        if apply:
            await db.tree_usage.update_one(
                {"tree_id": tree_id},
                {"$set": {"tree_id": tree_id, "bytes": total, "updated_at": server.now_utc()}},
                upsert=True,
            )

    print(f"\nTOTAL penyimpanan terhitung: {server.fmt_size(grand_total) if grand_total else '0 MB'}")
    over_count = sum(1 for r in rows if r[6])
    if over_count:
        print(f"PERHATIAN: {over_count} pohon melebihi kuota paketnya.")

    # Peringatan penting: 0 MB bisa berarti kuota memang kosong, ATAU file
    # sudah tidak ada di storage (data yatim). Jangan sampai admin mengira
    # backfill berhasil padahal file referensinya hilang.
    total_missing = sum(r[4] for r in rows)
    total_refs = sum(r[3] for r in rows)
    if total_refs and total_missing == total_refs:
        print("\n!! PERINGATAN: SEMUA file referensi tidak ditemukan di storage.")
        print("   Kemungkinan penyebab:")
        print("   - FIREBASE_STORAGE_BUCKET menunjuk bucket yang salah")
        print("   - file sudah dihapus manual dari storage (data yatim di DB)")
        print("   Hasil backfill 0 MB kemungkinan BUKAN mencerminkan pemakaian nyata.")
    elif total_missing:
        print(f"\n!! PERINGATAN: {total_missing} dari {total_refs} file tidak ditemukan di storage.")
        print("   Kuota yang tercatat lebih kecil dari jumlah referensi di database.")

    if apply:
        print(f"\nSELESAI: {len(rows)} baris tree_usage ditulis.")
    else:
        print("\nMODE PRATINJAU - tidak ada yang ditulis. Jalankan dengan --apply untuk menyimpan.")
    client = getattr(server, "client", None)
    if client is not None:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
