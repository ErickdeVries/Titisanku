import os
import io
import uuid
import time
import logging
import secrets
import hashlib
from collections import deque
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

import httpx
import requests
from fastapi import FastAPI, APIRouter, HTTPException, Header, Depends, Request, UploadFile, File, Query, Body
from fastapi.responses import Response, JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError
from dotenv import load_dotenv
from pydantic import BaseModel, Field, EmailStr
from html import escape

# Integrasi pihak ketiga pengganti Emergent (Firebase Auth/Storage, Resend, Expo Push)
import integrations

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("keturunanku")

app = FastAPI()
api_router = APIRouter(prefix="/api")


@app.get("/health")
async def health():
    """Health check dengan verifikasi koneksi database.

    Sebelumnya endpoint ini selalu mengembalikan "ok" meskipun MongoDB tidak
    dapat diakses (mis. kredensial salah), sehingga masalah DB tidak terdeteksi
    oleh monitoring maupun oleh verifikasi manual.
    """
    db_ok = True
    db_error = None
    try:
        await client.admin.command("ping")
    except Exception as e:
        db_ok = False
        db_error = type(e).__name__
        logger.warning("Health check: ping MongoDB gagal: %s", e)

    payload = {
        "status": "ok" if db_ok else "degraded",
        "database": "ok" if db_ok else "unavailable",
    }
    if db_error:
        payload["database_error"] = db_error
    return JSONResponse(status_code=200 if db_ok else 503, content=payload)


# ---------------------------------------------------------------------------
# Object Storage — Firebase Storage (lihat backend/integrations.py)
# ---------------------------------------------------------------------------
APP_NAME = "keturunanku"

# Midtrans payment config
MIDTRANS_SERVER_KEY = os.environ.get("MIDTRANS_SERVER_KEY", "")
MIDTRANS_CLIENT_KEY = os.environ.get("MIDTRANS_CLIENT_KEY", "")
MIDTRANS_IS_PRODUCTION = os.environ.get("MIDTRANS_ENV", "production").lower() == "production"
MIDTRANS_SNAP_URL = ("https://app.midtrans.com" if MIDTRANS_IS_PRODUCTION else "https://app.sandbox.midtrans.com") + "/snap/v1/transactions"
MIDTRANS_STATUS_BASE = "https://api.midtrans.com" if MIDTRANS_IS_PRODUCTION else "https://api.sandbox.midtrans.com"
PLAN_PRICES = {"pro": 149000, "family": 199000}
SUPERADMIN_EMAILS = [e.strip().lower() for e in os.environ.get("SUPERADMIN_EMAILS", "").split(",") if e.strip()]

# CORS — daftar origin yang diizinkan (dipisah koma) via env CORS_ORIGINS.
# Bila kosong -> fallback "*" TANPA credentials (kombinasi "*" + credentials tidak valid
# menurut spesifikasi CORS dan menyebabkan browser memblokir request).
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
CORS_ALLOW_ALL = "*" in CORS_ORIGINS or not CORS_ORIGINS
# Default: izinkan dev web + domain produksi bila env tidak diisi.
if CORS_ALLOW_ALL and not os.environ.get("CORS_ORIGINS"):
    CORS_ORIGINS = [
        "http://localhost:8081",
        "http://127.0.0.1:8081",
        "http://localhost:19006",
        "https://titisanku.helipod.app",
    ]
    CORS_ALLOW_ALL = False


def cors_headers_for(request: Request) -> dict:
    """Header CORS untuk respons yang dibuat manual (mis. dari exception handler).

    Respons yang diproduksi ``ServerErrorMiddleware`` berada di luar jangkauan
    ``CORSMiddleware`` sehingga tidak otomatis mendapat header CORS. Tanpa header
    ini, browser akan melaporkan "Failed to fetch" (CORS) alih-alih pesan error
    yang sebenarnya, membuat masalah backend sulit didiagnosis.
    """
    origin = request.headers.get("origin")
    if not origin:
        return {}
    if CORS_ALLOW_ALL:
        return {"Access-Control-Allow-Origin": "*"}
    if origin in CORS_ORIGINS:
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
        }
    return {}


def is_superadmin(user) -> bool:
    return (user.get("email") or "").lower() in SUPERADMIN_EMAILS


RECENT_TIMINGS: deque = deque(maxlen=800)

def put_object(path: str, data: bytes, content_type: str) -> dict:
    """Unggah objek ke Firebase Storage."""
    return integrations.storage_upload(path, data, content_type)

def get_object(path: str):
    """Unduh objek dari Firebase Storage."""
    return integrations.storage_download(path)


def object_size(path: str):
    """Ukuran objek (byte) dari metadata storage, atau None bila tak ditemukan."""
    return integrations.storage_size(path)

# ---------------------------------------------------------------------------
# Email - Resend (lihat backend/integrations.py)
# ---------------------------------------------------------------------------
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "KETURUNANKU")


async def send_email(*, to: str, subject: str, html: str) -> Optional[str]:
    try:
        return await run_in_threadpool(
            integrations.email_send, to=to, subject=subject, html=html, from_name=EMAIL_FROM_NAME
        )
    except integrations.IntegrationError as e:
        logger.error("Email gagal: %s", e)
        raise HTTPException(status_code=502, detail=f"Gagal mengirim email: {e}")

# ---------------------------------------------------------------------------
def now_utc():
    return datetime.now(timezone.utc)


def _aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


class PersonData(BaseModel):
    name: str
    gender: Optional[str] = None  # 'male' | 'female'
    birth_date: Optional[str] = None
    birth_place: Optional[str] = None
    death_date: Optional[str] = None
    photo_url: Optional[str] = None
    cover_url: Optional[str] = None
    job: Optional[str] = None
    is_adopted: bool = False
    notes: Optional[str] = None
    is_alive: Optional[bool] = None  # override; else auto from death_date
    privacy: Optional[Dict[str, bool]] = None  # field -> hidden from other members


class AddRelativeInput(BaseModel):
    focus_id: str
    direction: str  # father | mother | spouse | child
    person: PersonData
    marriage_date: Optional[str] = None
    divorce_date: Optional[str] = None
    is_divorced: bool = False
    other_parent_id: Optional[str] = None  # child direction: explicit second parent (spouse of focus)


class InviteInput(BaseModel):
    email: EmailStr


class AcceptInviteInput(BaseModel):
    code: str


