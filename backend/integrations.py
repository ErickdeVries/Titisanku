"""Integrasi pihak ketiga pengganti Emergent.

Modul ini menyediakan tiga layanan yang sebelumnya dibundel oleh Emergent:

1. **Firebase Auth** — verifikasi ID token dari Firebase (menggantikan
   OAuth ``auth.emergentagent.com`` + ``demobackend.emergentagent.com``).
2. **Firebase Storage** — unggah/unduh objek binari (menggantikan
   ``objstore`` Emergent).
3. **Resend** — kirim email undangan (menggantikan email Emergent).
4. **Expo Push** — notifikasi push (menggantikan push Emergent).

Semua integrasi bersifat *opsional* saat boot: bila environment variable belum
diisi, modul tidak gagal saat import, tetapi setiap pemanggilan akan melempar
``IntegrationError`` sehingga kegagalan terlihat jelas (tidak lagi *silent*).
"""
from __future__ import annotations

import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
import requests

logger = logging.getLogger("titisanku.integrations")


class IntegrationError(RuntimeError):
    """Kesalahan konfigurasi atau kegagalan layanan pihak ketiga."""


# ---------------------------------------------------------------------------
# Konfigurasi umum
# ---------------------------------------------------------------------------
def env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(name, default)
    if value is None:
        return None
    value = value.strip()
    return value or None


def describe_config() -> Dict[str, bool]:
    """Ringkasan status konfigurasi, dipakai endpoint /health dan /api/integrations."""
    return {
        "firebase_auth": bool(env("FIREBASE_PROJECT_ID") and firebase_credentials_available()),
        "firebase_storage": bool(env("FIREBASE_STORAGE_BUCKET") and firebase_credentials_available()),
        "resend_email": bool(env("RESEND_API_KEY")),
        "expo_push": True,  # Expo Push API gratis, tanpa key
        "midtrans": bool(env("MIDTRANS_SERVER_KEY")),
    }


# ---------------------------------------------------------------------------
# Firebase — service account (dipakai untuk Storage & verifikasi token admin)
# ---------------------------------------------------------------------------
_FIREBASE_SCOPES = [
    "https://www.googleapis.com/auth/firebase",
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/devstorage.full_control",
]

_service_token_cache: Dict[str, Any] = {"token": None, "expires_at": 0.0}


def firebase_credentials_path() -> Optional[Path]:
    raw = env("FIREBASE_SERVICE_ACCOUNT_JSON")
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_file() else None


def firebase_credentials_dict() -> Optional[Dict[str, Any]]:
    """Ambil service account dari file, atau dari JSON inline (aman untuk PaaS)."""
    path = firebase_credentials_path()
    if path:
        return json.loads(path.read_text(encoding="utf-8"))
    inline = env("FIREBASE_SERVICE_ACCOUNT_JSON_INLINE")
    if inline:
        return json.loads(inline)
    return None


def firebase_credentials_available() -> bool:
    return firebase_credentials_dict() is not None


def _sign_jwt(claims: Dict[str, Any], private_key: str, key_id: Optional[str]) -> str:
    """Buat JWT RS256 untuk Google OAuth2 (tanpa dependensi tambahan)."""
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except ImportError as exc:  # pragma: no cover
        raise IntegrationError("Paket 'cryptography' belum terpasang") from exc

    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    header = {"alg": "RS256", "typ": "JWT"}
    if key_id:
        header["kid"] = key_id
    signing_input = f"{b64(json.dumps(header, separators=(',', ':')).encode())}." \
                    f"{b64(json.dumps(claims, separators=(',', ':')).encode())}"

    key = serialization.load_pem_private_key(private_key.encode("utf-8"), password=None)
    signature = key.sign(signing_input.encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input}.{b64(signature)}"


