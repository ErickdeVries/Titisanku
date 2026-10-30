"""Backend tests for KETURUNANKU 3-tier subscription plans + limit enforcement.

CRITICAL: DB may hold REAL production data. This file MUST only insert synthetic
docs and MUST only delete docs it created (tracked in the module-level CREATED
registry). NEVER call delete_many({}).

Setiap kelas test memakai user admin-nya SENDIRI (fixture `admin`), supaya file
ini bisa dijalankan berulang kali tanpa perlu truncate DB dan aman diparalelkan
(--dist loadfile / -n 0).
"""
import hashlib
import io
import os
import uuid
import secrets
from datetime import datetime, timezone, timedelta

import pytest
import requests
from bson import DBRef, ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

# Pakai EXPO_PUBLIC_BACKEND_URL/EXPO_BACKEND_URL bila di-set, supaya sama
# dengan konfigurasi suite lain di backend/tests.
BASE_URL = (
    os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or os.environ.get("EXPO_BACKEND_URL")
    or "http://localhost:8001"
).rstrip("/") + "/api"

# Kunci yang sama dipakai backend untuk memverifikasi signature webhook Midtrans.
MIDTRANS_SERVER_KEY = os.environ.get("MIDTRANS_SERVER_KEY", "")

_client = MongoClient(MONGO_URL)
db = _client[DB_NAME]


def now_utc():
    return datetime.now(timezone.utc)


# Registry of everything we create so teardown deletes ONLY our synthetic docs
# State bersama untuk ISOLASI module: saat file dijalankan dengan
# `--dist loadfile`/`-n 0`, semua test file ini berada di worker yang sama,
# jadi STATE aman dipakai. Setiap kelas tetap memakai akun admin sendiri.
STATE = {}

CREATED = {
    "user_ids": set(),
    "session_tokens": set(),
    "tree_ids": set(),
    "person_ids": set(),
    "note_ids": set(),
    "invite_tokens": set(),
    "member_ids": set(),   # tree_members _uuid_ ids that we inserted directly
    "storage_paths": set(),  # fs.files filename yang disuntikkan test kuota
}


def _seed_user(name_prefix="PLAN"):
    uid = f"user_{uuid.uuid4().hex[:12]}"
    tok = secrets.token_hex(16)
    email = f"TEST_PLAN_{uid[-6:]}@example.com"
    db.users.insert_one({
        "user_id": uid,
        "email": email,
        "name": f"TEST_{name_prefix}_{uid[-4:]}",
        "picture": None,
        "role": "admin",   # global role (only used for legacy endpoints)
        "created_at": now_utc(),
    })
    db.user_sessions.insert_one({
        "session_token": tok,
        "user_id": uid,
        "created_at": now_utc(),
        "expires_at": now_utc() + timedelta(days=7),
    })
    CREATED["user_ids"].add(uid)
    CREATED["session_tokens"].add(tok)
    return uid, tok, email


def auth(tok):
    return {"Authorization": f"Bearer {tok}"}


# Harga resmi (Rupiah) yang harus sama dengan backend & layar langganan.
PLAN_PRICE = {"pro": 149000, "family": 199000}


def _upgrade_via_payment(tree_id, plan):
    """Naikkan plan lewat jalur pembayaran resmi (webhook Midtrans).

    Endpoint POST /trees/{id}/upgrade sengaja hanya untuk superadmin; plan
    berbayar WAJIB lewat pembayaran. Test ini menyuntikkan order pending lalu
    mengirim notifikasi webhook dengan signature SHA-512 yang valid, sehingga
    yang diuji adalah logika aktivasi yang sesungguhnya.
    """
    order_id = f"TEST-{uuid.uuid4().hex[:16]}"
    amount = PLAN_PRICE[plan]
    db.payment_orders.insert_one({
        "order_id": order_id, "user_id": _owner_of(tree_id),
        "tree_id": tree_id, "plan": plan, "amount": amount,
        "status": "pending", "created_at": now_utc(),
    })
    CREATED.setdefault("order_ids", set()).add(order_id)
    gross = f"{amount}.00"
    raw = f"{order_id}200{gross}{MIDTRANS_SERVER_KEY}"
    r = requests.post(
        f"{BASE_URL}/payments/notification",
        json={
            "order_id": order_id, "status_code": "200", "gross_amount": gross,
            "signature_key": hashlib.sha512(raw.encode()).hexdigest(),
            "transaction_status": "settlement", "fraud_status": "accept",
        },
        timeout=30,
    )
    assert r.status_code == 200, f"webhook pembayaran gagal: {r.status_code} {r.text}"


