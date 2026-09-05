import os
import uuid
import logging
import secrets
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import httpx
import requests
from fastapi import FastAPI, APIRouter, HTTPException, Header, Depends, UploadFile, File, Query
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pydantic import BaseModel, Field, EmailStr
from html import escape

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("keturunanku")

app = FastAPI()
api_router = APIRouter(prefix="/api")

# ---------------------------------------------------------------------------
# Object Storage
# ---------------------------------------------------------------------------
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_NAME = "keturunanku"
storage_key = None


def init_storage():
    global storage_key
    if storage_key:
        return storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    storage_key = resp.json()["storage_key"]
    return storage_key


def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data,
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def get_object(path: str):
    key = init_storage()
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


# ---------------------------------------------------------------------------
# Email (Emergent managed Resend)
# ---------------------------------------------------------------------------
EMAIL_BASE_URL = "https://integrations.emergentagent.com"
EMAIL_KEY = os.environ.get("EMERGENT_EMAIL_KEY")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "KETURUNANKU")


async def send_email(*, to: str, subject: str, html: str) -> Optional[str]:
    payload = {"to": [to], "subject": subject, "html": html, "from_name": EMAIL_FROM_NAME}
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            resp = await c.post(
                f"{EMAIL_BASE_URL}/api/v1/email/send",
                headers={"X-Email-Key": EMAIL_KEY},
                json=payload,
            )
        resp.raise_for_status()
        return resp.json().get("id")
    except Exception as e:
        logger.error(f"Email send error: {e}")
        raise HTTPException(status_code=502, detail="Failed to send invite email")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
def now_utc():
    return datetime.now(timezone.utc)


class PersonData(BaseModel):
    name: str
    gender: Optional[str] = None  # 'male' | 'female'
    birth_date: Optional[str] = None
    birth_place: Optional[str] = None
    death_date: Optional[str] = None
    photo_url: Optional[str] = None
    job: Optional[str] = None
    is_adopted: bool = False
    notes: Optional[str] = None


class AddRelativeInput(BaseModel):
    focus_id: str
    direction: str  # father | mother | spouse | child
    person: PersonData
    marriage_date: Optional[str] = None
    divorce_date: Optional[str] = None
    is_divorced: bool = False


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
# Auth routes
# ---------------------------------------------------------------------------
@api_router.post("/auth/session")
async def auth_session(body: SessionInput):
    async with httpx.AsyncClient(timeout=30) as c:
        resp = await c.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": body.session_id},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid session")
    data = resp.json()
    email = data["email"]
    name = data.get("name") or email.split("@")[0]
    picture = data.get("picture")
    session_token = data["session_token"]

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
        if is_first:
            person_id = str(uuid.uuid4())
            await db.people.insert_one({
                "id": person_id,
                "name": name,
                "gender": None,
                "birth_date": None,
                "birth_place": None,
                "death_date": None,
                "photo_url": picture,
                "job": None,
                "is_adopted": False,
                "notes": None,
                "is_root": True,
                "created_by": user_id,
                "created_at": now_utc(),
                "deleted_at": None,
            })
            await db.meta.update_one({"key": "root_person_id"}, {"$set": {"value": person_id}}, upsert=True)

    await db.user_sessions.insert_one({
        "session_token": session_token,
        "user_id": user_id,
        "created_at": now_utc(),
        "expires_at": now_utc() + timedelta(days=7),
    })
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return {"session_token": session_token, "user": user}


@api_router.get("/auth/me")
async def auth_me(user=Depends(get_current_user)):
    return user


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
async def get_tree(user=Depends(get_current_user)):
    people = await db.people.find({"deleted_at": None}, {"_id": 0}).to_list(5000)
    relations = await db.relations.find({"deleted_at": None}, {"_id": 0}).to_list(10000)
    meta = await db.meta.find_one({"key": "root_person_id"}, {"_id": 0})
    root_id = meta["value"] if meta else (people[0]["id"] if people else None)
    return {"people": people, "relations": relations, "root_id": root_id}


@api_router.get("/people")
async def list_people(q: Optional[str] = None, user=Depends(get_current_user)):
    query = {"deleted_at": None}
    if q:
        query["name"] = {"$regex": q, "$options": "i"}
    people = await db.people.find(query, {"_id": 0}).to_list(5000)
    return people