def firebase_access_token() -> str:
    """Ambil OAuth2 access token dari service account (di-cache sampai ~50 menit)."""
    now = time.time()
    if _service_token_cache["token"] and now < _service_token_cache["expires_at"]:
        return _service_token_cache["token"]

    creds = firebase_credentials_dict()
    if not creds:
        raise IntegrationError(
            "Firebase belum dikonfigurasi: set FIREBASE_SERVICE_ACCOUNT_JSON "
            "(path file) atau FIREBASE_SERVICE_ACCOUNT_JSON_INLINE (isi JSON)."
        )

    claims = {
        "iss": creds["client_email"],
        "scope": " ".join(_FIREBASE_SCOPES),
        "aud": creds.get("token_uri", "https://oauth2.googleapis.com/token"),
        "iat": int(now),
        "exp": int(now) + 3600,
    }
    assertion = _sign_jwt(claims, creds["private_key"], creds.get("private_key_id"))

    resp = requests.post(
        creds.get("token_uri", "https://oauth2.googleapis.com/token"),
        data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
        timeout=30,
    )
    if resp.status_code != 200:
        raise IntegrationError(f"Gagal mengambil access token Firebase: {resp.status_code} {resp.text[:200]}")

    payload = resp.json()
    token = payload["access_token"]
    _service_token_cache["token"] = token
    # Refresh lebih awal 10 menit agar tidak kedaluwarsa di tengah permintaan.
    _service_token_cache["expires_at"] = now + payload.get("expires_in", 3600) - 600
    return token


# ---------------------------------------------------------------------------
# Firebase Auth — verifikasi ID token (JWT dari Firebase client SDK)
# ---------------------------------------------------------------------------
_FIREBASE_CERTS_URL = (
    "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
)
_certs_cache: Dict[str, Any] = {"certs": None, "expires_at": 0.0}


def _firebase_public_certs() -> Dict[str, str]:
    now = time.time()
    if _certs_cache["certs"] and now < _certs_cache["expires_at"]:
        return _certs_cache["certs"]

    resp = requests.get(_FIREBASE_CERTS_URL, timeout=30)
    if resp.status_code != 200:
        raise IntegrationError(f"Gagal mengambil sertifikat Firebase: {resp.status_code}")

    max_age = 3600
    cache_control = resp.headers.get("Cache-Control", "")
    for part in cache_control.split(","):
        part = part.strip()
        if part.startswith("max-age="):
            try:
                max_age = int(part.split("=", 1)[1])
            except ValueError:
                pass

    certs = resp.json()
    _certs_cache["certs"] = _certs_to_public_keys(certs)
    _certs_cache["expires_at"] = now + max(max_age - 300, 300)
    return _certs_cache["certs"]


def _certs_to_public_keys(certs: Dict[str, str]) -> Dict[str, Any]:
    """Ubah sertifikat X.509 (PEM) Google menjadi objek public key RS256.

    Endpoint ``robot/v1/metadata/x509`` mengembalikan sertifikat, bukan kunci
    publik. PyJWT tidak bisa memakainya, jadi kunci publik diekstrak dulu.
    """
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    from cryptography.x509 import load_pem_x509_certificate

    keys: Dict[str, Any] = {}
    for kid, pem in certs.items():
        try:
            keys[kid] = load_pem_x509_certificate(pem.encode("utf-8")).public_key()
        except Exception:
            # Sebagian isi endpoint bisa berupa public key biasa, bukan sertifikat.
            try:
                keys[kid] = load_pem_public_key(pem.encode("utf-8"))
            except Exception as exc:  # pragma: no cover - data rusak dari Google
                raise IntegrationError(
                    f"Gagal membaca kunci publik Firebase untuk kid={kid}: {exc}"
                ) from exc
    return keys


