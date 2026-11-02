"""Integrasi pihak ketiga Titisanku (mandiri, tanpa Emergent).

Modul ini menyediakan empat layanan eksternal yang dipakai aplikasi:

1. **Firebase Auth** — verifikasi ID token Google Sign-In dari Firebase SDK client.
2. **Firebase Storage** — unggah/unduh objek binari (foto profil, galeri, lampiran).
3. **Resend** — kirim email undangan kolaborasi.
4. **Expo Push** — notifikasi push ke perangkat.

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


# ---------------------------------------------------------------------------
# Apple App Store — verifikasi transaksi StoreKit 2 (JWS)
#
# Klien iOS mengirim `transactionJws` hasil `getTransactionJwsIOS()`. JWS itu
# ditandatangani Apple (ES256) dengan rantai sertifikat x5c = [leaf, intermediate,
# root]. Server TIDAK mempercayai isi payload sebelum rantai tersebut terbukti
# berakar pada sertifikat root Apple, sehingga klien tidak bisa memalsukan
# `productId`/`expiresDate` untuk mengaktifkan plan gratis.
#
# Bila kredensial App Store Server API (issuer id, key id, .p8) diisi, status
# langganan juga dicek ulang ke Apple supaya refund/pembatalan terdeteksi.
# ---------------------------------------------------------------------------
_APPLE_ROOT_G3_URL = "https://www.apple.com/certificateauthority/AppleRootCA-G3.cer"
_APPLE_API_BASE = "https://api.storekit.itunes.apple.com"
_APPLE_API_BASE_SANDBOX = "https://api.storekit-sandbox.itunes.apple.com"
_apple_root_cache: Dict[str, Any] = {"cert": None, "expires_at": 0.0}


def apple_api_configured() -> bool:
    """Kredensial opsional App Store Server API tersedia."""
    return bool(
        env("APPLE_ISSUER_ID")
        and env("APPLE_KEY_ID")
        and (env("APPLE_PRIVATE_KEY_PATH") or env("APPLE_PRIVATE_KEY_P8"))
    )


def apple_jws_configured() -> bool:
    """Verifikasi JWS hanya butuh bundle id aplikasi iOS."""
    return bool(env("APPLE_BUNDLE_ID") or env("IOS_BUNDLE_ID"))


def _apple_bundle_id() -> str:
    bundle = env("APPLE_BUNDLE_ID") or env("IOS_BUNDLE_ID")
    if not bundle:
        raise IntegrationError("APPLE_BUNDLE_ID belum diset.")
    return bundle


def _apple_root_cert():
    """Ambil & cache sertifikat root Apple (Apple Root CA - G3)."""
    now = time.time()
    if _apple_root_cache["cert"] is not None and now < _apple_root_cache["expires_at"]:
        return _apple_root_cache["cert"]
    try:
        from cryptography import x509
    except ImportError as exc:  # pragma: no cover
        raise IntegrationError("Paket 'cryptography' belum terpasang") from exc

    resp = requests.get(_APPLE_ROOT_G3_URL, timeout=30)
    if resp.status_code != 200:
        raise IntegrationError(f"Gagal mengunduh sertifikat root Apple: {resp.status_code}")
    cert = x509.load_der_x509_certificate(resp.content)
    _apple_root_cache["cert"] = cert
    _apple_root_cache["expires_at"] = now + 86400
    return cert


def _b64url_decode(part: str) -> bytes:
    pad = "=" * (-len(part) % 4)
    return base64.urlsafe_b64decode(part + pad)


def verify_apple_jws(transaction_jws: str) -> Dict[str, Any]:
    """Verifikasi JWS transaksi Apple dan kembalikan payload-nya.

    Melempar ``IntegrationError`` bila tanda tangan tidak valid, bundle id tidak
    cocok, atau langganan sudah kedaluwarsa/direfund.
    """
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
        from cryptography.exceptions import InvalidSignature
    except ImportError as exc:  # pragma: no cover
        raise IntegrationError("Paket 'cryptography' belum terpasang") from exc

    parts = (transaction_jws or "").split(".")
    if len(parts) != 3:
        raise IntegrationError("Format JWS transaksi Apple tidak valid.")
    header_b64, payload_b64, signature_b64 = parts
    try:
        header = json.loads(_b64url_decode(header_b64))
        payload = json.loads(_b64url_decode(payload_b64))
        signature = _b64url_decode(signature_b64)
    except (ValueError, TypeError) as exc:
        raise IntegrationError("JWS transaksi Apple tidak dapat dibaca.") from exc

    chain = header.get("x5c") or []
    if len(chain) < 2:
        raise IntegrationError("JWS tidak menyertakan rantai sertifikat Apple.")

    try:
        leaf = x509.load_der_x509_certificate(base64.b64decode(chain[0]))
        intermediate = x509.load_der_x509_certificate(base64.b64decode(chain[1]))
    except Exception as exc:  # pragma: no cover - sertifikat rusak
        raise IntegrationError("Sertifikat pada JWS tidak valid.") from exc

    # 1) Rantai sertifikat harus berakar pada Apple Root CA - G3.
    root = _apple_root_cert()
    try:
        intermediate.verify_directly_issued_by(root)
        leaf.verify_directly_issued_by(intermediate)
    except Exception as exc:
        raise IntegrationError("Rantai sertifikat JWS bukan milik Apple.") from exc

    # 2) Tanda tangan JWS harus cocok dengan kunci publik leaf.
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    public_key = leaf.public_key()
    try:
        if isinstance(public_key, ec.EllipticCurvePublicKey):
            public_key.verify(signature, signing_input, ec.ECDSA(hashes.SHA256()))
        elif isinstance(public_key, rsa.RSAPublicKey):
            public_key.verify(signature, signing_input, padding.PKCS1v15(), hashes.SHA256())
        else:  # pragma: no cover - algoritma tak terduga
            raise IntegrationError("Algoritma tanda tangan JWS tidak didukung.")
    except InvalidSignature as exc:
        raise IntegrationError("Tanda tangan JWS transaksi Apple tidak valid.") from exc

    # 3) Payload harus milik aplikasi kita.
    bundle = payload.get("bundleId")
    if bundle != _apple_bundle_id():
        raise IntegrationError(f"JWS berasal dari bundle lain: {bundle}")

    # 4) Langganan harus masih berlaku (expiresDate dalam milidetik).
    expires_ms = payload.get("expiresDate")
    if not isinstance(expires_ms, (int, float)):
        raise IntegrationError("Transaksi tidak memuat expiresDate.")
    if expires_ms / 1000.0 <= time.time():
        raise IntegrationError("Langganan Apple sudah kedaluwarsa.")
    if payload.get("revocationDate"):
        raise IntegrationError("Transaksi Apple sudah direfund/dicabut.")

    return payload


def _apple_api_token() -> str:
    """JWT ES256 untuk App Store Server API (berlaku ~5 menit)."""
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
    except ImportError as exc:  # pragma: no cover
        raise IntegrationError("Paket 'cryptography' belum terpasang") from exc

    issuer = env("APPLE_ISSUER_ID")
    key_id = env("APPLE_KEY_ID")
    key_path = env("APPLE_PRIVATE_KEY_PATH")
    inline_key = env("APPLE_PRIVATE_KEY_P8")
    if not (issuer and key_id and (key_path or inline_key)):
        raise IntegrationError("Kredensial App Store Server API belum lengkap.")

    pem = inline_key or Path(key_path or "").read_text(encoding="utf-8")

    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    now = int(time.time())
    header = {"alg": "ES256", "kid": key_id, "typ": "JWT"}
    claims = {
        "iss": issuer,
        "iat": now,
        "exp": now + 300,
        "aud": "appstoreconnect-v1",
        "bid": _apple_bundle_id(),
    }
    signing_input = (
        f"{b64(json.dumps(header, separators=(',', ':')).encode())}."
        f"{b64(json.dumps(claims, separators=(',', ':')).encode())}"
    )
    key = load_pem_private_key(pem.encode("utf-8"), password=None)
    der_sig = key.sign(signing_input.encode("ascii"), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der_sig)
    # JWS ES256 memakai R||S mentah (masing-masing 32 byte), bukan DER.
    raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return f"{signing_input}.{b64(raw)}"


def apple_subscription_status(original_transaction_id: str, sandbox: bool = False) -> Dict[str, Any]:
    """Status langganan otoritatif dari App Store Server API."""
    token = _apple_api_token()
    base = _APPLE_API_BASE_SANDBOX if sandbox else _APPLE_API_BASE
    resp = requests.get(
        f"{base}/inApps/v1/subscriptions/{original_transaction_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if resp.status_code == 404 and not sandbox:
        # Transaksi sandbox (mis. saat App Review) tidak ada di host produksi.
        return apple_subscription_status(original_transaction_id, sandbox=True)
    if resp.status_code != 200:
        raise IntegrationError(f"App Store Server API gagal: {resp.status_code} {resp.text[:200]}")
    return resp.json()


def describe_config() -> Dict[str, bool]:
    """Ringkasan status konfigurasi, dipakai endpoint /health dan /api/integrations."""
    return {
        "firebase_auth": bool(env("FIREBASE_PROJECT_ID") and firebase_credentials_available()),
        "firebase_storage": bool(env("FIREBASE_STORAGE_BUCKET") and firebase_credentials_available()),
        "resend_email": bool(env("RESEND_API_KEY")),
        "expo_push": True,  # Expo Push API gratis, tanpa key
        "midtrans": bool(env("MIDTRANS_SERVER_KEY")),
        "play_billing": play_api_configured(),
        "apple_iap": apple_jws_configured(),
        "apple_server_api": apple_api_configured(),
    }


# ---------------------------------------------------------------------------
# Firebase — service account (dipakai untuk Storage & verifikasi token admin)
# ---------------------------------------------------------------------------
_FIREBASE_SCOPES = [
    "https://www.googleapis.com/auth/firebase",
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/devstorage.full_control",
]

_service_token_cache: Dict[str, Dict[str, Any]] = {}


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


def firebase_access_token(scopes: Optional[list[str]] = None) -> str:
    """Ambil OAuth2 access token dari service account (di-cache sampai ~50 menit).

    ``scopes`` opsional: bila diisi (mis. scope Google Play Developer API), token
    yang dikembalikan berlaku untuk scope tersebut dan di-cache terpisah.
    """
    now = time.time()
    scope_list = scopes or _FIREBASE_SCOPES
    cache_key = " ".join(sorted(scope_list))
    cached = _service_token_cache.get(cache_key)
    if cached and now < cached["expires_at"]:
        return cached["token"]

    creds = firebase_credentials_dict()
    if not creds:
        raise IntegrationError(
            "Firebase belum dikonfigurasi: set FIREBASE_SERVICE_ACCOUNT_JSON "
            "(path file) atau FIREBASE_SERVICE_ACCOUNT_JSON_INLINE (isi JSON)."
        )

    claims = {
        "iss": creds["client_email"],
        "scope": " ".join(scope_list),
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
    _service_token_cache[cache_key] = {
        "token": token,
        "expires_at": now + payload.get("expires_in", 3600) - 600,
    }
    return token


# ---------------------------------------------------------------------------
# Google Play Developer API — verifikasi pembelian (Play Billing)
# ---------------------------------------------------------------------------
_PLAY_SCOPE = "https://www.googleapis.com/auth/androidpublisher"
_PLAY_API_BASE = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications"


def play_api_configured() -> bool:
    """Konfigurasi minimal untuk memverifikasi pembelian Play sudah ada."""
    return bool(env("PLAY_PACKAGE_NAME") and firebase_credentials_available())

def verify_play_subscription(purchase_token: str, subscription_id: str) -> Dict[str, Any]:
    """Verifikasi & ambil status langganan dari Google Play Developer API.

    Mengembalikan dict ``subscriptionPurchase`` bila pembelian valid. Pembelian
    yang tidak valid, kedaluwarsa, atau token palsu akan melempar
    ``IntegrationError``.
    """
    package = env("PLAY_PACKAGE_NAME") or env("ANDROID_PACKAGE_NAME")
    if not package:
        raise IntegrationError("PLAY_PACKAGE_NAME belum diset.")
    try:
        token = firebase_access_token([_PLAY_SCOPE])
    except IntegrationError as e:
        logger.error("Gagal ambil token Play API: %s", e)
        raise

    url = f"{_PLAY_API_BASE}/{package}/purchases/subscriptions/{subscription_id}/tokens/{purchase_token}"
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if resp.status_code == 404:
        raise IntegrationError("Pembelian tidak ditemukan (token/produk tidak valid).")
    if resp.status_code != 200:
        raise IntegrationError(f"Verifikasi Play gagal: {resp.status_code} {resp.text[:200]}")
    return resp.json()


def acknowledge_play_purchase(subscription_id: str, purchase_token: str) -> None:
    """Acknowledge pembelian agar Play tidak mengembalikan dana setelah 3 hari."""
    package = env("PLAY_PACKAGE_NAME") or env("ANDROID_PACKAGE_NAME")
    if not package:
        raise IntegrationError("PLAY_PACKAGE_NAME belum diset.")
    token = firebase_access_token([_PLAY_SCOPE])
    url = f"{_PLAY_API_BASE}/{package}/purchases/subscriptions/{subscription_id}/tokens/{purchase_token}:acknowledge"
    resp = requests.post(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if resp.status_code not in (200, 204):
        raise IntegrationError(f"Acknowledge Play gagal: {resp.status_code} {resp.text[:200]}")



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