@api_router.get("/people/{person_id}")
async def get_person(person_id: str, user=Depends(get_current_user)):
    p = await db.people.find_one({"id": person_id, "deleted_at": None}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Person not found")
    return p


@api_router.put("/people/{person_id}")
async def update_person(person_id: str, data: PersonData, user=Depends(get_current_user)):
    require_role(user, ["admin", "editor"])
    p = await db.people.find_one({"id": person_id, "deleted_at": None})
    if not p:
        raise HTTPException(status_code=404, detail="Person not found")
    await db.people.update_one({"id": person_id}, {"$set": data.model_dump()})
    return await db.people.find_one({"id": person_id}, {"_id": 0})


@api_router.delete("/people/{person_id}")
async def delete_person(person_id: str, user=Depends(get_current_user)):
    require_role(user, ["admin"])
    meta = await db.meta.find_one({"key": "root_person_id"}, {"_id": 0})
    if meta and meta["value"] == person_id:
        raise HTTPException(status_code=400, detail="Cannot delete root person")
    await db.people.update_one({"id": person_id}, {"$set": {"deleted_at": now_utc()}})
    await db.relations.update_many(
        {"$or": [{"person_id": person_id}, {"related_person_id": person_id}]},
        {"$set": {"deleted_at": now_utc()}},
    )
    return {"ok": True}


@api_router.post("/people/add-relative")
async def add_relative(body: AddRelativeInput, user=Depends(get_current_user)):
    require_role(user, ["admin", "editor"])
    focus = await db.people.find_one({"id": body.focus_id, "deleted_at": None}, {"_id": 0})
    if not focus:
        raise HTTPException(status_code=404, detail="Focus person not found")

    pd = body.person.model_dump()
    if body.direction == "father":
        pd["gender"] = "male"
    elif body.direction == "mother":
        pd["gender"] = "female"

    new_id = str(uuid.uuid4())
    person_doc = {
        "id": new_id,
        **pd,
        "is_root": False,
        "created_by": user["user_id"],
        "created_at": now_utc(),
        "deleted_at": None,
    }
    await db.people.insert_one(person_doc)

    rel_id = str(uuid.uuid4())
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
    elif body.direction == "spouse":
        rel = {
            "id": rel_id,
            "person_id": body.focus_id,
            "related_person_id": new_id,
            "relation_type": "divorced" if body.is_divorced else "spouse",
            "marriage_date": body.marriage_date,
            "divorce_date": body.divorce_date,
        }
    else:
        raise HTTPException(status_code=400, detail="Invalid direction")
    rel["deleted_at"] = None
    rel["created_at"] = now_utc()
    await db.relations.insert_one(rel)

    return {"person": clean_person(person_doc), "relation_id": rel_id}


# ---------------------------------------------------------------------------
# Upload / Files
# ---------------------------------------------------------------------------
@api_router.post("/upload")
async def upload_file(file: UploadFile = File(...), user=Depends(get_current_user)):
    require_role(user, ["admin", "editor"])
    content = await file.read()
    ext = (file.filename or "photo.jpg").split(".")[-1].lower()
    path = f"{APP_NAME}/uploads/{user['user_id']}/{uuid.uuid4().hex}.{ext}"
    result = await run_in_threadpool(put_object, path, content, file.content_type or "image/jpeg")
    stored = result["path"]
    return {"path": stored, "url": f"/api/files/{stored}"}


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
async def backup(user=Depends(get_current_user)):
    require_role(user, ["admin"])
    users = await db.users.find({}, {"_id": 0}).to_list(5000)
    people = await db.people.find({}, {"_id": 0}).to_list(5000)
    relations = await db.relations.find({}, {"_id": 0}).to_list(10000)
    return {
        "exported_at": now_utc().isoformat(),
        "users": _serialize(users),
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
    email_id = None
    try:
        email_id = await send_email(to=body.email, subject=subject, html=html)
    except HTTPException:
        pass
    return {"code": code, "email_id": email_id, "email": body.email}


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
# Startup
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup():
    try:
        await db.users.create_index("email", unique=True)
        await db.users.create_index("user_id", unique=True)
        await db.user_sessions.create_index("session_token", unique=True)
        await db.user_sessions.create_index("user_id")
        await db.user_sessions.create_index("expires_at", expireAfterSeconds=0)
        await db.people.create_index("id", unique=True)
    except Exception as e:
        logger.warning(f"Index setup: {e}")
    try:
        await run_in_threadpool(init_storage)
    except Exception as e:
        logger.warning(f"Storage init failed: {e}")


@api_router.get("/")
async def root():
    return {"message": "KETURUNANKU API"}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