def verify_firebase_id_token(id_token: str) -> Dict[str, Any]:
    """Validasi ID token Firebase dan kembalikan klaimnya.

    Memverifikasi signature RS256 terhadap sertifikat publik Google, plus
    ``aud``/``iss``/``exp`` sesuai dokumentasi Firebase.
    """
    try:
        import jwt  # PyJWT
    except ImportError as exc:  # pragma: no cover
        raise IntegrationError("Paket 'pyjwt' belum terpasang") from exc

    project_id = env("FIREBASE_PROJECT_ID")
    if not project_id:
        raise IntegrationError("Firebase belum dikonfigurasi: set FIREBASE_PROJECT_ID.")

    try:
        header = jwt.get_unverified_header(id_token)
    except Exception as exc:
        raise IntegrationError(f"ID token tidak valid: {exc}") from exc

    kid = header.get("kid")
    certs = _firebase_public_certs()
    if not kid or kid not in certs:
        raise IntegrationError("ID token tidak valid: kid tidak dikenal")

    try:
        claims = jwt.decode(
            id_token,
            certs[kid],
            algorithms=["RS256"],
            audience=project_id,
            issuer=f"https://securetoken.google.com/{project_id}",
            options={"verify_iat": True, "require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except Exception as exc:
        raise IntegrationError(f"ID token tidak valid: {exc}") from exc

    if not claims.get("sub"):
        raise IntegrationError("ID token tidak valid: sub kosong")
    return claims


# ---------------------------------------------------------------------------
# Firebase Storage — unggah & unduh objek
# ---------------------------------------------------------------------------
def storage_upload(path: str, data: bytes, content_type: str = "application/octet-stream") -> Dict[str, Any]:
    """Unggah objek ke Firebase Storage (GCS JSON API)."""
    bucket = env("FIREBASE_STORAGE_BUCKET")
    if not bucket:
        raise IntegrationError("Firebase Storage belum dikonfigurasi: set FIREBASE_STORAGE_BUCKET.")

    token = firebase_access_token()
    url = f"https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o"
    resp = requests.post(
        url,
        params={"uploadType": "media", "name": path},
        headers={"Authorization": f"Bearer {token}", "Content-Type": content_type},
        data=data,
        timeout=180,
    )
    if resp.status_code == 404 and "bucket" in resp.text.lower():
        _ensure_bucket(bucket, token)
        resp = requests.post(
            url,
            params={"uploadType": "media", "name": path},
            headers={"Authorization": f"Bearer {token}", "Content-Type": content_type},
            data=data,
            timeout=180,
        )
    if resp.status_code not in (200, 201):
        raise IntegrationError(
            f"Upload ke Firebase Storage gagal: {resp.status_code} {resp.text[:300]}"
        )

    meta = resp.json()
    # URL publik (bucket harus boleh dibaca publik) agar <Image source={{ uri }}> langsung jalan.
    public_url = (
        f"https://firebasestorage.googleapis.com/v0/b/{bucket}/o/"
        f"{requests.utils.quote(meta['name'], safe='')}?alt=media"
    )
    return {"path": f"/api/files/{path}", "storage_path": path, "url": public_url, "size": meta.get("size")}


def _ensure_bucket(bucket: str, token: str) -> None:
    """Buat bucket Storage bila belum ada, dan izinkan pembacaan publik.

    Firebase Storage butuh bucket GCS; pada project baru bucket terkadang belum
    di-provision. Helper ini idempoten.
    """
    project_id = env("FIREBASE_PROJECT_ID")
    if not project_id:
        raise IntegrationError("FIREBASE_PROJECT_ID wajib diisi untuk membuat bucket Storage.")

    logger.info("Membuat bucket Storage '%s' di project '%s'...", bucket, project_id)
    resp = requests.post(
        "https://storage.googleapis.com/storage/v1/b",
        params={"project": project_id, "name": bucket},
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    if resp.status_code not in (200, 409):  # 409 = sudah ada
        raise IntegrationError(
            f"Gagal membuat bucket Storage: {resp.status_code} {resp.text[:300]}"
        )

    # Izinkan publik membaca objek (aplikasi menampilkan foto lewat URL langsung).
    iam = requests.post(
        f"https://storage.googleapis.com/storage/v1/b/{bucket}/iam",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "bindings": [
                {"role": "roles/storage.objectViewer", "members": ["allUsers"]}
            ]
        },
        timeout=60,
    )
    if iam.status_code not in (200, 400):
        logger.warning("Gagal mengatur akses publik bucket: %s %s", iam.status_code, iam.text[:200])


def storage_download(path: str) -> tuple[bytes, str]:
    """Unduh objek dari Firebase Storage, kembalikan (bytes, content_type)."""
    bucket = env("FIREBASE_STORAGE_BUCKET")
    if not bucket:
        raise IntegrationError("Firebase Storage belum dikonfigurasi: set FIREBASE_STORAGE_BUCKET.")

    token = firebase_access_token()
    url = f"https://storage.googleapis.com/storage/v1/b/{bucket}/o/{requests.utils.quote(path, safe='')}"
    resp = requests.get(url, params={"alt": "media"}, headers={"Authorization": f"Bearer {token}"}, timeout=180)
    if resp.status_code == 404:
        raise FileNotFoundError(path)
    if resp.status_code != 200:
        raise IntegrationError(f"Unduh dari Firebase Storage gagal: {resp.status_code}")

    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


def storage_size(path: str) -> Optional[int]:
    """Ukuran objek dalam byte, dibaca dari metadata GCS (tanpa mengunduh isinya).

    Mengembalikan None bila objek tidak ada. Dipakai skrip backfill kuota
    penyimpanan agar tidak perlu mengunduh seluruh file lama.
    """
    bucket = env("FIREBASE_STORAGE_BUCKET")
    if not bucket:
        raise IntegrationError("Firebase Storage belum dikonfigurasi: set FIREBASE_STORAGE_BUCKET.")

    token = firebase_access_token()
    url = f"https://storage.googleapis.com/storage/v1/b/{bucket}/o/{requests.utils.quote(path, safe='')}"
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if resp.status_code == 404:
        return None
    if resp.status_code == 200:
        size = resp.json().get("size")
        return int(size) if size is not None else None
    # Fallback: ambil metadata lewat HEAD pada media (beberapa konfigurasi
    # bucket membatasi JSON API metadata tetapi mengizinkan media).
    url_media = f"https://storage.googleapis.com/download/storage/v1/b/{bucket}/o/{requests.utils.quote(path, safe='')}"
    r2 = requests.get(url_media, params={"alt": "media"},
                      headers={"Authorization": f"Bearer {token}", "Range": "bytes=0-0"}, timeout=30)
    if r2.status_code in (200, 206):
        cr = r2.headers.get("Content-Range") or ""
        if "/" in cr:
            try:
                return int(cr.rsplit("/", 1)[1])
            except ValueError:
                return None
    raise IntegrationError(f"Gagal membaca metadata Firebase Storage: {resp.status_code}")


# ---------------------------------------------------------------------------
# Resend — email transaksional
# ---------------------------------------------------------------------------
def email_send(*, to: str, subject: str, html: str, from_name: Optional[str] = None) -> str:
    """Kirim email via Resend, kembalikan message id. Melempar error bila gagal."""
    api_key = env("RESEND_API_KEY")
    if not api_key:
        raise IntegrationError("Email belum dikonfigurasi: set RESEND_API_KEY.")

    sender_addr = env("EMAIL_FROM_ADDRESS", "onboarding@resend.dev")
    sender = f"{from_name or env('EMAIL_FROM_NAME', 'Titisanku')} <{sender_addr}>"

    resp = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"from": sender, "to": [to], "subject": subject, "html": html},
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        raise IntegrationError(f"Resend gagal ({resp.status_code}): {resp.text[:300]}")
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Expo Push — notifikasi push
# ---------------------------------------------------------------------------
PUSH_PLATFORM_TOKENS_URL = "https://exp.host/--/api/v2/push/send"


async def push_send(messages: list[dict]) -> list[dict]:
    """Kirim batch pesan ke Expo Push API. Tidak pernah melempar ke pemanggil."""
    if not messages:
        return []
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                PUSH_PLATFORM_TOKENS_URL,
                json=messages,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
        if resp.status_code >= 400:
            logger.warning("Expo Push gagal %s: %s", resp.status_code, resp.text[:200])
            return []
        data = resp.json().get("data", [])
        errors = [d for d in data if d.get("status") == "error"]
        if errors:
            logger.info("Expo Push sebagian gagal: %s", errors[:3])
        return data
    except Exception as exc:
        logger.warning("Expo Push exception: %s", exc)
        return []