class SessionInput(BaseModel):
    session_id: str


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
async def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ", 1)[1]
    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")
    expires_at = session["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now_utc():
        raise HTTPException(status_code=401, detail="Session expired")
    user = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def require_role(user, roles):
    if user.get("role") not in roles:
        raise HTTPException(status_code=403, detail="Permission denied")


# ---------------------------------------------------------------------------
# Multi-tenant Tree helpers
# ---------------------------------------------------------------------------
FREE_PERSON_LIMIT = 50

# Kuota penyimpanan per pohon dalam BYTE. Dibatasi berdasarkan total ukuran file,
# bukan jumlah foto, karena biaya server mengikuti ukuran (satu foto ponsel bisa
# 4-8 MB, sedangkan foto terkompresi hanya ~300 KB).
MB = 1024 * 1024
GB = 1024 * MB


def _storage_limit_mb(env_key: str, default_mb: int) -> int:
    """Kuota storage dalam byte, bisa ditimpa lewat env (memudahkan tes).

    Nilai default tetap seperti semula (free 500 MB, pro 10 GB, ...). Override
    hanya dipakai bila env diisi angka > 0.
    """
    raw = (os.environ.get(env_key) or "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw) * MB
    return default_mb * MB


STORAGE_LIMITS = {
    "free": _storage_limit_mb("STORAGE_LIMIT_FREE_MB", 500),
    "pro": _storage_limit_mb("STORAGE_LIMIT_PRO_MB", 10 * 1024),
    "family": _storage_limit_mb("STORAGE_LIMIT_FAMILY_MB", 25 * 1024),
    "unlimited": None,  # None = tak terbatas
}

# Subscription plan limits. None = unlimited.
# Kuota penyimpanan file TIDAK di sini — lihat STORAGE_LIMITS (berbasis byte).
PLAN_LIMITS = {
    "free": {"people": 50, "editors": 3},
    "pro": {"people": None, "editors": 10},
    "family": {"people": None, "editors": 50},
    "unlimited": {"people": None, "editors": None},
}


def plan_limits(plan: str) -> dict:
    return PLAN_LIMITS.get(plan or "free", PLAN_LIMITS["free"])


def effective_plan(tree: dict) -> str:
    """Plan yang benar-benar berlaku. Plan berbayar otomatis turun ke `free`
    setelah lewat `expires_at`, supaya langganan tidak bisa dipakai selamanya
    hanya karena frontend yang menampilkan batas waktunya.

    PENTING: motor mengembalikan datetime NAIVE (UTC) dari MongoDB. Membandingkan
    nilai naive dengan `now_utc()` (aware) melempar TypeError dan membuat
    GET /trees crash 500 begitu ada pohon berbayar — yaitu tepat pada pelanggan
    yang sudah membayar. Karena itu `expires_at` selalu dinormalkan lewat
    `_aware()` sebelum dibandingkan.
    """
    plan = (tree or {}).get("plan") or "free"
    if plan == "free":
        return "free"
    exp = _aware((tree or {}).get("expires_at"))
    if exp and exp < now_utc():
        return "free"
    return plan


async def editor_count(tree_id: str) -> int:
    return await db.tree_members.count_documents({"tree_id": tree_id, "role": "editor"})


async def member_count(tree_id: str) -> int:
    """Jumlah akun yang bergabung ke pohon (semua role, termasuk admin)."""
    return await db.tree_members.count_documents({"tree_id": tree_id})


async def owned_tree_count(user_id: str) -> int:
    """Jumlah pohon AKTIF milik user. delete_tree melakukan hard delete, jadi
    setiap baris di db.trees adalah pohon yang masih ada."""
    return await db.trees.count_documents({"owner_id": user_id})


def member_limit(plan: str) -> Optional[int]:
    """Kuota anggota yang boleh bergabung ke satu pohon = kuota editor plan.

    Anggota login tidak pernah melebihi editor karena hanya admin & editor yang
    dihitung sebagai kolaborator aktif; viewer tetap terikat batas yang sama
    agar jumlah akun di dalam satu pohon tidak tak terbatas."""
    return plan_limits(plan).get("editors")

async def ensure_can_join(tree: dict) -> None:
    """Tolak penambahan anggota bila kuota anggota plan pohon sudah penuh."""
    lim = member_limit(effective_plan(tree))
    if lim is not None and await member_count(tree["id"]) >= lim:
        raise HTTPException(
            status_code=402,
            detail=f"MEMBER_LIMIT:Batas {lim} anggota untuk paket ini sudah tercapai. "
                   f"Upgrade plan untuk menambah anggota.",
        )


# --- Penyimpanan: kuota ukuran & kompresi foto -------------------------------

def storage_limit(plan: str) -> Optional[int]:
    """Kuota penyimpanan (byte) untuk plan tsb. None = tak terbatas."""
    return STORAGE_LIMITS.get(plan or "free", STORAGE_LIMITS["free"])


def fmt_size(num_bytes: int) -> str:
    if num_bytes >= GB:
        return f"{num_bytes / GB:.1f} GB"
    return f"{num_bytes / MB:.0f} MB"


async def storage_used(tree_id: str) -> int:
    """Total byte yang dipakai pohon. Disimpan di koleksi `tree_usage` agar tidak
    perlu menjumlah ulang seluruh lampiran pada setiap upload."""
    row = await db.tree_usage.find_one({"tree_id": tree_id}, {"_id": 0, "bytes": 1})
    return int((row or {}).get("bytes", 0) or 0)


async def add_storage_usage(tree_id: str, delta: int) -> None:
    if delta == 0:
        return
    row = await db.tree_usage.update_one(
        {"tree_id": tree_id}, {"$inc": {"bytes": delta}, "$set": {"updated_at": now_utc()}}, upsert=True
    )
    # Jangan biarkan penghitung turun di bawah nol karena data lama/penghapusan ganda.
    if delta < 0:
        await db.tree_usage.update_one({"tree_id": tree_id, "bytes": {"$lt": 0}}, {"$set": {"bytes": 0}})


async def ensure_storage_room(tree: dict, incoming: int) -> None:
    """Tolak upload bila kuota penyimpanan pohon akan terlampaui."""
    lim = storage_limit(effective_plan(tree))
    if lim is None:
        return
    used = await storage_used(tree["id"])
    if used + incoming > lim:
        sisa = max(0, lim - used)
        raise HTTPException(
            status_code=402,
            detail=f"STORAGE_LIMIT:Kuota penyimpanan paket ini {fmt_size(lim)} sudah hampir penuh "
                   f"(tersisa {fmt_size(sisa)}). Upgrade plan untuk menambah ruang.",
        )


def _normalize_photo_path(raw) -> Optional[str]:
    """Samakan bentuk rujukan foto agar path yang sama tidak dihitung dua kali."""
    if not raw or not isinstance(raw, str):
        return None
    p = raw.strip()
    if not p:
        return None
    if p.startswith("/api/files/"):
        p = p[len("/api/files/"):]
    p = p.split("?")[0]
    if p.startswith(("http://", "https://")):
        marker = "/o/"
        if marker in p:
            from urllib.parse import unquote
            p = unquote(p.split(marker, 1)[1])
        else:
            return None
    # Skema lain (gs://, ftp://, data:, dsb.) bukan path storage yang bisa ditaksir.
    if "://" in p or p.startswith("data:"):
        return None
    return p.lstrip("/") or None


async def _sum_storage_bytes(paths) -> int:
    """Total ukuran file dari metadata storage. Path tak ditemukan dihitung 0."""
    total = 0
    for path in paths:
        try:
            size = await run_in_threadpool(object_size, path)
        except FileNotFoundError:
            continue
        except Exception as exc:  # konfigurasi/jaringan: jangan gagalkan claim
            logger.warning("claim-branch: gagal membaca ukuran %s: %s", path, exc)
            continue
        if size:
            total += size
    return total


MAX_IMAGE_DIMENSION = 1920
JPEG_QUALITY = 85
# Lewat batas ini kompresi dijalankan di thread pool agar event loop tetap responsif.
COMPRESS_IN_THREAD_THRESHOLD = 512 * 1024

_COMPRESSIBLE_EXTS = {"jpg", "jpeg", "png", "webp", "heic", "heif", "bmp", "tif", "tiff"}


def _compress_image_sync(data: bytes) -> tuple:
    """Kecilkan foto ke maks 1920px sisi terpanjang & re-encode JPEG kualitas 85.

    Mengembalikan (bytes_baru, ext, content_type). Bila hasil kompresi tidak lebih
    kecil, atau file bukan gambar yang bisa dibaca, data asli dikembalikan utuh.
    """
    try:
        from PIL import Image, ImageOps
    except ImportError:  # pragma: no cover - Pillow wajib ada di requirements
        return data, None, None

    with io.BytesIO(data) as raw:
        try:
            img = Image.open(raw)
            img.load()
        except Exception:
            return data, None, None

        # Terapkan rotasi EXIF agar foto potret dari ponsel tidak tampil miring
        # setelah diratakan ke JPEG (orientasi EXIF hilang saat re-encode).
        img = ImageOps.exif_transpose(img)

        if img.mode in ("RGBA", "LA", "P"):
            # Latar putih untuk transparansi agar tidak jadi hitam saat JPEG.
            img = img.convert("RGBA")
            canvas = Image.new("RGB", img.size, (255, 255, 255))
            canvas.paste(img, mask=img.split()[-1])
            img = canvas
        elif img.mode != "RGB":
            img = img.convert("RGB")

        w, h = img.size
        if max(w, h) > MAX_IMAGE_DIMENSION:
            img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
        out = buf.getvalue()

    if len(out) >= len(data):
        return data, None, None
    return out, "jpg", "image/jpeg"


async def compress_image(data: bytes, ext: str) -> tuple:
    """Kompres foto bila memungkinkan. Return (bytes, ext, content_type)."""
    if ext not in _COMPRESSIBLE_EXTS or not data:
        return data, ext, None
    if len(data) < COMPRESS_IN_THREAD_THRESHOLD:
        new_data, new_ext, ctype = _compress_image_sync(data)
    else:
        new_data, new_ext, ctype = await run_in_threadpool(_compress_image_sync, data)
    if new_ext is None:
        return data, ext, None
    return new_data, new_ext, ctype


async def photo_count(tree_id: str) -> int:
    return await db.person_notes.count_documents({"tree_id": tree_id, "attachments": {"$ne": []}, "deleted_at": None})
async def gallery_count(tree_id: str) -> int:
    pipeline = [
        {"$match": {"tree_id": tree_id, "deleted_at": None}},
        {"$project": {"n": {"$size": {"$ifNull": ["$gallery", []]}}}},
        {"$group": {"_id": None, "total": {"$sum": "$n"}}},
    ]
    rows = await db.people.aggregate(pipeline).to_list(1)
    return rows[0]["total"] if rows else 0


class TreeCreateInput(BaseModel):
    name: str


class UpgradeInput(BaseModel):
    plan: str = "pro"


class MemberRoleInput(BaseModel):
    user_id: str
    role: str  # editor | viewer


class ClaimBranchInput(BaseModel):
    person_id: str
    scope: str = "descendants"  # descendants | children | whole
    name: Optional[str] = None


async def resolve_tree(user, tree_id: Optional[str]):
    """Return (tree, role) for the given user. If tree_id is None, use the
    user's primary (first joined) tree. Raises 403 if not a member."""
    q = {"user_id": user["user_id"]}
    if tree_id:
        q["tree_id"] = tree_id
    member = await db.tree_members.find_one(q, {"_id": 0}, sort=[("joined_at", 1)])
    if not member:
        if tree_id:
            # Superadmin has full permanent access to every tree.
            if is_superadmin(user):
                tree = await db.trees.find_one({"id": tree_id}, {"_id": 0})
                if not tree:
                    raise HTTPException(status_code=404, detail="Pohon tidak ditemukan")
                tree["plan"] = "unlimited"
                return tree, "admin"
            raise HTTPException(status_code=403, detail="Anda bukan anggota pohon ini")
        return None, None
    tree = await db.trees.find_one({"id": member["tree_id"]}, {"_id": 0})
    if not tree:
        raise HTTPException(status_code=404, detail="Pohon tidak ditemukan")
    if is_superadmin(user):
        tree["plan"] = "unlimited"
    else:
        tree = await _check_plan_expiry(tree)
    role = "admin" if is_superadmin(user) else member["role"]
    return tree, role


def require_role_t(role, roles):
    # `resolve_tree` returns (None, None) when the caller is signed in but does
    # not belong to any tree yet (e.g. a brand-new user). Endpoints below use
    # tree["id"] right after this check, so reject early with a 403 instead of
    # letting a `None` tree blow up into a 500 further down.
    if role is None:
        raise HTTPException(status_code=403, detail="Anda belum tergabung dalam pohon keluarga mana pun")
    if role not in roles:
        raise HTTPException(status_code=403, detail="Permission denied")


# ---------------------------------------------------------------------------
# Card privacy: hide personal fields from *other* members of the same tree.
# The owner of a record (created_by), tree admins, and superadmins always see
# everything. Everyone else only gets fields the owner left unhidden.
# ---------------------------------------------------------------------------
SENSITIVE_PERSON_FIELDS = (
    "birth_date",
    "birth_place",
    "job",
    "death_date",
    "notes",
)


def _privacy_entry(value) -> dict:
    """Normalise one privacy entry to {"hidden": bool, "allow": [user_id, ...]}.

    Two shapes are accepted so old records keep working:
      - bool            -> {"hidden": value, "allow": []}   (legacy, hide from all)
      - {"hidden": .., "allow": [..]}                      (current)
    """
    if isinstance(value, dict):
        return {
            "hidden": bool(value.get("hidden")),
            "allow": [str(u) for u in (value.get("allow") or []) if u],
        }
    return {"hidden": bool(value), "allow": []}


def _entry_visible_to(entry: dict, uid: Optional[str]) -> bool:
    """A field is visible when it is not hidden, or when an allow-list exists
    and the caller is on it. `hidden` alone means "nobody else"."""
    if not entry.get("hidden"):
        return True
    if uid and uid in entry.get("allow", []):
        return True
    return False


def redact_person(p: dict, user, role: Optional[str], tree: Optional[dict] = None) -> dict:
    """Strip personal fields the caller may not see. Mutates and returns the
    record. `privacy` is always rewritten to the normalised shape so the client
    only has to understand one format."""
    if not p:
        return p
    raw = p.get("privacy") or {}
    if not raw:
        return p
    # Always hand the client the normalised map, even to people who may see
    # everything, so the UI never has to parse legacy bare booleans.
    p["privacy"] = {f: _privacy_entry(v) for f, v in raw.items()
                    if f in SENSITIVE_PERSON_FIELDS}
    # Always allowed: the person's creator, superadmin, tree admin.
    uid = (user or {}).get("user_id")
    if p.get("created_by") and p.get("created_by") == uid:
        return p
    if is_superadmin(user or {}) or role == "admin":
        return p

    redacted = []
    for field, entry in p["privacy"].items():
        if not _entry_visible_to(entry, uid):
            p[field] = None
            redacted.append(field)

    # Signal to the client that something was withheld.
    if redacted:
        p["redacted_fields"] = redacted
    return p


def redact_people(people: List[dict], user, role: Optional[str]) -> List[dict]:
    return [redact_person(p, user, role) for p in people]


async def tree_person_count(tree_id: str) -> int:
    return await db.people.count_documents({"tree_id": tree_id, "deleted_at": None})


async def create_tree_for_user(user, name: str, make_root: bool = True) -> dict:
    """Create a new tree owned by the user, add them as admin member,
    and optionally create a root person."""
    tree_id = f"tree_{uuid.uuid4().hex[:12]}"
    root_person_id = None
    if make_root:
        root_person_id = str(uuid.uuid4())
        await db.people.insert_one({
            "id": root_person_id,
            "tree_id": tree_id,
            "name": user["name"],
            "email": user["email"],
            "gender": None,
            "birth_date": None,
            "birth_place": None,
            "death_date": None,
            "photo_url": user.get("picture"),
            "job": None,
            "is_adopted": False,
            "notes": None,
            "is_alive": True,
            "is_root": True,
            "created_by": user["user_id"],
            "created_at": now_utc(),
            "deleted_at": None,
        })
    tree_doc = {
        "id": tree_id,
        "name": name,
        "owner_id": user["user_id"],
        "plan": "free",
        "is_public": False,
        "root_person_id": root_person_id,
        "created_at": now_utc(),
    }
    await db.trees.insert_one(tree_doc)
    await db.tree_members.insert_one({
        "id": str(uuid.uuid4()),
        "tree_id": tree_id,
        "user_id": user["user_id"],
        "role": "admin",
        "joined_at": now_utc(),
    })
    tree_doc.pop("_id", None)
    return tree_doc


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@api_router.post("/auth/session")
async def auth_session(body: SessionInput):
    """Tukar ID token Firebase dengan session token milik aplikasi."""
    try:
        # `session_id` kini membawa Firebase ID Token (JWT) dari client SDK.
        claims = integrations.verify_firebase_id_token(body.session_id)
    except integrations.IntegrationError as e:
        logger.warning("auth/session ditolak: %s", e)
        raise HTTPException(status_code=401, detail="Invalid session")
    email = claims.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="Token tidak memiliki email")
    name = claims.get("name") or email.split("@")[0]
    picture = claims.get("picture")
    session_token = secrets.token_urlsafe(32)

    try:
        existing = await db.users.find_one({"email": email}, {"_id": 0})
        if existing:
            user_id = existing["user_id"]
        else:
            user_count = await db.users.count_documents({})
            is_first = user_count == 0
            user_id = f"user_{uuid.uuid4().hex[:12]}"
            role = "admin" if is_first else "viewer"
            pending = await db.invites.find_one({"email": email, "accepted": False})
            if pending and not is_first:
                role = "editor"
                await db.invites.update_one({"_id": pending["_id"]}, {"$set": {"accepted": True, "accepted_at": now_utc()}})
            user_doc = {
                "user_id": user_id,
                "email": email,
                "name": name,
                "picture": picture,
                "role": role,
                "created_at": now_utc(),
            }
            await db.users.insert_one(user_doc)
            # New users choose in onboarding whether to create or join a tree (no auto tree).

        await db.user_sessions.insert_one({
            "session_token": session_token,
            "user_id": user_id,
            "created_at": now_utc(),
            "expires_at": now_utc() + timedelta(days=7),
        })
        user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    except PyMongoError as e:
        # Kredensial/klaster DB bermasalah (mis. "bad auth") atau DB tak terjangkau.
        # Balas 503 dengan pesan jelas, bukan 500 tanpa header CORS.
        logger.error("auth/session gagal mengakses database: %s", e)
        raise HTTPException(
            status_code=503,
            detail="Database tidak tersedia. Periksa konfigurasi MongoDB.",
        )
    return {"session_token": session_token, "user": user}


@api_router.get("/auth/me")
async def auth_me(user=Depends(get_current_user)):
    return {**user, "is_superadmin": is_superadmin(user)}


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    picture: Optional[str] = None


@api_router.put("/users/me")
async def update_me(body: ProfileUpdate, user=Depends(get_current_user)):
    upd = {}
    if body.name is not None and body.name.strip():
        upd["name"] = body.name.strip()
    if body.picture is not None:
        upd["picture"] = body.picture
    if upd:
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": upd})
    u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return {**u, "is_superadmin": is_superadmin(u)}


@api_router.post("/auth/logout")
async def auth_logout(authorization: Optional[str] = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
        await db.user_sessions.delete_one({"session_token": token})
    return {"ok": True}


# ---------------------------------------------------------------------------
# People / Relations
# ---------------------------------------------------------------------------
def clean_person(p: dict) -> dict:
    p.pop("_id", None)
    return p


@api_router.get("/tree")
async def get_tree(tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    if not tree:
        return {"people": [], "relations": [], "root_id": None, "tree": None, "role": None}
    tid = tree["id"]
    people = await db.people.find({"tree_id": tid, "deleted_at": None}, {"_id": 0}).to_list(5000)
    relations = await db.relations.find({"tree_id": tid, "deleted_at": None}, {"_id": 0}).to_list(10000)
    root_id = tree.get("root_person_id") or (people[0]["id"] if people else None)
    counts = {}
    async for row in db.person_notes.aggregate(
        [{"$match": {"tree_id": tid, "deleted_at": None}}, {"$group": {"_id": "$person_id", "c": {"$sum": 1}}}]
    ):
        counts[row["_id"]] = row["c"]
    for p in people:
        p["note_count"] = counts.get(p["id"], 0)
        if p.get("is_alive") is None:
            p["is_alive"] = not bool(p.get("death_date"))
    people = redact_people(people, user, role)
    return {
        "people": people,
        "relations": relations,
        "root_id": root_id,
        "tree": tree,
        "role": role,
        "person_count": len(people),
        "limit": plan_limits(effective_plan(tree)).get("people"),
        "storage_used": await storage_used(tree["id"]),
        "storage_limit": storage_limit(effective_plan(tree)),
    }


@api_router.get("/people")
async def list_people(q: Optional[str] = None, tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    if not tree:
        return []
    query = {"tree_id": tree["id"], "deleted_at": None}
    if q:
        query["name"] = {"$regex": q, "$options": "i"}
    people = await db.people.find(query, {"_id": 0}).to_list(5000)
    return redact_people(people, user, role)


@api_router.get("/people/{person_id}")
async def get_person(person_id: str, tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    if not tree:
        raise HTTPException(status_code=404, detail="Person not found")
    p = await db.people.find_one({"id": person_id, "tree_id": tree["id"], "deleted_at": None}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Person not found")
    return redact_person(p, user, role)


class GalleryInput(BaseModel):
    path: Optional[str] = None
    caption: Optional[str] = None
    date: Optional[str] = None
    id: Optional[str] = None


class GalleryEdit(BaseModel):
    caption: Optional[str] = None
    date: Optional[str] = None


@api_router.post("/people/{person_id}/gallery")
async def add_gallery_photo(person_id: str, body: GalleryInput, tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    require_role_t(role, ["admin", "editor"])
    person = await db.people.find_one({"id": person_id, "tree_id": tree["id"], "deleted_at": None}, {"_id": 0})
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    # Kuota penyimpanan sudah ditegakkan di endpoint /upload (foto ini diunggah
    # lebih dulu dan ukurannya sudah dicatat). Jangan dicek ulang di sini agar
    # tidak menghitung ganda dan tidak memblokir penambahan galeri tanpa upload.
    if not body.path:
        raise HTTPException(status_code=400, detail="path wajib diisi")
    item = {"id": str(uuid.uuid4()), "path": body.path, "caption": body.caption or "", "date": body.date or "", "created_at": now_utc()}
    await db.people.update_one({"id": person_id, "tree_id": tree["id"]}, {"$push": {"gallery": item}})
    p = await db.people.find_one({"id": person_id}, {"_id": 0})
    return {"gallery": _serialize(p.get("gallery", []))}


@api_router.patch("/people/{person_id}/gallery/{photo_id}")
async def edit_gallery_photo(person_id: str, photo_id: str, body: GalleryEdit, tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    require_role_t(role, ["admin", "editor"])
    await db.people.update_one(
        {"id": person_id, "tree_id": tree["id"], "gallery.id": photo_id},
        {"$set": {"gallery.$.caption": body.caption or "", "gallery.$.date": body.date or ""}},
    )
    p = await db.people.find_one({"id": person_id}, {"_id": 0})
    return {"gallery": _serialize((p or {}).get("gallery", []))}


@api_router.delete("/people/{person_id}/gallery")
async def remove_gallery_photo(person_id: str, body: GalleryInput, tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    require_role_t(role, ["admin", "editor"])
    if body.id:
        await db.people.update_one({"id": person_id, "tree_id": tree["id"]}, {"$pull": {"gallery": {"id": body.id}}})
    elif body.path:
        await db.people.update_one({"id": person_id, "tree_id": tree["id"]}, {"$pull": {"gallery": {"path": body.path}}})
    p = await db.people.find_one({"id": person_id}, {"_id": 0})
    return {"gallery": _serialize((p or {}).get("gallery", []))}


@api_router.put("/people/{person_id}")
async def update_person(person_id: str, data: PersonData, tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    require_role_t(role, ["admin", "editor"])
    p = await db.people.find_one({"id": person_id, "tree_id": tree["id"], "deleted_at": None})
    if not p:
        raise HTTPException(status_code=404, detail="Person not found")
    d = data.model_dump()
    # Privacy is managed only via PUT /people/{id}/privacy. Drop it here so a
    # normal edit (the app's form does not send `privacy`) cannot wipe the map
    # and silently un-hide fields for every other member of the tree.
    d.pop("privacy", None)
    is_alive = d.pop("is_alive", None)
    if is_alive is None:
        is_alive = not bool(d.get("death_date"))
    d["is_alive"] = is_alive
    await db.people.update_one({"id": person_id}, {"$set": d})
    return redact_person(await db.people.find_one({"id": person_id}, {"_id": 0}), user, role)


@api_router.put("/people/{person_id}/privacy")
async def set_person_privacy(person_id: str, body: Dict[str, object], tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    """Set which personal fields are hidden, and optionally open them to
    specific members.

    Body accepts either legacy booleans or the richer per-field object:
      {"job": true}                                   -> hide from everyone else
      {"job": {"hidden": true, "allow": [user_id]}}   -> hidden except those users
      {"job": {"hidden": false}}                      -> visible to all members

    Keys not present in the body are left untouched, so the client can update
    one field without clobbering the rest. Allowed for the record's creator,
    tree admins and superadmins.
    """
    tree, role = await resolve_tree(user, tree_id)
    if not tree:
        raise HTTPException(status_code=404, detail="Person not found")
    p = await db.people.find_one({"id": person_id, "tree_id": tree["id"], "deleted_at": None}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Person not found")
    is_owner = p.get("created_by") == user["user_id"]
    if not (is_owner or is_superadmin(user) or role == "admin"):
        raise HTTPException(status_code=403, detail="Hanya pemilik data atau admin pohon yang dapat mengubah privasi")

    # Only members of this tree may be granted access - otherwise a record could
    # be exposed to a user from another family.
    member_ids = {
        m["user_id"]
        async for m in db.tree_members.find({"tree_id": tree["id"]}, {"user_id": 1})
    }

    existing = {f: _privacy_entry(v) for f, v in (p.get("privacy") or {}).items()
                if f in SENSITIVE_PERSON_FIELDS}
    updates = {}
    for field, value in (body or {}).items():
        if field not in SENSITIVE_PERSON_FIELDS:
            continue
        entry = _privacy_entry(value)
        entry["allow"] = [u for u in entry["allow"] if u in member_ids]
        updates[field] = entry

    merged = {**existing, **updates}
    # Drop fields that are effectively public so the stored map stays small.
    merged = {f: e for f, e in merged.items() if e["hidden"] or e["allow"]}
    await db.people.update_one({"id": person_id, "tree_id": tree["id"]}, {"$set": {"privacy": merged}})
    return {"ok": True, "privacy": merged}


@api_router.delete("/people/{person_id}")
async def delete_person(person_id: str, tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    require_role_t(role, ["admin"])
    if tree.get("root_person_id") == person_id:
        raise HTTPException(status_code=400, detail="Cannot delete root person")
    res = await db.people.update_one({"id": person_id, "tree_id": tree["id"], "deleted_at": None}, {"$set": {"deleted_at": now_utc()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Person not found")
    await db.relations.update_many(
        {"tree_id": tree["id"], "$or": [{"person_id": person_id}, {"related_person_id": person_id}]},
        {"$set": {"deleted_at": now_utc()}},
    )
    return {"ok": True}


@api_router.delete("/relations/{rel_id}")
async def delete_relation(rel_id: str, tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    require_role_t(role, ["admin", "editor"])
    r = await db.relations.find_one({"id": rel_id, "tree_id": tree["id"], "deleted_at": None}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="Relation not found")
    await db.relations.update_one({"id": rel_id}, {"$set": {"deleted_at": now_utc()}})
    return {"ok": True}


class RelationUpdate(BaseModel):
    marriage_date: Optional[str] = None
    divorce_date: Optional[str] = None
    is_divorced: bool = False


@api_router.put("/relations/{rel_id}")
async def update_relation(rel_id: str, data: RelationUpdate, tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    require_role_t(role, ["admin", "editor"])
    r = await db.relations.find_one({"id": rel_id, "tree_id": tree["id"], "deleted_at": None}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="Relation not found")
    if r["relation_type"] not in ("spouse", "divorced"):
        raise HTTPException(status_code=400, detail="Only spouse relations can be updated")
    update = {
        "marriage_date": data.marriage_date,
        "divorce_date": data.divorce_date if data.is_divorced else None,
        "relation_type": "divorced" if data.is_divorced else "spouse",
    }
    await db.relations.update_one({"id": rel_id}, {"$set": update})
    return await db.relations.find_one({"id": rel_id}, {"_id": 0})


@api_router.post("/tree/link-coparents")
async def link_coparents(tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    """Link every child to their OTHER parent (the linked parent's spouse) when unambiguous:
    the child currently has exactly one parent AND that parent has exactly one spouse. Reuses the
    existing spouse as the second parent — never creates a new person. Fixes the 'child only shows
    under the father' problem so it is consistent from every individual's point of view."""
    tree, role = await resolve_tree(user, tree_id)
    require_role_t(role, ["admin", "editor"])
    tid = tree["id"]
    rels = await db.relations.find({"tree_id": tid, "deleted_at": None}, {"_id": 0}).to_list(100000)
    PARENT = ("parent", "adopted_child")
    SPOUSE = ("spouse", "divorced")
    parents_of: dict = {}
    spouses_of: dict = {}
    for r in rels:
        if r["relation_type"] in PARENT:
            parents_of.setdefault(r["related_person_id"], []).append((r["person_id"], r["relation_type"]))
        elif r["relation_type"] in SPOUSE:
            spouses_of.setdefault(r["person_id"], set()).add(r["related_person_id"])
            spouses_of.setdefault(r["related_person_id"], set()).add(r["person_id"])
    new_rels = []
    for child, plist in parents_of.items():
        if len(plist) != 1:
            continue  # already has both parents (or none)
        parent_id, ptype = plist[0]
        sp = spouses_of.get(parent_id, set())
        if len(sp) != 1:
            continue  # ambiguous (no spouse or multiple spouses)
        other = next(iter(sp))
        if other == parent_id or other == child:
            continue
        new_rels.append({
            "id": str(uuid.uuid4()), "tree_id": tid, "person_id": other,
            "related_person_id": child, "relation_type": ptype,
            "created_at": now_utc(), "deleted_at": None,
        })
    if new_rels:
        await db.relations.insert_many(new_rels)
    return {"linked": len(new_rels)}





@api_router.post("/people/first")
async def add_first_person(body: PersonData, tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    require_role_t(role, ["admin", "editor"])
    if await tree_person_count(tree["id"]) > 0:
        raise HTTPException(status_code=400, detail="Pohon ini sudah memiliki anggota.")
    pid = str(uuid.uuid4())
    doc = {
        "id": pid,
        "tree_id": tree["id"],
        "name": body.name,
        "gender": body.gender,
        "birth_date": body.birth_date,
        "birth_place": body.birth_place,
        "death_date": body.death_date,
        "photo_url": body.photo_url,
        "cover_url": body.cover_url,
        "job": body.job,
        "is_adopted": body.is_adopted,
        "notes": body.notes,
        "is_alive": body.is_alive if body.is_alive is not None else (body.death_date is None),
        "is_root": True,
        "created_by": user["user_id"],
        "created_at": now_utc(),
        "deleted_at": None,
    }
    await db.people.insert_one(doc)
    await db.trees.update_one({"id": tree["id"]}, {"$set": {"root_person_id": pid}})
    return _serialize([doc])[0]


@api_router.post("/people/add-relative")
async def add_relative(body: AddRelativeInput, tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    require_role_t(role, ["admin", "editor"])
    # Subscription limit for people
    lim_people = plan_limits(effective_plan(tree)).get("people")
    if lim_people is not None:
        count = await tree_person_count(tree["id"])
        if count >= lim_people:
            raise HTTPException(
                status_code=402,
                detail=f"LIMIT_REACHED:Pohon '{tree.get('name')}' sudah mencapai {lim_people} orang. Upgrade untuk membuka kunci generasi selanjutnya.",
            )
    focus = await db.people.find_one({"id": body.focus_id, "tree_id": tree["id"], "deleted_at": None}, {"_id": 0})
    if not focus:
        raise HTTPException(status_code=404, detail="Focus person not found")

    # Prevent duplicate father/mother for the same person
    if body.direction in ("father", "mother"):
        want = "male" if body.direction == "father" else "female"
        parent_rels = await db.relations.find(
            {"tree_id": tree["id"], "related_person_id": body.focus_id,
             "relation_type": {"$in": ["parent", "adopted_child"]}, "deleted_at": None},
            {"_id": 0, "person_id": 1},
        ).to_list(50)
        for pr in parent_rels:
            par = await db.people.find_one({"id": pr["person_id"], "deleted_at": None}, {"_id": 0, "gender": 1})
            if par and par.get("gender") == want:
                raise HTTPException(status_code=400, detail=f"{'Ayah' if want == 'male' else 'Ibu'} sudah ada untuk orang ini.")

    pd = body.person.model_dump()
    pd.pop("is_alive", None)
    if body.direction == "father":
        pd["gender"] = "male"
    elif body.direction == "mother":
        pd["gender"] = "female"

    new_id = str(uuid.uuid4())
    person_doc = {
        "id": new_id,
        "tree_id": tree["id"],
        **pd,
        "is_alive": not bool(pd.get("death_date")),
        "is_root": False,
        "created_by": user["user_id"],
        "created_at": now_utc(),
        "deleted_at": None,
    }
    await db.people.insert_one(person_doc)

    rel_id = str(uuid.uuid4())
    extra_rels = []
    if body.direction in ("father", "mother"):
        rel = {
            "id": rel_id,
            "person_id": new_id,
            "related_person_id": body.focus_id,
            "relation_type": "parent",
        }
    elif body.direction == "child":
        rel = {
            "id": rel_id,
            "person_id": body.focus_id,
            "related_person_id": new_id,
            "relation_type": "adopted_child" if pd.get("is_adopted") else "parent",
        }
        # Auto-link the child to the focus person's spouse (the other parent) so the
        # user doesn't have to re-create the mother/father and end up with duplicates.
        spouse_rels = await db.relations.find(
            {"tree_id": tree["id"], "relation_type": {"$in": ["spouse", "divorced"]},
             "$or": [{"person_id": body.focus_id}, {"related_person_id": body.focus_id}],
             "deleted_at": None},
            {"_id": 0, "person_id": 1, "related_person_id": 1},
        ).to_list(50)
        spouse_ids = {
            (r["related_person_id"] if r["person_id"] == body.focus_id else r["person_id"])
            for r in spouse_rels
        }
        # Determine the "other parent": an explicit choice (when the focus has multiple spouses),
        # otherwise auto-link only when there is exactly one spouse (unambiguous).
        other_parent = None
        if body.other_parent_id and body.other_parent_id in spouse_ids:
            other_parent = body.other_parent_id
        elif len(spouse_ids) == 1:
            other_parent = next(iter(spouse_ids))
        if other_parent:
            extra_rels.append({
                "id": str(uuid.uuid4()),
                "person_id": other_parent,
                "related_person_id": new_id,
                "relation_type": "adopted_child" if pd.get("is_adopted") else "parent",
                "tree_id": tree["id"],
                "deleted_at": None,
                "created_at": now_utc(),
            })
    elif body.direction == "spouse":
        rel = {
            "id": rel_id,
            "person_id": body.focus_id,
            "related_person_id": new_id,
            "relation_type": "divorced" if body.is_divorced else "spouse",
            "marriage_date": body.marriage_date,
            "divorce_date": body.divorce_date,
        }
    elif body.direction == "sibling":
        # A sibling shares the same parents as the focus person.
        parent_rels = await db.relations.find(
            {"tree_id": tree["id"], "related_person_id": body.focus_id,
             "relation_type": {"$in": ["parent", "adopted_child"]}, "deleted_at": None},
            {"_id": 0, "person_id": 1},
        ).to_list(50)
        parent_ids = [r["person_id"] for r in parent_rels]
        if parent_ids:
            # link the new sibling as a child of every parent of the focus person
            rel = {
                "id": rel_id,
                "person_id": parent_ids[0],
                "related_person_id": new_id,
                "relation_type": "parent",
            }
            for pid in parent_ids[1:]:
                extra_rels.append({
                    "id": str(uuid.uuid4()),
                    "person_id": pid,
                    "related_person_id": new_id,
                    "relation_type": "parent",
                    "tree_id": tree["id"],
                    "deleted_at": None,
                    "created_at": now_utc(),
                })
        else:
            # focus has no parents yet -> connect the two as explicit siblings
            rel = {
                "id": rel_id,
                "person_id": body.focus_id,
                "related_person_id": new_id,
                "relation_type": "sibling",
            }
    else:
        raise HTTPException(status_code=400, detail="Invalid direction")
    rel["tree_id"] = tree["id"]
    rel["deleted_at"] = None
    rel["created_at"] = now_utc()
    await db.relations.insert_one(rel)
    if extra_rels:
        await db.relations.insert_many(extra_rels)

    return {"person": clean_person(person_doc), "relation_id": rel_id}


# ---------------------------------------------------------------------------
# Upload / Files
# ---------------------------------------------------------------------------
@api_router.post("/upload")
async def upload_file(file: UploadFile = File(...), tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    require_role_t(role, ["admin", "editor"])
    content = await file.read()
    ext = (file.filename or "photo.jpg").split(".")[-1].lower()
    # Kompres foto sebelum cek kuota, supaya yang ditolak/diterima adalah ukuran
    # yang benar-benar disimpan (bukan ukuran asli ponsel).
    content, ext, ctype = await compress_image(content, ext)
    await ensure_storage_room(tree, len(content))
    path = f"{APP_NAME}/uploads/{user['user_id']}/{uuid.uuid4().hex}.{ext}"
    try:
        result = await run_in_threadpool(put_object, path, content, ctype or file.content_type or "image/jpeg")
    except integrations.IntegrationError as e:
        logger.error("Upload gagal: %s", e)
        raise HTTPException(status_code=503, detail=f"Penyimpanan file belum siap: {e}")
    await add_storage_usage(tree["id"], len(content))
    stored = result["path"]
    # `url` memakai URL publik Firebase Storage bila tersedia, fallback ke proxy /api/files.
    return {"path": stored, "url": result.get("url") or f"/api/files/{stored}"}


async def _validate_token(token: str):
    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")
    return True


@api_router.get("/files/{path:path}")
async def get_file(path: str, token: Optional[str] = Query(None), authorization: Optional[str] = Header(None)):
    tok = token
    if not tok and authorization and authorization.startswith("Bearer "):
        tok = authorization.split(" ", 1)[1]
    if not tok:
        raise HTTPException(status_code=401, detail="Not authenticated")
    await _validate_token(tok)
    try:
        content, content_type = await run_in_threadpool(get_object, path)
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")
    return Response(content=content, media_type=content_type)


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------
def _serialize(docs):
    out = []
    for d in docs:
        d.pop("_id", None)
        for k, v in list(d.items()):
            if isinstance(v, datetime):
                d[k] = v.isoformat()
        out.append(d)
    return out


@api_router.get("/backup")
async def backup(tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    require_role_t(role, ["admin"])
    tid = tree["id"]
    people = await db.people.find({"tree_id": tid}, {"_id": 0}).to_list(5000)
    relations = await db.relations.find({"tree_id": tid}, {"_id": 0}).to_list(10000)
    return {
        "exported_at": now_utc().isoformat(),
        "tree": {"id": tid, "name": tree.get("name")},
        "people": _serialize(people),
        "relations": _serialize(relations),
    }


# ---------------------------------------------------------------------------
# Collaboration invites
# ---------------------------------------------------------------------------
@api_router.get("/invites")
async def list_invites(user=Depends(get_current_user)):
    require_role(user, ["admin"])
    invites = await db.invites.find({}, {"_id": 0}).to_list(500)
    return _serialize(invites)


@api_router.post("/invite")
async def create_invite(body: InviteInput, user=Depends(get_current_user)):
    require_role(user, ["admin"])
    code = secrets.token_hex(4).upper()
    invite = {
        "id": str(uuid.uuid4()),
        "email": body.email,
        "code": code,
        "invited_by": user["user_id"],
        "accepted": False,
        "created_at": now_utc(),
    }
    await db.invites.insert_one(invite)

    subject = f"Undangan bergabung ke pohon keluarga {EMAIL_FROM_NAME}"
    html = (
        f'<table role="presentation" width="100%"><tr><td style="padding:24px;'
        f'font-family:Arial,sans-serif;color:#0F172A">'
        f'<h2 style="margin:0 0 12px">Anda diundang ke {escape(EMAIL_FROM_NAME)}</h2>'
        f'<p>Hai, {escape(user["name"])} mengundang Anda untuk berkolaborasi mencatat silsilah keluarga.</p>'
        f'<p>Buka aplikasi {escape(EMAIL_FROM_NAME)}, masuk dengan Google, lalu buka '
        f'<strong>Setting &rarr; Gabung dengan Kode</strong> dan masukkan kode di bawah ini:</p>'
        f'<p style="font-size:28px;font-weight:bold;letter-spacing:4px;color:#F59E0B">{escape(code)}</p>'
        f'<p style="font-size:12px;color:#888">Dikirim oleh {escape(EMAIL_FROM_NAME)}. '
        f'Kami tidak pernah meminta kata sandi Anda melalui email.</p>'
        f'</td></tr></table>'
    )
    # Email yang gagal TIDAK boleh dilaporkan sebagai sukses: kode tetap dibuat,
    # tetapi respons menandai bahwa email belum terkirim lengkap dengan alasannya.
    email_id = None
    email_error = None
    try:
        email_id = await send_email(to=body.email, subject=subject, html=html)
    except HTTPException as e:
        email_error = e.detail
        logger.warning("Undangan %s dibuat, tetapi email gagal: %s", code, e.detail)
    if email_error:
        return {
            "code": code,
            "email_id": None,
            "email": body.email,
            "email_sent": False,
            "error": email_error,
            "hint": "Bagikan kode undangan di atas secara manual.",
        }
    return {"code": code, "email_id": email_id, "email": body.email, "email_sent": True}


@api_router.post("/invite/accept")
async def accept_invite(body: AcceptInviteInput, user=Depends(get_current_user)):
    invite = await db.invites.find_one({"code": body.code.upper().strip()})
    if not invite:
        raise HTTPException(status_code=404, detail="Kode undangan tidak valid")
    await db.invites.update_one({"_id": invite["_id"]}, {"$set": {"accepted": True, "accepted_at": now_utc()}})
    if user["role"] == "viewer":
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"role": "editor"}})
    updated = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return updated


# ---------------------------------------------------------------------------
# Person notes & files, Family chat, In-app notifications
# ---------------------------------------------------------------------------
class NoteInput(BaseModel):
    note_text: str


class ChatInput(BaseModel):
    message: Optional[str] = ""
    attachments: List[str] = []
    reply_to: Optional[str] = None
    mentions: List[str] = []  # user_ids mentioned


class GroupCreateInput(BaseModel):
    name: str
    member_ids: List[str] = []
    picture: Optional[str] = None


class DirectInput(BaseModel):
    user_id: str


async def is_user_deceased(tree_id: str, user) -> bool:
    """A member whose linked person (matched by email) is deceased cannot chat."""
    if not user.get("email"):
        return False
    p = await db.people.find_one({"tree_id": tree_id, "email": user["email"], "deleted_at": None}, {"_id": 0})
    if not p:
        return False
    alive = p.get("is_alive")
    if alive is None:
        alive = not bool(p.get("death_date"))
    return not alive


async def resolve_room(tree, user, room_id: Optional[str]):
    """Return a room dict {id,type,name,member_ids,tree_id,can_send} or raise."""
    if not tree:
        raise HTTPException(status_code=403, detail="Anda belum tergabung dalam pohon keluarga mana pun")
    tid = tree["id"]
    rows = await db.tree_members.find({"tree_id": tid}, {"_id": 0, "user_id": 1, "role": 1}).to_list(2000)
    all_ids = [r["user_id"] for r in rows]
    my_role = next((r["role"] for r in rows if r["user_id"] == user["user_id"]), None)
    if my_role is None:
        raise HTTPException(status_code=403, detail="Anda bukan anggota pohon ini")
    if not room_id or room_id == tid:
        return {"id": tid, "type": "family", "name": tree.get("name", "Keluarga"),
                "member_ids": all_ids, "tree_id": tid, "can_send": my_role in ("admin", "editor")}
    r = await db.chat_rooms.find_one({"id": room_id, "tree_id": tid}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="Ruang chat tidak ditemukan")
    if user["user_id"] not in r.get("member_ids", []):
        raise HTTPException(status_code=403, detail="Anda bukan peserta chat ini")
    return {**r, "tree_id": tid, "can_send": True}


async def notify_room(room, actor_id: str, ntype: str, title: str, body: str):
    muted = {m["user_id"] for m in await db.chat_mutes.find({"room_id": room["id"]}, {"_id": 0, "user_id": 1}).to_list(2000)}
    docs = []
    for uid in room.get("member_ids", []):
        if uid == actor_id or uid in muted:
            continue
        docs.append({
            "id": str(uuid.uuid4()), "user_id": uid, "tree_id": room["tree_id"],
            "type": ntype, "title": title, "body": body, "read": False, "created_at": now_utc(),
        })
    if docs:
        await db.app_notifications.insert_many(docs)
    try:
        await send_push(
            [d["user_id"] for d in docs],
            {
                "title": title,
                "message": body,
                "channel_id": "chat",
                "sound": "ding.wav",
                "action_url": f"/chat/{room['id']}",
            },
        )
    except Exception as e:
        logger.warning(f"Push failed (non-blocking): {e}")


async def notify_tree(tree_id: str, actor_id: str, ntype: str, title: str, body: str):
    members = await db.tree_members.find(
        {"tree_id": tree_id, "role": {"$in": ["admin", "editor"]}}, {"_id": 0, "user_id": 1}
    ).to_list(2000)
    docs = []
    for r in members:
        if r["user_id"] == actor_id:
            continue
        docs.append({
            "id": str(uuid.uuid4()),
            "user_id": r["user_id"],
            "tree_id": tree_id,
            "type": ntype,
            "title": title,
            "body": body,
            "read": False,
            "created_at": now_utc(),
        })
    if docs:
        await db.app_notifications.insert_many(docs)


async def _check_plan_expiry(tree):
    """Lazily enforce yearly plan expiry on tree access (no cron needed).
    Auto-downgrades to free when expired and fires H-7 / H-1 reminders once."""
    if not tree or tree.get("plan") in (None, "free"):
        return tree
    exp = tree.get("expires_at")
    if not exp:
        return tree
    exp = _aware(exp)
    now = now_utc()
    tid = tree["id"]
    name = tree.get("name", "")
    if exp <= now:
        await db.trees.update_one(
            {"id": tid},
            {"$set": {"plan": "free"}, "$unset": {"expires_at": "", "expiry_reminder_7": "", "expiry_reminder_1": ""}},
        )
        try:
            await notify_tree(tid, "", "plan", "Paket berakhir",
                              f"Paket berbayar untuk \"{name}\" telah berakhir. Pohon kini memakai paket Free — data Anda tetap aman. Perpanjang untuk membuka kembali fitur premium.")
        except Exception as e:
            logger.warning(f"expiry notify failed: {e}")
        tree["plan"] = "free"
        tree.pop("expires_at", None)
        return tree
    days = (exp - now).days
    if days <= 1 and not tree.get("expiry_reminder_1"):
        await db.trees.update_one({"id": tid}, {"$set": {"expiry_reminder_1": True}})
        try:
            await notify_tree(tid, "", "plan", "Paket segera berakhir",
                              f"Paket \"{name}\" berakhir dalam 1 hari. Perpanjang agar fitur premium tetap aktif.")
        except Exception:
            pass
    elif days <= 7 and not tree.get("expiry_reminder_7"):
        await db.trees.update_one({"id": tid}, {"$set": {"expiry_reminder_7": True}})
        try:
            await notify_tree(tid, "", "plan", "Paket akan berakhir",
                              f"Paket \"{name}\" berakhir dalam {days} hari. Jangan lupa perpanjang langganan Anda.")
        except Exception:
            pass
    return tree
# ---------------------------------------------------------------------------
class RegisterPushBody(BaseModel):
    platform: str
    device_token: str

@api_router.post("/register-push", status_code=201)
async def register_push(body: RegisterPushBody, user=Depends(get_current_user)):
    """Simpan token perangkat untuk notifikasi via Expo Push."""
    await db.push_tokens.update_one(
        {"user_id": user["user_id"], "device_token": body.device_token},
        {"$set": {
            "user_id": user["user_id"],
            "platform": body.platform,
            "device_token": body.device_token,
            "updated_at": now_utc(),
        }},
        upsert=True,
    )
    return {"status": "registered"}

async def send_push(recipients: list, data: dict, idempotency_key: Optional[str] = None):
    """Kirim notifikasi via Expo Push API. Kegagalan tidak memblokir pemanggil."""
    recipients = list(dict.fromkeys([r for r in recipients if r]))[:100]
    if not recipients or "title" not in data or "message" not in data:
        return
    # recipients berisi user_id internal; terjemahkan ke Expo push token.
    tokens = await db.push_tokens.find(
        {"user_id": {"$in": recipients}}, {"_id": 0, "device_token": 1}
    ).to_list(500)
    if not tokens:
        return
    messages = [
        {
            "to": t["device_token"],
            "title": data["title"],
            "body": data["message"],
            "sound": "default",
            "data": {**{k: v for k, v in data.items() if k not in ("title", "message")},
                     **({"idempotency_key": idempotency_key} if idempotency_key else {})},
        }
        for t in tokens
        if str(t.get("device_token", "")).startswith(("ExponentPushToken[", "ExpoPushToken["))
    ]
    if messages:
        await integrations.push_send(messages)


@api_router.get("/people/{person_id}/notes")
async def list_person_notes(person_id: str, tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    if not tree:
        return []
    notes = await db.person_notes.find({"person_id": person_id, "tree_id": tree["id"], "deleted_at": None}, {"_id": 0}).sort("created_at", -1).to_list(2000)
    return _serialize(notes)


@api_router.post("/people/{person_id}/notes")
async def add_person_note(person_id: str, body: NoteInput, tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    require_role_t(role, ["admin", "editor"])
    person = await db.people.find_one({"id": person_id, "tree_id": tree["id"], "deleted_at": None}, {"_id": 0})
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    doc = {
        "id": str(uuid.uuid4()),
        "person_id": person_id,
        "tree_id": tree["id"],
        "author_id": user["user_id"],
        "author_name": user["name"],
        "note_text": body.note_text,
        "attachments": [],
        "created_at": now_utc(),
        "deleted_at": None,
    }
    await db.person_notes.insert_one(doc)
    await notify_tree(tree["id"], user["user_id"], "note", f"Catatan baru: {person['name']}", f"{user['name']}: {body.note_text[:60]}")
    return _serialize([doc])[0]


@api_router.post("/people/{person_id}/files")
async def add_person_file(person_id: str, file: UploadFile = File(...), tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    require_role_t(role, ["admin", "editor"])
    person = await db.people.find_one({"id": person_id, "tree_id": tree["id"], "deleted_at": None}, {"_id": 0})
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    content = await file.read()
    ext = (file.filename or "file").split(".")[-1].lower()
    content, ext, ctype = await compress_image(content, ext)
    await ensure_storage_room(tree, len(content))
    path = f"{APP_NAME}/uploads/{user['user_id']}/{uuid.uuid4().hex}.{ext}"
    result = await run_in_threadpool(put_object, path, content, ctype or file.content_type or "application/octet-stream")
    await add_storage_usage(tree["id"], len(content))
    doc = {
        "id": str(uuid.uuid4()),
        "person_id": person_id,
        "tree_id": tree["id"],
        "author_id": user["user_id"],
        "author_name": user["name"],
        "note_text": file.filename or "File",
        "attachments": [result["path"]],
        "created_at": now_utc(),
        "deleted_at": None,
    }
    await db.person_notes.insert_one(doc)
    await notify_tree(tree["id"], user["user_id"], "file", f"File baru: {person['name']}", f"{user['name']} menambahkan file")
    return _serialize([doc])[0]


@api_router.delete("/notes/{note_id}")
async def delete_note(note_id: str, user=Depends(get_current_user)):
    note = await db.person_notes.find_one({"id": note_id, "deleted_at": None}, {"_id": 0})
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    tree, role = await resolve_tree(user, note.get("tree_id"))
    if role != "admin" and note["author_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Hanya penulis atau admin yang bisa menghapus")
    await db.person_notes.update_one({"id": note_id}, {"$set": {"deleted_at": now_utc()}})
    return {"ok": True}


class GroupUpdateInput(BaseModel):
    name: Optional[str] = None
    member_ids: Optional[List[str]] = None
    picture: Optional[str] = None


class MuteInput(BaseModel):
    muted: bool = True


@api_router.put("/chat/rooms/{room_id}")
async def update_group(room_id: str, body: GroupUpdateInput, tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    if not tree:
        raise HTTPException(status_code=403, detail="Anda belum tergabung dalam pohon keluarga mana pun")
    room = await db.chat_rooms.find_one({"id": room_id, "tree_id": tree["id"]}, {"_id": 0})
    if not room or room.get("type") != "group":
        raise HTTPException(status_code=404, detail="Grup tidak ditemukan")
    is_manager = room.get("created_by") == user["user_id"] or role in ("admin", "editor")
    if user["user_id"] not in room.get("member_ids", []) or not is_manager:
        raise HTTPException(status_code=403, detail="Hanya pengelola grup yang dapat mengubah grup")
    updates = {}
    if body.name is not None and body.name.strip():
        updates["name"] = body.name.strip()
    if body.member_ids is not None:
        valid = {r["user_id"] for r in await db.tree_members.find({"tree_id": tree["id"]}, {"_id": 0, "user_id": 1}).to_list(2000)}
        members = {m for m in body.member_ids if m in valid}
        members.add(room["created_by"])
        members.add(user["user_id"])
        updates["member_ids"] = list(members)
    if body.picture is not None:
        updates["picture"] = body.picture or None
    if updates:
        await db.chat_rooms.update_one({"id": room_id}, {"$set": updates})
    updated = await db.chat_rooms.find_one({"id": room_id}, {"_id": 0})
    return _serialize([updated])[0]


@api_router.post("/chat/rooms/{room_id}/mute")
async def mute_room(room_id: str, body: MuteInput, tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    await resolve_room(tree, user, room_id)  # validates membership
    rid = room_id if room_id else tree["id"]
    if body.muted:
        await db.chat_mutes.update_one(
            {"user_id": user["user_id"], "room_id": rid},
            {"$set": {"user_id": user["user_id"], "room_id": rid, "created_at": now_utc()}},
            upsert=True,
        )
    else:
        await db.chat_mutes.delete_one({"user_id": user["user_id"], "room_id": rid})
    return {"ok": True, "muted": body.muted}


@api_router.get("/chat/rooms")
async def list_chat_rooms(tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    if not tree:
        return {"rooms": []}
    tid = tree["id"]
    uid = user["user_id"]
    users = {u["user_id"]: u for u in await db.users.find({}, {"_id": 0}).to_list(3000)}
    muted_ids = {m["room_id"] for m in await db.chat_mutes.find({"user_id": uid}, {"_id": 0, "room_id": 1}).to_list(2000)}

    async def enrich(room):
        last = await db.family_chat.find_one(
            {"room_id": room["id"], "deleted_at": None}, {"_id": 0}, sort=[("created_at", -1)],
        )
        unread = await db.family_chat.count_documents(
            {"room_id": room["id"], "deleted_at": None, "sender_id": {"$ne": uid}, "read_by": {"$ne": uid}},
        )
        preview = ""
        last_at = room.get("created_at")
        if last:
            sname = users.get(last["sender_id"], {}).get("name", "?")
            body = last.get("message") or ("📷 Foto" if last.get("attachments") else "")
            preview = f"{sname}: {body}" if room["type"] != "direct" else body
            last_at = last.get("created_at")
        return {
            "id": room["id"], "type": room["type"], "name": room["name"],
            "picture": room.get("picture"), "member_count": len(room.get("member_ids", [])),
            "last_message": preview, "last_message_at": last_at, "unread": unread,
            "muted": room["id"] in muted_ids,
        }

    rooms = []
    # Family room (virtual, id = tree_id)
    fam_rows = await db.tree_members.find({"tree_id": tid}, {"_id": 0, "user_id": 1}).to_list(2000)
    rooms.append(await enrich({
        "id": tid, "type": "family", "name": tree.get("name", "Keluarga"),
        "member_ids": [r["user_id"] for r in fam_rows], "created_at": tree.get("created_at"),
    }))
    # Custom groups + direct rooms the user belongs to
    customs = await db.chat_rooms.find({"tree_id": tid, "member_ids": uid}, {"_id": 0}).to_list(1000)
    for r in customs:
        display = dict(r)
        if r["type"] == "direct":
            other = next((m for m in r.get("member_ids", []) if m != uid), None)
            ou = users.get(other, {})
            display["name"] = ou.get("name", "?")
            display["picture"] = ou.get("picture")
        rooms.append(await enrich(display))
    rooms.sort(key=lambda x: (x["last_message_at"] is None, x["last_message_at"] or ""), reverse=True)
    # keep family pinned on top
    rooms.sort(key=lambda x: 0 if x["type"] == "family" else 1)
    return {"rooms": _serialize(rooms)}


@api_router.get("/chat/contacts")
async def chat_contacts(tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    if not tree:
        return {"contacts": []}
    rows = await db.tree_members.find({"tree_id": tree["id"]}, {"_id": 0, "user_id": 1, "role": 1}).to_list(2000)
    users = {u["user_id"]: u for u in await db.users.find({"user_id": {"$in": [r["user_id"] for r in rows]}}, {"_id": 0}).to_list(2000)}
    out = []
    for r in rows:
        if r["user_id"] == user["user_id"]:
            continue
        u = users.get(r["user_id"], {})
        out.append({"user_id": r["user_id"], "name": u.get("name", "?"), "picture": u.get("picture"), "role": r["role"]})
    return {"contacts": out}


@api_router.post("/chat/group")
async def create_group(body: GroupCreateInput, tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    # Any member of the tree can create a group chat and freely choose who to add.
    if not tree:
        raise HTTPException(status_code=403, detail="Anda bukan anggota pohon ini")
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nama grup wajib diisi")
    valid = {r["user_id"] for r in await db.tree_members.find({"tree_id": tree["id"]}, {"_id": 0, "user_id": 1}).to_list(2000)}
    members = {user["user_id"]} | {m for m in body.member_ids if m in valid}
    doc = {
        "id": str(uuid.uuid4()), "tree_id": tree["id"], "type": "group", "name": name,
        "picture": body.picture or None,
        "member_ids": list(members), "created_by": user["user_id"], "created_at": now_utc(),
    }
    await db.chat_rooms.insert_one(doc)
    return _serialize([{k: v for k, v in doc.items()}])[0]


@api_router.post("/chat/direct")
async def open_direct(body: DirectInput, tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    if not tree:
        raise HTTPException(status_code=403, detail="Anda belum tergabung dalam pohon keluarga mana pun")
    other = body.user_id
    if other == user["user_id"]:
        raise HTTPException(status_code=400, detail="Tidak bisa chat dengan diri sendiri")
    if not await db.tree_members.find_one({"tree_id": tree["id"], "user_id": other}):
        raise HTTPException(status_code=404, detail="Anggota tidak ditemukan")
    pair = sorted([user["user_id"], other])
    dm_key = f"{tree['id']}:{pair[0]}:{pair[1]}"
    existing = await db.chat_rooms.find_one({"dm_key": dm_key}, {"_id": 0})
    if existing:
        return _serialize([existing])[0]
    doc = {
        "id": str(uuid.uuid4()), "tree_id": tree["id"], "type": "direct", "name": "",
        "member_ids": pair, "dm_key": dm_key, "created_by": user["user_id"], "created_at": now_utc(),
    }
    await db.chat_rooms.insert_one(doc)
    return _serialize([doc])[0]


@api_router.get("/chat")
async def get_chat(tree_id: Optional[str] = Query(None), room_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    if not tree:
        return {"room_id": None, "room_name": "Keluarga", "room_type": "family", "messages": [], "members": [], "typing": [], "can_send": False}
    room = await resolve_room(tree, user, room_id)
    rid = room["id"]
    # participant display names (for mentions)
    users = {u["user_id"]: u for u in await db.users.find({}, {"_id": 0}).to_list(3000)}
    roles = {r["user_id"]: r["role"] for r in await db.tree_members.find({"tree_id": tree["id"]}, {"_id": 0, "user_id": 1, "role": 1}).to_list(2000)}
    creator = room.get("created_by")
    members = [
        {
            "user_id": mid,
            "name": users.get(mid, {}).get("name", "?"),
            "picture": users.get(mid, {}).get("picture"),
            "role": roles.get(mid, "viewer"),
            "is_creator": mid == creator,
        }
        for mid in room.get("member_ids", [])
    ]
    room_name = room["name"]
    room_picture = room.get("picture")
    if room["type"] == "direct":
        other = next((m for m in room.get("member_ids", []) if m != user["user_id"]), None)
        room_name = users.get(other, {}).get("name", "?")
        room_picture = users.get(other, {}).get("picture")
    # read receipts: mark others' messages read by me
    await db.family_chat.update_many(
        {"room_id": rid, "sender_id": {"$ne": user["user_id"]}, "read_by": {"$ne": user["user_id"]}, "deleted_at": None},
        {"$addToSet": {"read_by": user["user_id"]}},
    )
    msgs = await db.family_chat.find({"room_id": rid, "deleted_at": None}, {"_id": 0}).sort("created_at", 1).to_list(3000)
    out = []
    for m in _serialize(msgs):
        s = users.get(m["sender_id"], {})
        m["sender_name"] = s.get("name", "?")
        m["sender_picture"] = s.get("picture")
        m["read_by"] = m.get("read_by", [])
        out.append(m)
    cutoff = now_utc() - timedelta(seconds=6)
    typing_names = []
    async for d in db.chat_typing.find({"room_id": rid, "user_id": {"$ne": user["user_id"]}}, {"_id": 0}):
        upd = d.get("updated_at")
        if upd is not None and upd.tzinfo is None:
            upd = upd.replace(tzinfo=timezone.utc)
        if upd and upd > cutoff:
            typing_names.append(d.get("name", "?"))
    is_muted = await db.chat_mutes.find_one({"user_id": user["user_id"], "room_id": rid}) is not None
    can_manage = room["type"] == "group" and (room.get("created_by") == user["user_id"] or role in ("admin", "editor"))
    return {
        "room_id": rid, "room_name": room_name, "room_type": room["type"], "room_picture": room_picture,
        "created_by": creator,
        "messages": out, "members": members, "typing": typing_names,
        "can_send": room.get("can_send", False), "muted": is_muted, "can_manage": can_manage,
    }


@api_router.post("/chat/typing")
async def chat_typing(tree_id: Optional[str] = Query(None), room_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    room = await resolve_room(tree, user, room_id)
    await db.chat_typing.update_one(
        {"user_id": user["user_id"], "room_id": room["id"]},
        {"$set": {"user_id": user["user_id"], "name": user["name"], "room_id": room["id"], "updated_at": now_utc()}},
        upsert=True,
    )
    return {"ok": True}


@api_router.delete("/chat/{msg_id}")
async def delete_chat(msg_id: str, user=Depends(get_current_user)):
    m = await db.family_chat.find_one({"id": msg_id, "deleted_at": None}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Message not found")
    tree, role = await resolve_tree(user, m.get("tree_id") or m.get("room_id"))
    if role != "admin" and m["sender_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Hanya pengirim atau admin yang bisa menghapus pesan")
    await db.family_chat.update_one({"id": msg_id}, {"$set": {"deleted_at": now_utc()}})
    return {"ok": True}


@api_router.post("/chat")
async def send_chat(body: ChatInput, tree_id: Optional[str] = Query(None), room_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    room = await resolve_room(tree, user, room_id)
    if not room.get("can_send"):
        raise HTTPException(status_code=403, detail="Anda tidak dapat mengirim pesan di ruang ini")
    if await is_user_deceased(tree["id"], user):
        raise HTTPException(status_code=403, detail="Anggota yang telah meninggal tidak dapat mengirim pesan")
    rid = room["id"]
    reply = None
    if body.reply_to:
        rmsg = await db.family_chat.find_one({"id": body.reply_to}, {"_id": 0})
        if rmsg:
            sender = await db.users.find_one({"user_id": rmsg["sender_id"]}, {"_id": 0})
            reply = {
                "id": rmsg["id"],
                "message": rmsg.get("message"),
                "sender_name": sender["name"] if sender else "?",
                "has_attachment": bool(rmsg.get("attachments")),
            }
    if not (body.message or "").strip() and not body.attachments:
        raise HTTPException(status_code=400, detail="Empty message")
    doc = {
        "id": str(uuid.uuid4()),
        "room_id": rid,
        "tree_id": tree["id"],
        "sender_id": user["user_id"],
        "message": body.message or "",
        "attachments": body.attachments,
        "reply_to": reply,
        "read_by": [],
        "edited": False,
        "created_at": now_utc(),
        "deleted_at": None,
    }
    await db.family_chat.insert_one(doc)
    rname = room["name"] if room["type"] != "direct" else user["name"]
    ntitle = "Pesan baru di Chat Keluarga" if room["type"] == "family" else f"Pesan baru: {rname}"
    await notify_room(room, user["user_id"], "chat", ntitle, f"{user['name']}: {(body.message or 'Foto')[:60]}")
    # mention notifications
    mention_docs = []
    for uid in set(body.mentions):
        if uid == user["user_id"]:
            continue
        mention_docs.append({
            "id": str(uuid.uuid4()),
            "user_id": uid,
            "tree_id": tree["id"],
            "type": "mention",
            "title": "Anda disebut di Chat",
            "body": f"{user['name']} menyebut Anda: {(body.message or '')[:60]}",
            "read": False,
            "created_at": now_utc(),
        })
    if mention_docs:
        await db.app_notifications.insert_many(mention_docs)
    return _serialize([doc])[0]


@api_router.get("/notifications")
async def get_notifications(user=Depends(get_current_user)):
    items = await db.app_notifications.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).limit(50).to_list(50)
    unread = await db.app_notifications.count_documents({"user_id": user["user_id"], "read": False})
    unread_chat = await db.app_notifications.count_documents({"user_id": user["user_id"], "read": False, "type": "chat"})
    return {"unread": unread, "unread_chat": unread_chat, "items": _serialize(items)}


@api_router.post("/notifications/read")
async def mark_notifications_read(type: Optional[str] = None, user=Depends(get_current_user)):
    q = {"user_id": user["user_id"], "read": False}
    if type:
        q["type"] = type
    await db.app_notifications.update_many(q, {"$set": {"read": True}})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Restore from backup
# ---------------------------------------------------------------------------
class RestoreInput(BaseModel):
    people: List[dict] = []
    relations: List[dict] = []


@api_router.post("/restore")
async def restore(body: RestoreInput, tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    require_role_t(role, ["admin"])
    if not body.people:
        raise HTTPException(status_code=400, detail="Backup kosong atau tidak valid")
    tid = tree["id"]
    people_ids = [p.get("id") for p in body.people if p.get("id")]
    rel_ids = [r.get("id") for r in body.relations if r.get("id")]
    # soft-delete current records (in THIS tree) that are not part of the backup
    await db.people.update_many({"tree_id": tid, "id": {"$nin": people_ids}, "deleted_at": None}, {"$set": {"deleted_at": now_utc()}})
    await db.relations.update_many({"tree_id": tid, "id": {"$nin": rel_ids}, "deleted_at": None}, {"$set": {"deleted_at": now_utc()}})
    root_id = None
    for p in body.people:
        pid = p.get("id")
        if not pid:
            continue
        doc = {k: v for k, v in p.items() if k != "_id"}
        doc["deleted_at"] = None
        doc["tree_id"] = tid
        if doc.get("is_root"):
            root_id = pid
        await db.people.update_one({"id": pid}, {"$set": doc}, upsert=True)
    for r in body.relations:
        rid = r.get("id")
        if not rid:
            continue
        doc = {k: v for k, v in r.items() if k != "_id"}
        doc["deleted_at"] = None
        doc["tree_id"] = tid
        await db.relations.update_one({"id": rid}, {"$set": doc}, upsert=True)
    if root_id:
        await db.trees.update_one({"id": tid}, {"$set": {"root_person_id": root_id}})
    return {"ok": True, "people": len(body.people), "relations": len(body.relations)}


# ---------------------------------------------------------------------------
# Trees (multi-tenant) + Subscription + Members
# ---------------------------------------------------------------------------
@api_router.get("/trees")
async def list_trees(user=Depends(get_current_user)):
    members = await db.tree_members.find({"user_id": user["user_id"]}, {"_id": 0}).sort("joined_at", 1).to_list(200)
    out = []
    for m in members:
        tree = await db.trees.find_one({"id": m["tree_id"]}, {"_id": 0})
        if not tree:
            continue
        if is_superadmin(user):
            tree["plan"] = "unlimited"
        else:
            tree = await _check_plan_expiry(tree)
        count = await tree_person_count(tree["id"])
        member_count = await db.tree_members.count_documents({"tree_id": tree["id"]})
        limits = plan_limits(effective_plan(tree))
        out.append({
            **tree,
            "role": m["role"],
            "person_count": count,
            "member_count": member_count,
            "editor_count": await editor_count(tree["id"]),
            "photo_count": await photo_count(tree["id"]),
            "plan_limits": limits,
            "limit": limits.get("people"),
            "storage_used": await storage_used(tree["id"]),
            "storage_limit": storage_limit(effective_plan(tree)),
        })
    return out


@api_router.post("/trees")
async def create_tree(body: TreeCreateInput, user=Depends(get_current_user)):
    # Setiap pengguna hanya boleh memiliki SATU pohon aktif miliknya sendiri.
    # Bergabung ke pohon orang lain (undangan / join-request) tidak dihitung,
    # jadi user whitelist tetap bisa ikut pohon pengundang DAN punya pohon sendiri.
    # Pohon yang sudah dihapus (hard delete) tidak dihitung, sehingga user boleh
    # membuat pohon baru setelah menghapus pohon lamanya.
    if await owned_tree_count(user["user_id"]) >= 1:
        raise HTTPException(
            status_code=409,
            detail="Anda sudah memiliki satu pohon. Hapus pohon tersebut terlebih dahulu "
                   "untuk membuat pohon baru.",
        )
    name = (body.name or "").strip() or f"Keluarga {user['name']}"
    tree = await create_tree_for_user(user, name)
    # Payload harus identik dengan item GET /trees supaya klien bisa memakai
    # respons ini langsung (kuota storage juga wajib ada, bukan hanya plan_limits).
    limits = plan_limits(effective_plan(tree))
    return {**tree, "role": "admin", "person_count": 1, "member_count": 1,
            "editor_count": 0, "photo_count": 0, "plan_limits": limits,
            "limit": limits.get("people"),
            "storage_used": await storage_used(tree["id"]),
            "storage_limit": storage_limit(effective_plan(tree))}


@api_router.post("/trees/{tid}/claim-branch")
async def claim_branch(tid: str, body: ClaimBranchInput, user=Depends(get_current_user)):
    """Copy a person (and, per scope, their family) into a NEW tree owned by the
    caller. The source tree stays intact. New tree is always plan=free."""
    tree, role = await resolve_tree(user, tid)  # any member may claim
    if not tree:
        raise HTTPException(status_code=403, detail="Anda bukan anggota pohon ini")
    scope = body.scope if body.scope in ("descendants", "children", "whole") else "descendants"

    people = await db.people.find({"tree_id": tid, "deleted_at": None}, {"_id": 0}).to_list(5000)
    relations = await db.relations.find({"tree_id": tid, "deleted_at": None}, {"_id": 0}).to_list(10000)
    pset = {p["id"] for p in people}
    if body.person_id not in pset:
        raise HTTPException(status_code=404, detail="Orang tidak ditemukan di pohon ini")

    # children map from parent relations (person_id = parent, related_person_id = child)
    children_of: dict = {}
    spouses_of: dict = {}
    for r in relations:
        if r["relation_type"] in ("parent", "adopted_child"):
            children_of.setdefault(r["person_id"], []).append(r["related_person_id"])
        elif r["relation_type"] in ("spouse", "divorced"):
            spouses_of.setdefault(r["person_id"], set()).add(r["related_person_id"])
            spouses_of.setdefault(r["related_person_id"], set()).add(r["person_id"])

    selected: set = set()
    if scope == "whole":
        selected = set(pset)
    else:
        # start with the person + (all descendants OR direct children)
        selected.add(body.person_id)
        if scope == "descendants":
            stack = [body.person_id]
            while stack:
                cur = stack.pop()
                for ch in children_of.get(cur, []):
                    if ch not in selected:
                        selected.add(ch)
                        stack.append(ch)
        else:  # children
            for ch in children_of.get(body.person_id, []):
                selected.add(ch)
        # include spouses of everyone selected so couples stay intact
        for pid in list(selected):
            for sp in spouses_of.get(pid, set()):
                selected.add(sp)

    # Create the new tree (free) owned by the caller, without an auto root person.
    default_name = next((p["name"] for p in people if p["id"] == body.person_id), user["name"])
    new_name = (body.name or "").strip() or f"Cabang {default_name}"

    # Kuota orang: pohon baru selalu plan=free. Tanpa cek ini, cabang berisi
    # 300 orang bisa disalin dari pohon pro dan langsung menembus batas 50.
    lim_people = plan_limits("free").get("people")
    if lim_people is not None and len(selected) > lim_people:
        raise HTTPException(
            status_code=402,
            detail=f"LIMIT_REACHED:Cabang ini berisi {len(selected)} orang, melebihi batas "
                   f"{lim_people} orang untuk paket free. Pilih cabang yang lebih kecil "
                   f"(mis. scope 'children').",
        )

    # Kuota penyimpanan: foto orang TIDAK disalin, hanya `photo_url`/`path` yang
    # dirujuk ulang. File di storage dipakai bersama, tetapi biayanya tetap nyata,
    # jadi pohon hasil claim harus menanggung porsi byte-nya.
    photo_paths = set()
    for p in people:
        if p["id"] not in selected:
            continue
        for raw in [p.get("photo_url")] + [
            (g or {}).get("path") for g in (p.get("gallery") or [])
        ]:
            norm = _normalize_photo_path(raw)
            if norm:
                photo_paths.add(norm)
    inherited_bytes = 0
    if photo_paths:
        inherited_bytes = await _sum_storage_bytes(photo_paths)
    lim_storage = storage_limit("free")
    if lim_storage is not None and inherited_bytes > lim_storage:
        raise HTTPException(
            status_code=402,
            detail=f"STORAGE_LIMIT:Foto pada cabang ini ({fmt_size(inherited_bytes)}) melebihi "
                   f"kuota penyimpanan paket free ({fmt_size(lim_storage)}). "
                   f"Pilih cabang yang lebih kecil atau upgrade setelah dibuat.",
        )

    new_tree = await create_tree_for_user(user, new_name, make_root=False)
    new_tid = new_tree["id"]

    # Copy the selected people with fresh ids.
    id_map: dict = {}
    new_people = []
    for p in people:
        if p["id"] not in selected:
            continue
        nid = str(uuid.uuid4())
        id_map[p["id"]] = nid
        doc = {**p}
        doc.pop("_id", None)
        doc["id"] = nid
        doc["tree_id"] = new_tid
        doc["is_root"] = p["id"] == body.person_id
        doc["created_by"] = user["user_id"]
        doc["created_at"] = now_utc()
        doc["deleted_at"] = None
        new_people.append(doc)
    if new_people:
        await db.people.insert_many(new_people)

    # Copy relations where BOTH endpoints are in the selected set, remapped.
    new_rels = []
    for r in relations:
        if r["person_id"] in id_map and r["related_person_id"] in id_map:
            doc = {**r}
            doc.pop("_id", None)
            doc["id"] = str(uuid.uuid4())
            doc["person_id"] = id_map[r["person_id"]]
            doc["related_person_id"] = id_map[r["related_person_id"]]
            doc["tree_id"] = new_tid
            doc["deleted_at"] = None
            doc["created_at"] = now_utc()
            new_rels.append(doc)
    if new_rels:
        await db.relations.insert_many(new_rels)

    root_new_id = id_map.get(body.person_id)
    await db.trees.update_one({"id": new_tid}, {"$set": {"root_person_id": root_new_id}})

    # Catat byte warisan foto. Tanpa ini pohon hasil claim tampak 0 MB dan
    # pengguna bisa terus mengunggah melewati kuota free.
    if inherited_bytes:
        await add_storage_usage(new_tid, inherited_bytes)

    count = len(new_people)
    return {
        **new_tree, "root_person_id": root_new_id, "role": "admin",
        "person_count": count, "member_count": 1, "editor_count": 0, "photo_count": 0,
        "plan_limits": plan_limits("free"), "limit": FREE_PERSON_LIMIT, "copied": count,
        "storage_used": inherited_bytes,
    }


@api_router.get("/trees/search")
async def search_trees(q: str = Query(""), user=Depends(get_current_user)):
    """Search PUBLIC trees by name so a user can request to join."""
    q = (q or "").strip()
    if len(q) < 2:
        return []
    trees = await db.trees.find(
        {"is_public": True, "name": {"$regex": q, "$options": "i"}}, {"_id": 0}
    ).limit(20).to_list(20)
    my = {m["tree_id"] for m in await db.tree_members.find({"user_id": user["user_id"]}, {"_id": 0, "tree_id": 1}).to_list(500)}
    pend = {r["tree_id"] for r in await db.join_requests.find({"user_id": user["user_id"], "status": "pending"}, {"_id": 0, "tree_id": 1}).to_list(500)}
    out = []
    for tr in trees:
        owner = await db.users.find_one({"user_id": tr.get("owner_id")}, {"_id": 0, "name": 1})
        out.append({
            "id": tr["id"], "name": tr["name"], "owner_name": owner["name"] if owner else "?",
            "member_count": await db.tree_members.count_documents({"tree_id": tr["id"]}),
            "is_member": tr["id"] in my, "pending": tr["id"] in pend,
        })
    return out


@api_router.post("/trees/{tid}/join-request")
async def create_join_request(tid: str, user=Depends(get_current_user)):
    tree = await db.trees.find_one({"id": tid}, {"_id": 0})
    if not tree:
        raise HTTPException(status_code=404, detail="Pohon tidak ditemukan")
    if await db.tree_members.find_one({"tree_id": tid, "user_id": user["user_id"]}):
        raise HTTPException(status_code=400, detail="Anda sudah menjadi anggota pohon ini")
    if not await db.join_requests.find_one({"tree_id": tid, "user_id": user["user_id"], "status": "pending"}):
        await db.join_requests.insert_one({
            "id": str(uuid.uuid4()), "tree_id": tid, "user_id": user["user_id"],
            "status": "pending", "created_at": now_utc(),
        })
    return {"ok": True, "status": "pending", "tree_name": tree["name"]}


@api_router.get("/trees/{tid}/join-requests")
async def list_join_requests(tid: str, user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tid)
    require_role_t(role, ["admin"])
    reqs = await db.join_requests.find({"tree_id": tid, "status": "pending"}, {"_id": 0}).to_list(500)
    out = []
    for r in reqs:
        u = await db.users.find_one({"user_id": r["user_id"]}, {"_id": 0})
        out.append({**r, "name": u["name"] if u else "?", "email": u.get("email") if u else None, "picture": u.get("picture") if u else None})
    return _serialize(out)


@api_router.post("/join-requests/{req_id}/{action}")
async def act_join_request(req_id: str, action: str, user=Depends(get_current_user)):
    if action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Aksi tidak valid")
    req = await db.join_requests.find_one({"id": req_id}, {"_id": 0})
    if not req:
        raise HTTPException(status_code=404, detail="Permintaan tidak ditemukan")
    tree, role = await resolve_tree(user, req["tree_id"])
    require_role_t(role, ["admin"])
    if action == "approve":
        if not await db.tree_members.find_one({"tree_id": req["tree_id"], "user_id": req["user_id"]}):
            await ensure_can_join(tree)
            await db.tree_members.insert_one({
                "id": str(uuid.uuid4()), "tree_id": req["tree_id"], "user_id": req["user_id"],
                "role": "editor", "joined_at": now_utc(),
            })
        await db.join_requests.update_one({"id": req_id}, {"$set": {"status": "approved", "resolved_at": now_utc()}})
    else:
        await db.join_requests.update_one({"id": req_id}, {"$set": {"status": "rejected", "resolved_at": now_utc()}})
    return {"ok": True}


@api_router.put("/trees/{tid}/visibility")
async def set_tree_visibility(tid: str, body: dict = Body(...), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tid)
    require_role_t(role, ["admin"])
    val = bool(body.get("is_public"))
    await db.trees.update_one({"id": tid}, {"$set": {"is_public": val}})
    return {"ok": True, "is_public": val}


async def _purge_tree(tid: str):
    room_ids = [tid] + [r["id"] for r in await db.chat_rooms.find({"tree_id": tid}, {"_id": 0, "id": 1}).to_list(2000)]
    await db.trees.delete_one({"id": tid})
    await db.tree_members.delete_many({"tree_id": tid})
    await db.people.delete_many({"tree_id": tid})
    await db.relations.delete_many({"tree_id": tid})
    await db.person_notes.delete_many({"tree_id": tid})
    await db.app_notifications.delete_many({"tree_id": tid})
    await db.join_requests.delete_many({"tree_id": tid})
    await db.tree_invites.delete_many({"tree_id": tid})
    await db.chat_rooms.delete_many({"tree_id": tid})
    await db.family_chat.delete_many({"room_id": {"$in": room_ids}})
    await db.chat_typing.delete_many({"room_id": {"$in": room_ids}})
    await db.chat_mutes.delete_many({"room_id": {"$in": room_ids}})
    await db.tree_usage.delete_one({"tree_id": tid})


@api_router.delete("/trees/{tid}")
async def delete_tree(tid: str, user=Depends(get_current_user)):
    """Permanently delete a tree and all its data. Only the tree OWNER may do this."""
    tree = await db.trees.find_one({"id": tid}, {"_id": 0})
    if not tree:
        raise HTTPException(status_code=404, detail="Pohon tidak ditemukan")
    if tree.get("owner_id") != user["user_id"]:
        raise HTTPException(status_code=403, detail="Hanya pemilik yang dapat menghapus pohon")
    await _purge_tree(tid)
    return {"ok": True}


@api_router.post("/chat/rooms/{room_id}/leave")
async def leave_group(room_id: str, tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    if not tree:
        raise HTTPException(status_code=403, detail="Anda belum tergabung dalam pohon keluarga mana pun")
    room = await db.chat_rooms.find_one({"id": room_id, "tree_id": tree["id"]}, {"_id": 0})
    if not room or room.get("type") != "group":
        raise HTTPException(status_code=404, detail="Grup tidak ditemukan")
    if user["user_id"] not in room.get("member_ids", []):
        raise HTTPException(status_code=400, detail="Anda bukan anggota grup ini")
    remaining = [m for m in room["member_ids"] if m != user["user_id"]]
    if not remaining:
        await db.chat_rooms.delete_one({"id": room_id})
        await db.family_chat.delete_many({"room_id": room_id})
    else:
        await db.chat_rooms.update_one({"id": room_id}, {"$set": {"member_ids": remaining}})
    await db.chat_mutes.delete_one({"user_id": user["user_id"], "room_id": room_id})
    return {"ok": True}


class FeedbackInput(BaseModel):
    message: str
    category: Optional[str] = "general"


@api_router.post("/feedback")
async def submit_feedback(body: FeedbackInput, user=Depends(get_current_user)):
    if not (body.message or "").strip():
        raise HTTPException(status_code=400, detail="Masukan kosong")
    await db.feedback.insert_one({
        "id": str(uuid.uuid4()), "user_id": user["user_id"], "name": user.get("name"),
        "email": user.get("email"), "category": body.category or "general",
        "message": body.message.strip(), "status": "new", "created_at": now_utc(),
    })
    return {"ok": True}


@api_router.delete("/account")
async def delete_account(user=Depends(get_current_user)):
    if is_superadmin(user):
        raise HTTPException(status_code=403, detail="Akun superadmin tidak dapat dihapus")
    uid = user["user_id"]
    owned = await db.trees.find({"owner_id": uid}, {"_id": 0, "id": 1}).to_list(1000)
    for tr in owned:
        await _purge_tree(tr["id"])
    await db.tree_members.delete_many({"user_id": uid})
    await db.chat_rooms.update_many({"member_ids": uid}, {"$pull": {"member_ids": uid}})
    await db.user_sessions.delete_many({"user_id": uid})
    await db.chat_mutes.delete_many({"user_id": uid})
    await db.app_notifications.delete_many({"user_id": uid})
    await db.join_requests.delete_many({"user_id": uid})
    await db.users.delete_one({"user_id": uid})
    return {"ok": True}


@api_router.get("/admin/overview")
async def admin_overview(user=Depends(get_current_user)):
    if not is_superadmin(user):
        raise HTTPException(status_code=403, detail="Akses ditolak")
    now = now_utc()
    d7 = now - timedelta(days=7)
    d30 = now - timedelta(days=30)
    d1 = now - timedelta(days=1)

    total_users = await db.users.count_documents({})
    new_7d = await db.users.count_documents({"created_at": {"$gte": d7}})
    new_30d = await db.users.count_documents({"created_at": {"$gte": d30}})
    active_7d = len(await db.user_sessions.distinct("user_id", {"created_at": {"$gte": d7}}))

    total_trees = await db.trees.count_documents({})
    free_trees = await db.trees.count_documents({"plan": "free"})
    pro_trees = await db.trees.count_documents({"plan": "pro"})
    family_trees = await db.trees.count_documents({"plan": "family"})

    paid = await db.payment_orders.find({"status": "paid"}, {"_id": 0, "amount": 1, "paid_at": 1}).to_list(5000)
    revenue_total = sum(o.get("amount", 0) for o in paid)
    revenue_30d = sum(o.get("amount", 0) for o in paid if o.get("paid_at") and _aware(o["paid_at"]) >= d30)
    paid_count = len(paid)

    total_people = await db.people.count_documents({"deleted_at": None})
    total_messages = await db.family_chat.count_documents({"deleted_at": None})

    # Funnel
    owners = len(await db.trees.distinct("owner_id"))
    payers = len(await db.payment_orders.distinct("user_id", {"status": "paid"}))
    funnel = [
        {"step": "Daftar", "count": total_users},
        {"step": "Buat Pohon", "count": owners},
        {"step": "Upgrade", "count": payers},
    ]

    # Feature usage proxies
    features = [
        {"key": "Anggota ditambahkan", "count": total_people},
        {"key": "Pesan chat", "count": total_messages},
        {"key": "Grup chat", "count": await db.chat_rooms.count_documents({"type": "group"})},
        {"key": "Chat pribadi", "count": await db.chat_rooms.count_documents({"type": "direct"})},
        {"key": "Permintaan gabung", "count": await db.join_requests.count_documents({})},
        {"key": "Foto anggota", "count": await db.people.count_documents({"photo_url": {"$nin": [None, ""]}, "deleted_at": None})},
    ]
    features.sort(key=lambda f: f["count"], reverse=True)

    # Tech
    recent = list(RECENT_TIMINGS)
    last_hour = [r for r in recent if r[0] >= now - timedelta(hours=1)]
    avg_ms = round(sum(r[2] for r in last_hour) / len(last_hour), 1) if last_hour else 0
    req_1h = len(last_hour)
    err_24h = await db.error_logs.count_documents({"created_at": {"$gte": d1}})
    errors = _serialize(await db.error_logs.find({}, {"_id": 0}).sort("created_at", -1).to_list(15))
    db_counts = {
        "users": total_users, "trees": total_trees, "people": total_people,
        "relations": await db.relations.count_documents({"deleted_at": None}),
        "messages": total_messages, "feedback": await db.feedback.count_documents({}),
    }

    return {
        "business": {
            "total_users": total_users, "new_users_7d": new_7d, "new_users_30d": new_30d,
            "active_users_7d": active_7d, "total_trees": total_trees,
            "plans": {"free": free_trees, "pro": pro_trees, "family": family_trees},
            "revenue_total": revenue_total, "revenue_30d": revenue_30d, "paid_count": paid_count,
        },
        "funnel": funnel,
        "features": features,
        "tech": {
            "avg_response_ms": avg_ms, "requests_1h": req_1h, "errors_24h": err_24h,
            "db_counts": db_counts, "recent_errors": errors,
        },
    }


@api_router.get("/admin/users")
async def admin_users(user=Depends(get_current_user)):
    if not is_superadmin(user):
        raise HTTPException(status_code=403, detail="Akses ditolak")
    users = await db.users.find({}, {"_id": 0, "password": 0}).sort("created_at", -1).to_list(100)
    out = []
    for u in _serialize(users):
        u["tree_count"] = await db.tree_members.count_documents({"user_id": u["user_id"]})
        out.append(u)
    return {"users": out}


@api_router.get("/admin/feedback")
async def admin_feedback(user=Depends(get_current_user)):
    if not is_superadmin(user):
        raise HTTPException(status_code=403, detail="Akses ditolak")
    items = _serialize(await db.feedback.find({}, {"_id": 0}).sort("created_at", -1).to_list(200))
    return {"feedback": items}


@api_router.post("/trees/{tid}/upgrade")
async def upgrade_tree(tid: str, user=Depends(get_current_user), body: Optional[UpgradeInput] = None):
    """Aktifkan plan berbayar TANPA pembayaran. Hanya untuk superadmin (uji coba
    internal / kompensasi). Upgrade berbayar wajib lewat POST /payments/snap agar
    setiap pohon berbayar benar-benar menghasilkan pendapatan, bukan gratis.

    `body` dibuat OPSIONAL (default None) supaya otorisasi diperiksa LEBIH DULU:
    dengan body wajib, FastAPI membalas 422 sebelum handler jalan, sehingga
    non-member menerima 422 (bocor info validasi) alih-alih 403.
    """
    # 1) Otorisasi dulu, baru validasi input.
    if not is_superadmin(user):
        raise HTTPException(
            status_code=403,
            detail="Upgrade plan hanya dapat dilakukan melalui pembayaran",
        )
    tree, role = await resolve_tree(user, tid)
    require_role_t(role, ["admin"])

    # 2) Validasi input setelah otorisasi lolos.
    plan = (body.plan if body else None) or "pro"
    plan = plan if plan in ("free", "pro", "family") else "pro"
    if plan == "free":
        await db.trees.update_one({"id": tid}, {"$set": {"plan": "free"}, "$unset": {"expires_at": "", "expiry_reminder_7": "", "expiry_reminder_1": ""}})
    else:
        await db.trees.update_one({"id": tid}, {"$set": {"plan": plan, "upgraded_at": now_utc(), "expires_at": now_utc() + timedelta(days=365)}, "$unset": {"expiry_reminder_7": "", "expiry_reminder_1": ""}})
    return {"ok": True, "plan": plan}


class PaymentInput(BaseModel):
    plan: str
    finish_url: Optional[str] = None


async def _activate_order(order):
    if order.get("status") == "paid":
        return
    await db.trees.update_one(
        {"id": order["tree_id"]},
        {"$set": {"plan": order["plan"], "upgraded_at": now_utc(), "expires_at": now_utc() + timedelta(days=365)},
         "$unset": {"expiry_reminder_7": "", "expiry_reminder_1": ""}},
    )
    await db.payment_orders.update_one({"order_id": order["order_id"]}, {"$set": {"status": "paid", "paid_at": now_utc()}})


@api_router.post("/payments/snap")
async def create_snap(body: PaymentInput, tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    if not MIDTRANS_SERVER_KEY:
        raise HTTPException(status_code=503, detail="Pembayaran belum dikonfigurasi")
    if body.plan not in PLAN_PRICES:
        raise HTTPException(status_code=400, detail="Paket tidak valid")
    tree, role = await resolve_tree(user, tree_id)
    require_role_t(role, ["admin"])
    amount = PLAN_PRICES[body.plan]
    order_id = f"KTR-{tree['id'][:8]}-{secrets.token_hex(5)}"
    await db.payment_orders.insert_one({
        "order_id": order_id, "user_id": user["user_id"], "tree_id": tree["id"],
        "plan": body.plan, "amount": amount, "status": "pending", "created_at": now_utc(),
    })
    payload = {
        "transaction_details": {"order_id": order_id, "gross_amount": amount},
        "item_details": [{"id": body.plan, "price": amount, "quantity": 1, "name": f"Titisanku {body.plan.upper()}"}],
        "customer_details": {"first_name": user.get("name", "User"), "email": user.get("email", "")},
    }
    if body.finish_url:
        payload["callbacks"] = {"finish": body.finish_url}
    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.post(MIDTRANS_SNAP_URL, json=payload, auth=(MIDTRANS_SERVER_KEY, ""),
                               headers={"Accept": "application/json"})
    if resp.status_code >= 300:
        logger.error("Midtrans snap error %s %s", resp.status_code, resp.text)
        raise HTTPException(status_code=502, detail="Gagal membuat transaksi pembayaran")
    data = resp.json()
    return {"order_id": order_id, "token": data.get("token"), "redirect_url": data.get("redirect_url"),
            "amount": amount, "plan": body.plan}


@api_router.post("/payments/notification")
async def midtrans_notification(payload: dict = Body(...)):
    order_id = payload.get("order_id", "")
    status_code = payload.get("status_code", "")
    gross_amount = payload.get("gross_amount", "")
    sig = payload.get("signature_key", "")
    expected = hashlib.sha512(f"{order_id}{status_code}{gross_amount}{MIDTRANS_SERVER_KEY}".encode()).hexdigest()
    if sig != expected:
        raise HTTPException(status_code=403, detail="Invalid signature")
    order = await db.payment_orders.find_one({"order_id": order_id}, {"_id": 0})
    if not order:
        return {"ok": True}
    tstatus = payload.get("transaction_status")
    fraud = payload.get("fraud_status")
    if tstatus in ("capture", "settlement") and fraud in (None, "accept"):
        # Pastikan uang yang dibayar sesuai harga paket yang dibeli. Tanpa cek ini
        # notifikasi dengan gross_amount lebih kecil tetap mengaktifkan plan penuh.
        try:
            paid = int(round(float(gross_amount)))
        except (TypeError, ValueError):
            paid = -1
        if paid != int(order.get("amount", -1)):
            logger.warning("midtrans: nominal tidak cocok untuk %s (bayar=%s, tagihan=%s)",
                           order_id, gross_amount, order.get("amount"))
            return {"ok": True}
        await _activate_order(order)
    elif tstatus in ("cancel", "deny", "expire"):
        await db.payment_orders.update_one({"order_id": order_id}, {"$set": {"status": "failed"}})
    return {"ok": True}


@api_router.get("/payments/status/{order_id}")
async def payment_status(order_id: str, user=Depends(get_current_user)):
    order = await db.payment_orders.find_one({"order_id": order_id}, {"_id": 0})
    if not order or order["user_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="Order tidak ditemukan")
    # Proactively confirm with Midtrans (covers cases where the webhook hasn't arrived yet).
    if order["status"] == "pending" and MIDTRANS_SERVER_KEY:
        try:
            async with httpx.AsyncClient(timeout=20) as http:
                r = await http.get(f"{MIDTRANS_STATUS_BASE}/v2/{order_id}/status",
                                   auth=(MIDTRANS_SERVER_KEY, ""), headers={"Accept": "application/json"})
            if r.status_code < 300:
                d = r.json()
                if d.get("transaction_status") in ("capture", "settlement") and d.get("fraud_status") in (None, "accept"):
                    await _activate_order(order)
                    order["status"] = "paid"
        except Exception as e:
            logger.warning("payment status check failed: %s", e)
    return {"status": order["status"], "plan": order["plan"]}


@api_router.get("/payments/history")
async def payment_history(user=Depends(get_current_user)):
    orders = await db.payment_orders.find(
        {"user_id": user["user_id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    out = []
    for o in _serialize(orders):
        tree = await db.trees.find_one({"id": o.get("tree_id")}, {"_id": 0, "name": 1})
        o["tree_name"] = tree.get("name") if tree else None
        out.append(o)
    return {"orders": out}


@api_router.get("/trees/{tid}/members")
async def list_members(tid: str, user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tid)
    if not tree:
        raise HTTPException(status_code=403, detail="Anda bukan anggota pohon ini")
    members = await db.tree_members.find({"tree_id": tid}, {"_id": 0}).to_list(2000)
    out = []
    for m in members:
        u = await db.users.find_one({"user_id": m["user_id"]}, {"_id": 0})
        out.append({
            "user_id": m["user_id"],
            "role": m["role"],
            "name": u["name"] if u else "?",
            "email": u["email"] if u else None,
            "picture": u.get("picture") if u else None,
            "is_owner": tree.get("owner_id") == m["user_id"],
        })
    return {"members": _serialize(out), "role": role, "owner_id": tree.get("owner_id")}


@api_router.put("/trees/{tid}/members/role")
async def change_member_role(tid: str, body: MemberRoleInput, user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tid)
    require_role_t(role, ["admin"])
    if body.user_id == tree.get("owner_id"):
        raise HTTPException(status_code=400, detail="Tidak bisa mengubah peran pemilik pohon")
    if body.role not in ("admin", "editor", "viewer"):
        raise HTTPException(status_code=400, detail="Peran tidak valid")
    current = await db.tree_members.find_one({"tree_id": tid, "user_id": body.user_id}, {"_id": 0})
    if body.role == "editor" and (not current or current.get("role") != "editor"):
        lim_ed = plan_limits(effective_plan(tree)).get("editors")
        if lim_ed is not None and await editor_count(tid) >= lim_ed:
            raise HTTPException(status_code=402, detail=f"EDITOR_LIMIT:Batas {lim_ed} editor untuk paket ini sudah tercapai.")
    await db.tree_members.update_one({"tree_id": tid, "user_id": body.user_id}, {"$set": {"role": body.role}})
    return {"ok": True}


@api_router.delete("/trees/{tid}/members/{member_id}")
async def remove_member(tid: str, member_id: str, user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tid)
    require_role_t(role, ["admin"])
    if member_id == tree.get("owner_id"):
        raise HTTPException(status_code=400, detail="Pemilik pohon tidak bisa dihapus")
    await db.tree_members.delete_one({"tree_id": tid, "user_id": member_id})
    return {"ok": True}


@api_router.post("/trees/{tid}/invite-link")
async def create_invite_link(tid: str, user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tid)
    require_role_t(role, ["admin"])
    # reuse an existing active link for this tree if present
    existing = await db.tree_invites.find_one({"tree_id": tid, "active": True}, {"_id": 0})
    if existing:
        return {"token": existing["token"]}
    token = secrets.token_urlsafe(9)
    await db.tree_invites.insert_one({
        "id": str(uuid.uuid4()),
        "tree_id": tid,
        "token": token,
        "role": "editor",
        "created_by": user["user_id"],
        "created_at": now_utc(),
        "active": True,
    })
    return {"token": token}


@api_router.get("/invite-info/{token}")
async def invite_info(token: str, user=Depends(get_current_user)):
    inv = await db.tree_invites.find_one({"token": token, "active": True}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Undangan tidak valid atau sudah tidak aktif")
    tree = await db.trees.find_one({"id": inv["tree_id"]}, {"_id": 0})
    if not tree:
        raise HTTPException(status_code=404, detail="Pohon tidak ditemukan")
    inviter = await db.users.find_one({"user_id": inv["created_by"]}, {"_id": 0})
    member = await db.tree_members.find_one({"tree_id": inv["tree_id"], "user_id": user["user_id"]})
    return {
        "tree_id": inv["tree_id"],
        "tree_name": tree.get("name"),
        "inviter_name": inviter["name"] if inviter else "?",
        "role": inv.get("role", "editor"),
        "already_member": bool(member),
    }


@api_router.post("/invite-accept/{token}")
async def invite_accept(token: str, user=Depends(get_current_user)):
    inv = await db.tree_invites.find_one({"token": token, "active": True}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Undangan tidak valid atau sudah tidak aktif")
    tree = await db.trees.find_one({"id": inv["tree_id"]}, {"_id": 0})
    if not tree:
        raise HTTPException(status_code=404, detail="Pohon tidak ditemukan")
    existing = await db.tree_members.find_one({"tree_id": inv["tree_id"], "user_id": user["user_id"]})
    if not existing:
        await ensure_can_join(tree)
        lim_ed = plan_limits(effective_plan(tree)).get("editors")
        if lim_ed is not None and await editor_count(inv["tree_id"]) >= lim_ed:
            raise HTTPException(status_code=402, detail=f"EDITOR_LIMIT:Batas {lim_ed} editor untuk paket ini sudah tercapai. Upgrade untuk menambah editor.")
        await db.tree_members.insert_one({
            "id": str(uuid.uuid4()),
            "tree_id": inv["tree_id"],
            "user_id": user["user_id"],
            "role": inv.get("role", "editor"),
            "joined_at": now_utc(),
        })
    return {"tree_id": inv["tree_id"], "name": tree.get("name")}



# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
async def migrate_multitenant():
    """One-time migration: attach existing single-tree data to a default tree.
    Idempotent via a meta flag. Never deletes data."""
    flag = await db.meta.find_one({"key": "migrated_multitenant"})
    if flag:
        return
    people_exist = await db.people.count_documents({})
    trees_exist = await db.trees.count_documents({})
    if trees_exist == 0 and people_exist > 0:
        admin = await db.users.find_one({"role": "admin"}, {"_id": 0})
        if not admin:
            admin = await db.users.find_one({}, {"_id": 0})
        meta = await db.meta.find_one({"key": "root_person_id"}, {"_id": 0})
        root_pid = meta["value"] if meta else None
        tree_id = f"tree_{uuid.uuid4().hex[:12]}"
        owner_id = admin["user_id"] if admin else "unknown"
        await db.trees.insert_one({
            "id": tree_id,
            "name": f"Keluarga {admin['name']}" if admin else "Keluarga Saya",
            "owner_id": owner_id,
            "plan": "free",
            "root_person_id": root_pid,
            "created_at": now_utc(),
        })
        # stamp all existing data with tree_id
        await db.people.update_many({"tree_id": {"$exists": False}}, {"$set": {"tree_id": tree_id}})
        await db.relations.update_many({"tree_id": {"$exists": False}}, {"$set": {"tree_id": tree_id}})
        await db.person_notes.update_many({"tree_id": {"$exists": False}}, {"$set": {"tree_id": tree_id}})
        await db.app_notifications.update_many({"tree_id": {"$exists": False}}, {"$set": {"tree_id": tree_id}})
        # migrate chat room_id (was admin user_id) -> tree_id (only docs not yet migrated)
        await db.family_chat.update_many({"tree_id": {"$exists": False}}, {"$set": {"room_id": tree_id, "tree_id": tree_id}})
        await db.chat_typing.update_many({"room_id": {"$exists": True}}, {"$set": {"room_id": tree_id}})
        # add all existing users as members with their global role
        all_users = await db.users.find({}, {"_id": 0}).to_list(5000)
        for u in all_users:
            existing = await db.tree_members.find_one({"tree_id": tree_id, "user_id": u["user_id"]})
            if existing:
                continue
            await db.tree_members.insert_one({
                "id": str(uuid.uuid4()),
                "tree_id": tree_id,
                "user_id": u["user_id"],
                "role": u.get("role", "viewer"),
                "joined_at": u.get("created_at", now_utc()),
            })
        logger.info(f"Migrated existing data to default tree {tree_id}")
    await db.meta.update_one({"key": "migrated_multitenant"}, {"$set": {"value": True}}, upsert=True)


@app.on_event("startup")
async def startup():
    try:
        await db.users.create_index("email", unique=True)
        await db.users.create_index("user_id", unique=True)
        await db.user_sessions.create_index("session_token", unique=True)
        await db.user_sessions.create_index("user_id")
        await db.user_sessions.create_index("expires_at", expireAfterSeconds=0)
        await db.people.create_index("id", unique=True)
        await db.people.create_index("tree_id")
        await db.relations.create_index("tree_id")
        await db.tree_members.create_index([("tree_id", 1), ("user_id", 1)])
        await db.tree_members.create_index("user_id")
        await db.trees.create_index("id", unique=True)
    except Exception as e:
        logger.warning(f"Index setup: {e}")
    try:
        await migrate_multitenant()
    except Exception as e:
        logger.warning(f"Multitenant migration: {e}")
    # Status integrasi (bukan lagi bergantung pada Emergent).
    status = integrations.describe_config()
    missing = [k for k, ok in status.items() if not ok]
    if missing:
        logger.warning("Integrasi belum dikonfigurasi: %s", ", ".join(missing))
    else:
        logger.info("Semua integrasi terkonfigurasi: %s", ", ".join(status))

@api_router.get("/")
async def root():
    return {"message": "KETURUNANKU API"}

@api_router.get("/integrations/status")
async def integrations_status():
    """Diagnostik: layanan pihak ketiga mana yang sudah aktif."""
    return integrations.describe_config()



app.include_router(api_router)


@app.middleware("http")
async def metrics_middleware(request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as e:
        ms = (time.perf_counter() - start) * 1000
        RECENT_TIMINGS.append((now_utc(), request.url.path, ms, 500))
        try:
            await db.error_logs.insert_one({
                "id": str(uuid.uuid4()), "path": str(request.url.path), "method": request.method,
                "status": 500, "detail": str(e)[:400], "created_at": now_utc(),
            })
        except Exception:
            pass
        raise
    ms = (time.perf_counter() - start) * 1000
    path = request.url.path
    RECENT_TIMINGS.append((now_utc(), path, ms, response.status_code))
    if response.status_code >= 500 and path.startswith("/api"):
        try:
            await db.error_logs.insert_one({
                "id": str(uuid.uuid4()), "path": str(path), "method": request.method,
                "status": response.status_code, "detail": "", "created_at": now_utc(),
            })
        except Exception:
            pass
    return response


app.add_middleware(
    CORSMiddleware,
    # "*" + credentials tidak diizinkan browser. Bila allow-all diminta secara eksplisit
    # lewat CORS_ORIGINS=*, kirim "*" tanpa credentials; selain itu pakai daftar origin
    # eksplisit dengan credentials aktif.
    allow_credentials=not CORS_ALLOW_ALL,
    allow_origins=["*"] if CORS_ALLOW_ALL else CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Global error handling
# ---------------------------------------------------------------------------
# Tanpa handler ini, exception yang tidak tertangkap akan diproses oleh
# ServerErrorMiddleware (lapisan terluar) dan respons 500-nya TIDAK melewati
# CORSMiddleware. Akibatnya header CORS hilang dan browser melaporkan
# "blocked by CORS policy" / "Failed to fetch" — menutupi error 500 asli.
# Handler di bawah mengembalikan JSONResponse yang tetap melewati CORS middleware.
@app.exception_handler(PyMongoError)
async def mongo_error_handler(request: Request, exc: PyMongoError):
    logger.error("Database error pada %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "Database tidak tersedia. Silakan coba beberapa saat lagi."},
        headers=cors_headers_for(request),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Jaring pengaman terakhir: selalu balas JSON + header CORS, jangan biarkan
    # ServerErrorMiddleware mengembalikan respons tanpa header CORS.
    logger.exception("Unhandled error pada %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Terjadi kesalahan pada server."},
        headers=cors_headers_for(request),
    )


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