def _owner_of(tree_id):
    tree = db.trees.find_one({"id": tree_id}, {"owner_id": 1})
    return (tree or {}).get("owner_id")


def _stored_bytes(path):
    """Ukuran objek storage untuk `path` (format GridFS yang dipakai backend).

    Backend mencatat pemakaian lewat `add_storage_usage`, jadi test kuota cukup
    menyisipkan objek berukuran sama — tanpa benar-benar mengunggah file.
    """
    files = MongoClient(MONGO_URL)[DB_NAME]["fs.files"].find_one(
        {"filename": path}, {"length": 1}
    )
    return int((files or {}).get("length") or 0)


def _api_create_tree(tok, name):
    r = requests.post(f"{BASE_URL}/trees", headers=auth(tok), json={"name": name}, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    CREATED["tree_ids"].add(data["id"])
    return data


def _api_create_tree_unlimited(tok, name):
    """Buat pohon tanpa batas "1 pohon per akun" (khusus test).

    Dipakai hanya bila satu test butuh >1 pohon pada akun yang sama, karena
    POST /trees menolak pohon kedua. Dokumen yang dibuat tetap terdaftar di
    CREATED sehingga dibersihkan di teardown.
    """
    owner_id = db.user_sessions.find_one({"session_token": tok})["user_id"]
    user = db.users.find_one({"user_id": owner_id})
    return _create_tree_direct(user, name)


def _create_tree_direct(user, name):
    """Cermin `create_tree_for_user` di backend, untuk kebutuhan test paralel."""
    tree_id = f"tree_{uuid.uuid4().hex[:12]}"
    root_id = str(uuid.uuid4())
    db.people.insert_one({
        "id": root_id, "tree_id": tree_id, "name": user["name"],
        "email": user.get("email"), "gender": None, "birth_date": None,
        "birth_place": None, "death_date": None,
        "photo_url": user.get("picture"), "job": None, "is_adopted": False,
        "notes": None, "is_alive": True, "is_root": True,
        "created_by": user["user_id"], "created_at": now_utc(), "deleted_at": None,
    })
    db.trees.insert_one({
        "id": tree_id, "name": name, "owner_id": user["user_id"], "plan": "free",
        "is_public": False, "root_person_id": root_id, "created_at": now_utc(),
    })
    db.tree_members.insert_one({
        "id": str(uuid.uuid4()), "tree_id": tree_id, "user_id": user["user_id"],
        "role": "admin", "joined_at": now_utc(),
    })
    CREATED["tree_ids"].add(tree_id)
    return {"id": tree_id, "root_id": root_id, "plan": "free"}


# ---------------------------------------------------------------------------
# Fixture admin: satu user admin barus untuk setiap kelas test.
#
# Sebelumnya dipakai satu `admin["tok"]` level-sesi, sehingga test kedua
# yang membuat pohon gagal dengan "Anda sudah memiliki satu pohon". Dengan
# fixture ini setiap kelas memakai akun sendiri: bisa dijalankan berulang tanpa
# truncate DB, dan tetap benar walau kelas dibagi ke worker berbeda.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="function")
def admin():
    """Akun admin BARU untuk setiap test.

    Scope `function` (bukan `class`) penting: banyak test membuat pohon baru,
    dan POST /trees menolak akun yang sudah punya pohon. Dengan akun per-test,
    setiap test mandiri — tidak bergantung pada test lain dan aman diulang.
    """
    uid, tok, email = _seed_user("ADMIN")
    return {"id": uid, "tok": tok, "email": email}


@pytest.fixture(scope="session", autouse=True)
def _teardown_created():
    """Hapus dokumen yang dibuat file ini saja (tidak pernah wipe koleksi)."""
    yield
    # Teardown: delete ONLY docs we created.
    tids = list(CREATED["tree_ids"])
    if tids:
        db.people.delete_many({"tree_id": {"$in": tids}})
        db.relations.delete_many({"tree_id": {"$in": tids}})
        db.tree_members.delete_many({"tree_id": {"$in": tids}})
        db.trees.delete_many({"id": {"$in": tids}})
        db.family_chat.delete_many({"tree_id": {"$in": tids}})
        db.person_notes.delete_many({"tree_id": {"$in": tids}})
        db.app_notifications.delete_many({"tree_id": {"$in": tids}})
        db.tree_invites.delete_many({"tree_id": {"$in": tids}})
        db.tree_usage.delete_many({"tree_id": {"$in": tids}})
    oids = list(CREATED.get("order_ids") or ())
    if oids:
        db.payment_orders.delete_many({"order_id": {"$in": oids}})
    paths = list(CREATED["storage_paths"])
    if paths:
        db["fs.files"].delete_many({"filename": {"$in": paths}})
    uids = list(CREATED["user_ids"])
    if uids:
        db.users.delete_many({"user_id": {"$in": uids}})
        db.tree_members.delete_many({"user_id": {"$in": uids}})
        db.user_sessions.delete_many({"user_id": {"$in": uids}})


# ===========================================================================
# 1. Basic tree creation + list-shape (plan_limits, editor_count, photo_count)
# ===========================================================================
class TestTreeCreateAndList:
    """POST /trees + GET /trees konsisten. Satu test karena `admin` ber-scope
    function: membuat pohon di satu test tidak otomatis terlihat di test lain."""

    def test_create_tree_and_listing_are_consistent(self):
        uid, tok, email = _seed_user("ADMIN")  # user baru -> boleh punya pohon
        data = _api_create_tree(tok, "TEST_PLAN_TreeCreate")
        tid = data["id"]

        # --- Respons POST /trees ---
        assert data["role"] == "admin"
        assert data["plan"] == "free"
        assert data["person_count"] == 1
        assert data["member_count"] == 1
        assert data["limit"] == 50
        # "photos" sudah diganti kuota byte -> storage_limit (byte).
        assert data["plan_limits"] == {"people": 50, "editors": 3}
        assert data["storage_limit"] == 500 * 1024 * 1024
        assert data["storage_used"] == 0

        # --- Item di GET /trees harus berbentuk sama ---
        r = requests.get(f"{BASE_URL}/trees", headers=auth(tok), timeout=15)
        assert r.status_code == 200, r.text
        t = next((x for x in r.json() if x["id"] == tid), None)
        assert t is not None, "Pohon baru tidak muncul di GET /trees"
        for key in ("role", "person_count", "member_count", "editor_count",
                    "photo_count", "plan_limits", "limit",
                    "storage_used", "storage_limit"):
            assert key in t, f"missing key '{key}' in /trees item: {t}"
        assert t["role"] == "admin"
        assert t["editor_count"] == 0
        assert t["photo_count"] == 0
        assert t["plan_limits"]["people"] == 50
        assert t["plan_limits"]["editors"] == 3
        assert t["storage_limit"] == 500 * 1024 * 1024
        assert t["limit"] == 50

        # --- GET /tree mengembalikan root person ---
        r = requests.get(f"{BASE_URL}/tree", params={"tree_id": tid},
                         headers=auth(tok), timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["root_id"] is not None
        assert d["role"] == "admin"


def _need(key):
    """Ambil STATE milik test prasyarat; gagal dengan pesan jelas bila belum jalan.

    Sebagian test di file ini memang berurutan dalam satu kelas (alur 2 pohon,
    batas 50 orang, dsb). Membuat ketergantungannya eksplisit lebih baik
    daripada KeyError misterius saat pytest menyeleksi sebagian test.
    """
    if key not in STATE:
        pytest.fail(
            f"STATE[{key!r}] belum diisi — jalankan test prasyarat di kelas yang sama "
            f"(mis. `pytest tests/test_plans.py::{_PREREQ.get(key, '?')}`).",
        )
    return STATE[key]


# Kelas yang mengisi STATE tertentu, untuk pesan bantuan.
_PREREQ = {
    "ct_tree_id": "TestTreeCreateAndList",
    "ct_root_id": "TestTreeCreateAndList",
    "A": "TestTwoTreeFlow",
    "B": "TestTwoTreeFlow",
    "A_root": "TestTwoTreeFlow",
}


def _transfer_tree_to(admin, tree_id):
    """Pindahkan kepemilikan pohon ke admin kelas ini.

    Aturan produk: satu user hanya boleh memiliki SATU pohon aktif. Test plan
    membutuhkan pohon berbagi antar kelas (pohon A diisi s.d. 50 orang), jadi
    kepemilikan dipindah langsung di DB — bukan celah API.
    """
    db.trees.update_one({"id": tree_id}, {"$set": {"owner_id": admin["id"]}})
    db.tree_members.update_one(
        {"tree_id": tree_id, "user_id": admin["id"]},
        {"$set": {"role": "admin"}},
    )
    return tree_id


# ===========================================================================
# 2. THE 2-TREE FLOW — Tree A free, Tree B upgraded to pro
# ===========================================================================
# ===========================================================================
# Pohon A (free) & B (pro) dipakai lintas kelas. Dibuat lewat fixture dengan
# scope SESSION supaya:
#   * hanya dibuat sekali, dan
#   * ketergantungannya eksplisit (fixture), bukan urutan eksekusi tersembunyi.
# Keduanya dimiliki akun admin khusus (bukan akun test lain), sehingga kelas
# mana pun bisa memakainya tanpa saling menimpa kepemilikan.
# ===========================================================================
@pytest.fixture
def tree_ab():
    """Pohon A (free) + pohon B (pro) pada akun admin baru untuk test ini.

    Ber-scope function supaya aman dijalankan paralel (xdist): tidak ada state
    bersama antar worker. Pohon A dibuat langsung di DB karena POST /trees
    membatasi 1 pohon per akun.
    """
    uid, tok, _email = _seed_user("AB")
    owner = {"id": uid, "tok": tok}

    b = _api_create_tree(tok, "TEST_PLAN_TreeB")
    _upgrade_via_payment(b["id"], "pro")

    a = _api_create_tree_unlimited(tok, "TEST_PLAN_TreeA")
    return {"A": a["id"], "A_root": a["root_id"], "B": b["id"], "owner": owner}


class TestTwoTreeFlow:
    def test_setup_two_trees_and_upgrade_b(self, tree_ab):
        r = requests.get(f"{BASE_URL}/trees", headers=auth(tree_ab["owner"]["tok"]),
                         timeout=15)
        assert r.status_code == 200, r.text
        plans = {t["id"]: t["plan"] for t in r.json()}
        assert plans[tree_ab["A"]] == "free"
        assert plans[tree_ab["B"]] == "pro"

    def test_list_shows_a_free_and_b_pro(self, tree_ab):
        r = requests.get(f"{BASE_URL}/trees", headers=auth(tree_ab["owner"]["tok"]), timeout=15)
        assert r.status_code == 200, r.text
        trees = {t["id"]: t for t in r.json()}
        a, b = trees[tree_ab["A"]], trees[tree_ab["B"]]
        # Tree A remains free
        assert a["plan"] == "free"
        assert a["limit"] == 50
        # "photos" sudah diganti kuota byte -> lihat storage_limit di bawah.
        assert a["plan_limits"] == {"people": 50, "editors": 3}
        # Tree B is pro: people unlimited (None), editors=10
        assert b["plan"] == "pro"
        assert b["limit"] is None
        assert b["plan_limits"]["editors"] == 10
        assert b["plan_limits"]["people"] is None
        assert b["storage_limit"] > a["storage_limit"]


@pytest.fixture(scope="class")
def people_tree():
    """Pohon free yang dipakai berurutan oleh TestPeopleLimit (isi 50 orang ->
    402 -> upgrade -> 200). Scope `class` agar ketiga test berbagi pohon yang
    sama, dan sengaja dipisah dari `tree_ab` supaya upgrade di sini tidak
    mengubah plan pohon A yang dipakai test lain."""
    uid, tok, _email = _seed_user("PEOPLE")
    tree = _api_create_tree_unlimited(tok, "TEST_PLAN_PeopleTree")
    return {"id": tree["id"], "root_id": tree["root_id"],
            "owner": {"id": uid, "tok": tok}}


# ===========================================================================
# 3. PEOPLE LIMIT — free = 50, then upgrade unlocks
# ===========================================================================
class TestPeopleLimit:
    """Memakai pohon A dari fixture `tree_ab`. Diisi 50 orang lewat seed DB
    (cepat), lalu add-relative harus 402; setelah upgrade harus 200.
    """

    def test_free_tree_402_at_51st(self, people_tree):
        admin = people_tree["owner"]
        tid = people_tree["id"]
        tok = admin["tok"]
        # get root
        r = requests.get(f"{BASE_URL}/tree", params={"tree_id": tid},
                         headers=auth(tok), timeout=15)
        assert r.status_code == 200, r.text
        root = r.json()["root_id"]
        # Tree A has 1 person (root) — insert 49 synthetic to reach 50.
        docs = []
        for i in range(49):
            pid = str(uuid.uuid4())
            docs.append({
                "id": pid, "tree_id": tid, "name": f"TEST_PLAN_Fill_{i}",
                "gender": None, "is_alive": True, "is_root": False,
                "created_by": admin["id"], "created_at": now_utc(),
                "deleted_at": None,
            })
            CREATED["person_ids"].add(pid)
        db.people.insert_many(docs)
        assert db.people.count_documents({"tree_id": tid, "deleted_at": None}) == 50

        # 51st via API MUST 402 LIMIT_REACHED
        r = requests.post(f"{BASE_URL}/people/add-relative",
                          params={"tree_id": tid}, headers=auth(tok),
                          json={"focus_id": root, "direction": "child",
                                "person": {"name": "TEST_PLAN_51st"}}, timeout=15)
        assert r.status_code == 402, r.text
        assert r.json()["detail"].startswith("LIMIT_REACHED:")

    def test_upgrade_to_pro_unlocks_add(self, people_tree):
        admin = people_tree["owner"]
        tid = people_tree["id"]
        tok = admin["tok"]
        # Upgrade A to pro lewat jalur pembayaran (helper sudah assert 200).
        _upgrade_via_payment(tid, "pro")

        # get root & add beyond 50
        r = requests.get(f"{BASE_URL}/tree", params={"tree_id": tid},
                         headers=auth(tok), timeout=15)
        root = r.json()["root_id"]
        r = requests.post(f"{BASE_URL}/people/add-relative",
                          params={"tree_id": tid}, headers=auth(tok),
                          json={"focus_id": root, "direction": "child",
                                "person": {"name": "TEST_PLAN_AfterPro"}}, timeout=15)
        assert r.status_code == 200, r.text
        CREATED["person_ids"].add(r.json()["person"]["id"])
        assert db.people.count_documents({"tree_id": tid, "deleted_at": None}) >= 51

    def test_pro_tree_reports_unlimited(self, people_tree):
        r = requests.get(f"{BASE_URL}/tree", params={"tree_id": people_tree["id"]},
                         headers=auth(people_tree["owner"]["tok"]), timeout=15)
        assert r.status_code == 200
        assert r.json()["limit"] is None


# ===========================================================================
# 4. UPGRADE plan values + RBAC
# ===========================================================================
class TestUpgradeRBAC:
    def test_family_plan_gives_editors_50_people_none(self, admin):
        # Create a fresh tree so we don't disturb existing state
        t = _api_create_tree(admin["tok"], "TEST_PLAN_FamilyTree")
        tid = t["id"]
        _upgrade_via_payment(tid, "family")  # assert 200 di dalam helper
        # Verify plan_limits shape
        r = requests.get(f"{BASE_URL}/trees", headers=auth(admin["tok"]), timeout=15)
        t = next(x for x in r.json() if x["id"] == tid)
        assert t["plan"] == "family"
        assert t["plan_limits"]["editors"] == 50
        assert t["plan_limits"]["people"] is None
        # Family = 25 GB (bukan jumlah foto lagi).
        assert t["storage_limit"] == 25 * 1024 * 1024 * 1024
        assert t["limit"] is None

    def test_pro_upgrade_accepted(self, admin):
        t = _api_create_tree(admin["tok"], "TEST_PLAN_ProTree")
        _upgrade_via_payment(t['id'], "pro")  # assert 200 di dalam helper

    def test_non_admin_cannot_upgrade(self, admin):
        # Create tree with admin, then seed a second user as viewer + editor member
        t = _api_create_tree(admin["tok"], "TEST_PLAN_RBACTree")
        tid = t["id"]

        # Seed a viewer member
        viewer_id, viewer_tok, _ = _seed_user("VIEWER")
        mid = str(uuid.uuid4())
        db.tree_members.insert_one({
            "id": mid, "tree_id": tid, "user_id": viewer_id,
            "role": "viewer", "joined_at": now_utc(),
        })
        CREATED["member_ids"].add(mid)

        # Also seed as editor via another user
        editor_id, editor_tok, _ = _seed_user("EDITOR")
        mid2 = str(uuid.uuid4())
        db.tree_members.insert_one({
            "id": mid2, "tree_id": tid, "user_id": editor_id,
            "role": "editor", "joined_at": now_utc(),
        })
        CREATED["member_ids"].add(mid2)

        # Viewer & editor tidak boleh memicu upgrade sendiri: cek lewat jalur
        # pembayaran resmi (POST /payments/snap) -> harus 403.
        for tok, who in ((viewer_tok, "viewer"), (editor_tok, "editor")):
            r = requests.post(f"{BASE_URL}/payments/snap",
                              params={"tree_id": tid},
                              headers=auth(tok), json={"plan": "pro"}, timeout=30)
            assert r.status_code == 403, f"{who} seharusnya 403, dapat {r.status_code}: {r.text}"

        # Endpoint upgrade khusus superadmin juga menolak non-superadmin.
        r = requests.post(f"{BASE_URL}/trees/{tid}/upgrade",
                          headers=auth(editor_tok), json={"plan": "pro"}, timeout=15)
        assert r.status_code == 403, r.text
        assert "pembayaran" in r.json()["detail"].lower(), r.json()["detail"]

        # Pohon tetap free — tidak ada plan yang berubah karena percobaan ini.
        row = next(x for x in requests.get(f"{BASE_URL}/trees",
                                           headers=auth(admin["tok"]),
                                           timeout=15).json() if x["id"] == tid)
        assert row["plan"] == "free", row


# ===========================================================================
# 5. EDITOR LIMIT — free plan caps at 3 editors
# ===========================================================================
class TestEditorLimit:
    def test_invite_accept_hits_editor_limit_then_upgrade_unlocks(self, admin):
        # Fresh free tree owned by admin
        t = _api_create_tree(admin["tok"], "TEST_PLAN_EditorLimitTree")
        tid = t["id"]

        # Seed 3 editor members directly to reach the free-plan cap of 3
        for _ in range(3):
            uid, _, _ = _seed_user("EDITOR_SEED")
            mid = str(uuid.uuid4())
            db.tree_members.insert_one({
                "id": mid, "tree_id": tid, "user_id": uid,
                "role": "editor", "joined_at": now_utc(),
            })
            CREATED["member_ids"].add(mid)

        # Sanity: editor_count exposed by /trees
        r = requests.get(f"{BASE_URL}/trees", headers=auth(admin["tok"]), timeout=15)
        t_row = next(x for x in r.json() if x["id"] == tid)
        assert t_row["editor_count"] == 3

        # Create invite-link
        r = requests.post(f"{BASE_URL}/trees/{tid}/invite-link",
                          headers=auth(admin["tok"]), timeout=15)
        assert r.status_code == 200, r.text
        token = r.json()["token"]
        CREATED["invite_tokens"].add(token)

        # User ke-4 mencoba bergabung -> 402 karena kuota ANGGOTA penuh.
        # (Kuota editor = kuota anggota pada paket free, jadi backend memakai
        # kode MEMBER_LIMIT — pesan inilah yang ditampilkan ke pengguna.)
        new_uid, new_tok, _ = _seed_user("EDITOR_ACCEPT")
        r = requests.post(f"{BASE_URL}/invite-accept/{token}",
                          headers=auth(new_tok), timeout=15)
        assert r.status_code == 402, r.text
        assert r.json()["detail"].startswith("MEMBER_LIMIT:"), r.json()["detail"]

        # Upgrade ke pro (editors=10) lalu ulangi -> 200
        _upgrade_via_payment(tid, "pro")

        r = requests.post(f"{BASE_URL}/invite-accept/{token}",
                          headers=auth(new_tok), timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["tree_id"] == tid

        # Verify the accepting user is now an editor
        assert db.tree_members.count_documents(
            {"tree_id": tid, "user_id": new_uid, "role": "editor"}) == 1

        STATE["editor_limit_tree_id"] = tid
        STATE["editor_limit_new_uid"] = new_uid
        STATE["editor_limit_token"] = token

    def test_invite_accept_idempotent(self, admin):
        """Menerima undangan dua kali tidak boleh menggandakan keanggotaan."""
        # Pohon plan pro supaya tidak terbentur kuota anggota saat bergabung.
        t = _api_create_tree(admin["tok"], "TEST_PLAN_IdempotentTree")
        tid = t["id"]
        _upgrade_via_payment(tid, "pro")

        r = requests.post(f"{BASE_URL}/trees/{tid}/invite-link",
                          headers=auth(admin["tok"]), timeout=15)
        assert r.status_code == 200, r.text
        token = r.json()["token"]
        CREATED["invite_tokens"].add(token)

        uid, tok2, _ = _seed_user("IDEMPOTENT")
        r = requests.post(f"{BASE_URL}/invite-accept/{token}",
                          headers=auth(tok2), timeout=15)
        assert r.status_code == 200, r.text

        before = db.tree_members.count_documents({"tree_id": tid, "user_id": uid})
        r = requests.post(f"{BASE_URL}/invite-accept/{token}",
                          headers=auth(tok2), timeout=15)
        assert r.status_code == 200, r.text
        after = db.tree_members.count_documents({"tree_id": tid, "user_id": uid})
        assert before == after == 1, f"membership duplicated: before={before} after={after}"

    def test_change_member_role_402_when_at_editor_cap(self, admin):
        # Fresh free tree, seed 3 editors + 1 viewer member; try promoting viewer -> 402
        t = _api_create_tree(admin["tok"], "TEST_PLAN_PromoteCapTree")
        tid = t["id"]
        for _ in range(3):
            uid, _, _ = _seed_user("PROMOTE_ED")
            mid = str(uuid.uuid4())
            db.tree_members.insert_one({
                "id": mid, "tree_id": tid, "user_id": uid, "role": "editor",
                "joined_at": now_utc(),
            })
            CREATED["member_ids"].add(mid)
        viewer_uid, _, _ = _seed_user("PROMOTE_VW")
        mid = str(uuid.uuid4())
        db.tree_members.insert_one({
            "id": mid, "tree_id": tid, "user_id": viewer_uid, "role": "viewer",
            "joined_at": now_utc(),
        })
        CREATED["member_ids"].add(mid)

        r = requests.put(f"{BASE_URL}/trees/{tid}/members/role",
                         headers=auth(admin["tok"]),
                         json={"user_id": viewer_uid, "role": "editor"}, timeout=15)
        assert r.status_code == 402, r.text
        assert r.json()["detail"].startswith("EDITOR_LIMIT:")

        # Upgrade ke family (editors=50) -> promosi berhasil
        _upgrade_via_payment(tid, "family")
        r = requests.put(f"{BASE_URL}/trees/{tid}/members/role",
                         headers=auth(admin["tok"]),
                         json={"user_id": viewer_uid, "role": "editor"}, timeout=15)
        assert r.status_code == 200, r.text


# ===========================================================================
# 6. STORAGE QUOTA — kuota berbasis byte (menggantikan batas "20 foto")
# ===========================================================================
class TestStorageQuota:
    """Kuota penyimpanan berbasis BYTE (menggantikan batas "20 foto").

    Backend menghitung pemakaian dari `tree.storage_used`, yang diisi dari
    ukuran objek di storage. Test menyuntikkan objek berukuran sama (format
    GridFS) supaya tidak perlu benar-benar mengunggah file besar.
    """

    def test_storage_quota_402_then_upgrade_unlocks(self, admin):
        t = _api_create_tree(admin["tok"], "TEST_PLAN_StorageTree")
        tid = t["id"]
        limit = t["storage_limit"]
        assert limit and limit > 0, f"free tree harus punya storage_limit: {t}"
        assert t["storage_used"] == 0

        # Pemakaian disimpan backend di koleksi `tree_usage` (bukan di dokumen
        # tree). Isi sampai kuota tinggal 10 byte, jadi upload nyata berikutnya
        # pasti ditolak tanpa perlu benar-benar menyimpan file besar.
        used = limit - 10
        path = f"TESTPLAN/quota_{uuid.uuid4().hex}/filler.bin"
        db["fs.files"].insert_one({
            "_id": ObjectId(),
            "filename": path,
            "length": used,
            "chunkSize": 261120,
            "uploadDate": now_utc(),
            "metadata": {"tree_id": tid},
        })
        db.tree_usage.update_one({"tree_id": tid}, {"$set": {"bytes": used}}, upsert=True)
        CREATED["storage_paths"].add(path)

        # /trees melaporkan pemakaian & kuota apa adanya.
        r = requests.get(f"{BASE_URL}/trees", headers=auth(admin["tok"]), timeout=15)
        assert r.status_code == 200, r.text
        row = next(x for x in r.json() if x["id"] == tid)
        assert row["storage_used"] == used
        assert row["storage_limit"] == limit

        # Upload berikutnya ditolak 402 STORAGE_LIMIT.
        r = requests.get(f"{BASE_URL}/tree", params={"tree_id": tid},
                         headers=auth(admin["tok"]), timeout=15)
        root = r.json()["root_id"]
        files = {"file": ("test.jpg", io.BytesIO(b"x" * 100), "image/jpeg")}
        r = requests.post(f"{BASE_URL}/people/{root}/files",
                          params={"tree_id": tid},
                          headers=auth(admin["tok"]),
                          files=files, timeout=15)
        assert r.status_code == 402, r.text
        assert r.json()["detail"].startswith("STORAGE_LIMIT:"), r.json()["detail"]

        # Upgrade ke pro (kuota 10 GB): upload tidak lagi ditolak karena kuota.
        _upgrade_via_payment(tid, "pro")
        r = requests.get(f"{BASE_URL}/trees", headers=auth(admin["tok"]), timeout=15)
        row = next(x for x in r.json() if x["id"] == tid)
        assert row["plan"] == "pro"
        assert row["storage_limit"] > limit

        files = {"file": ("test2.jpg", io.BytesIO(b"y" * 100), "image/jpeg")}
        r = requests.post(f"{BASE_URL}/people/{root}/files",
                          params={"tree_id": tid},
                          headers=auth(admin["tok"]),
                          files=files, timeout=30)
        assert r.status_code != 402, f"masih kena kuota setelah upgrade: {r.text}"
        if r.status_code == 200:
            CREATED["note_ids"].add(r.json()["id"])


# ===========================================================================
# 7. Regression: cross-tenant isolation and existing tree scoping
# ===========================================================================
class TestRegression:
    def test_non_member_cannot_read_other_tree(self, tree_ab):
        # Akun baru tidak boleh membaca pohon milik orang lain.
        _, tok, _ = _seed_user("STRANGER")
        r = requests.get(f"{BASE_URL}/tree", params={"tree_id": tree_ab["B"]},
                         headers=auth(tok), timeout=15)
        assert r.status_code == 403, r.text

    def test_chat_is_tree_scoped(self, tree_ab):
        admin = tree_ab["owner"]
        tid_a = tree_ab["A"]
        tid_b = tree_ab["B"]
        r = requests.post(f"{BASE_URL}/chat",
                          params={"tree_id": tid_a},
                          headers=auth(admin["tok"]),
                          json={"message": "TEST_PLAN_isolated_chat"}, timeout=15)
        assert r.status_code == 200, r.text
        msg_id = r.json()["id"]
        # In A: present
        r_a = requests.get(f"{BASE_URL}/chat", params={"tree_id": tid_a},
                           headers=auth(admin["tok"]), timeout=15).json()
        assert any(m["id"] == msg_id for m in r_a["messages"])
        # In B: absent
        r_b = requests.get(f"{BASE_URL}/chat", params={"tree_id": tid_b},
                           headers=auth(admin["tok"]), timeout=15).json()
        assert not any(m["id"] == msg_id for m in r_b["messages"])
