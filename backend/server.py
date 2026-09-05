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
    is_alive: Optional[bool] = None  # override; else auto from death_date


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
# Multi-tenant Tree helpers
# ---------------------------------------------------------------------------
FREE_PERSON_LIMIT = 50


class TreeCreateInput(BaseModel):
    name: str


class MemberRoleInput(BaseModel):
    user_id: str
    role: str  # editor | viewer


async def resolve_tree(user, tree_id: Optional[str]):
    """Return (tree, role) for the given user. If tree_id is None, use the
    user's primary (first joined) tree. Raises 403 if not a member."""
    q = {"user_id": user["user_id"]}
    if tree_id:
        q["tree_id"] = tree_id
    member = await db.tree_members.find_one(q, {"_id": 0}, sort=[("joined_at", 1)])
    if not member:
        if tree_id:
            raise HTTPException(status_code=403, detail="Anda bukan anggota pohon ini")
        return None, None
    tree = await db.trees.find_one({"id": member["tree_id"]}, {"_id": 0})
    if not tree:
        raise HTTPException(status_code=404, detail="Pohon tidak ditemukan")
    return tree, member["role"]


def require_role_t(role, roles):
    if role not in roles:
        raise HTTPException(status_code=403, detail="Permission denied")


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
        # Every brand-new user gets their own tree (they are its admin/owner).
        await create_tree_for_user(user_doc, f"Keluarga {name}")

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
    return {
        "people": people,
        "relations": relations,
        "root_id": root_id,
        "tree": tree,
        "role": role,
        "person_count": len(people),
        "limit": None if tree.get("plan") == "pro" else FREE_PERSON_LIMIT,
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
    return people


@api_router.get("/people/{person_id}")
async def get_person(person_id: str, tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    if not tree:
        raise HTTPException(status_code=404, detail="Person not found")
    p = await db.people.find_one({"id": person_id, "tree_id": tree["id"], "deleted_at": None}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Person not found")
    return p


@api_router.put("/people/{person_id}")
async def update_person(person_id: str, data: PersonData, tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    require_role_t(role, ["admin", "editor"])
    p = await db.people.find_one({"id": person_id, "tree_id": tree["id"], "deleted_at": None})
    if not p:
        raise HTTPException(status_code=404, detail="Person not found")
    d = data.model_dump()
    is_alive = d.pop("is_alive", None)
    if is_alive is None:
        is_alive = not bool(d.get("death_date"))
    d["is_alive"] = is_alive
    await db.people.update_one({"id": person_id}, {"$set": d})
    return await db.people.find_one({"id": person_id}, {"_id": 0})


@api_router.delete("/people/{person_id}")
async def delete_person(person_id: str, tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    require_role_t(role, ["admin"])
    if tree.get("root_person_id") == person_id:
        raise HTTPException(status_code=400, detail="Cannot delete root person")
    await db.people.update_one({"id": person_id, "tree_id": tree["id"]}, {"$set": {"deleted_at": now_utc()}})
    await db.relations.update_many(
        {"tree_id": tree["id"], "$or": [{"person_id": person_id}, {"related_person_id": person_id}]},
        {"$set": {"deleted_at": now_utc()}},
    )
    return {"ok": True}


@api_router.post("/people/add-relative")
async def add_relative(body: AddRelativeInput, tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    require_role_t(role, ["admin", "editor"])
    # Subscription limit for Free plan
    if tree.get("plan") != "pro":
        count = await tree_person_count(tree["id"])
        if count >= FREE_PERSON_LIMIT:
            raise HTTPException(
                status_code=402,
                detail=f"LIMIT_REACHED:Pohon gratis dibatasi {FREE_PERSON_LIMIT} orang. Upgrade ke Pro untuk menambah lebih banyak.",
            )
    focus = await db.people.find_one({"id": body.focus_id, "tree_id": tree["id"], "deleted_at": None}, {"_id": 0})
    if not focus:
        raise HTTPException(status_code=404, detail="Focus person not found")

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
# Person notes & files, Family chat, In-app notifications
# ---------------------------------------------------------------------------
class NoteInput(BaseModel):
    note_text: str


class ChatInput(BaseModel):
    message: Optional[str] = ""
    attachments: List[str] = []
    reply_to: Optional[str] = None
    mentions: List[str] = []  # user_ids mentioned


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


@api_router.get("/people/{person_id}/notes")
async def list_person_notes(person_id: str, tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
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
    path = f"{APP_NAME}/uploads/{user['user_id']}/{uuid.uuid4().hex}.{ext}"
    result = await run_in_threadpool(put_object, path, content, file.content_type or "application/octet-stream")
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


@api_router.get("/chat")
async def get_chat(tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    if not tree:
        return {"room_id": None, "room_name": "Keluarga", "messages": [], "alive_count": 0, "total_count": 0, "members": [], "typing": []}
    room = tree["id"]
    room_name = tree.get("name", "Keluarga")
    people = await db.people.find({"tree_id": room, "deleted_at": None}, {"_id": 0}).to_list(5000)
    total_count = len(people)
    alive_count = 0
    email_person = {}
    for p in people:
        alive = p.get("is_alive")
        if alive is None:
            alive = not bool(p.get("death_date"))
        if alive:
            alive_count += 1
        if p.get("email"):
            email_person[p["email"]] = {"id": p["id"], "is_alive": alive}
    member_rows = await db.tree_members.find({"tree_id": room}, {"_id": 0, "user_id": 1, "role": 1}).to_list(2000)
    member_ids = [m["user_id"] for m in member_rows if m["role"] in ("admin", "editor")]
    users_map = {u["user_id"]: u for u in await db.users.find({"user_id": {"$in": [m["user_id"] for m in member_rows]}}, {"_id": 0}).to_list(2000)}
    members = [{"user_id": uid, "name": users_map.get(uid, {}).get("name", "?")} for uid in member_ids]
    # read receipts: mark all others' messages as read by me
    await db.family_chat.update_many(
        {"room_id": room, "sender_id": {"$ne": user["user_id"]}, "read_by": {"$ne": user["user_id"]}, "deleted_at": None},
        {"$addToSet": {"read_by": user["user_id"]}},
    )
    msgs = await db.family_chat.find({"room_id": room, "deleted_at": None}, {"_id": 0}).sort("created_at", 1).to_list(3000)
    users = {u["user_id"]: u for u in await db.users.find({}, {"_id": 0}).to_list(2000)}
    out = []
    for m in _serialize(msgs):
        s = users.get(m["sender_id"], {})
        m["sender_name"] = s.get("name", "?")
        m["sender_picture"] = s.get("picture")
        match = email_person.get(s.get("email"))
        m["sender_is_alive"] = match["is_alive"] if match else True
        m["sender_person_id"] = match["id"] if match else None
        m["read_by"] = m.get("read_by", [])
        out.append(m)
    cutoff = now_utc() - timedelta(seconds=6)
    typing_names = []
    async for d in db.chat_typing.find({"room_id": room, "user_id": {"$ne": user["user_id"]}}, {"_id": 0}):
        upd = d.get("updated_at")
        if upd is not None and upd.tzinfo is None:
            upd = upd.replace(tzinfo=timezone.utc)
        if upd and upd > cutoff:
            typing_names.append(d.get("name", "?"))
    return {
        "room_id": room,
        "room_name": room_name,
        "messages": out,
        "alive_count": alive_count,
        "total_count": total_count,
        "members": members,
        "typing": typing_names,
    }


@api_router.post("/chat/typing")
async def chat_typing(tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    require_role_t(role, ["admin", "editor"])
    room = tree["id"]
    await db.chat_typing.update_one(
        {"user_id": user["user_id"], "room_id": room},
        {"$set": {"user_id": user["user_id"], "name": user["name"], "room_id": room, "updated_at": now_utc()}},
        upsert=True,
    )
    return {"ok": True}


@api_router.delete("/chat/{msg_id}")
async def delete_chat(msg_id: str, user=Depends(get_current_user)):
    m = await db.family_chat.find_one({"id": msg_id, "deleted_at": None}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Message not found")
    tree, role = await resolve_tree(user, m.get("room_id"))
    if role != "admin" and m["sender_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Hanya pengirim atau admin yang bisa menghapus pesan")
    await db.family_chat.update_one({"id": msg_id}, {"$set": {"deleted_at": now_utc()}})
    return {"ok": True}


@api_router.post("/chat")
async def send_chat(body: ChatInput, tree_id: Optional[str] = Query(None), user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tree_id)
    require_role_t(role, ["admin", "editor"])
    room = tree["id"]
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
        "room_id": room,
        "tree_id": room,
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
    await notify_tree(room, user["user_id"], "chat", "Pesan baru di Chat Keluarga", f"{user['name']}: {(body.message or 'Foto')[:60]}")
    # mention notifications
    mention_docs = []
    for uid in set(body.mentions):
        if uid == user["user_id"]:
            continue
        mention_docs.append({
            "id": str(uuid.uuid4()),
            "user_id": uid,
            "tree_id": room,
            "type": "mention",
            "title": "Anda disebut di Chat Keluarga",
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
        count = await tree_person_count(tree["id"])
        member_count = await db.tree_members.count_documents({"tree_id": tree["id"]})
        out.append({
            **tree,
            "role": m["role"],
            "person_count": count,
            "member_count": member_count,
            "limit": None if tree.get("plan") == "pro" else FREE_PERSON_LIMIT,
        })
    return out


@api_router.post("/trees")
async def create_tree(body: TreeCreateInput, user=Depends(get_current_user)):
    name = (body.name or "").strip() or f"Keluarga {user['name']}"
    tree = await create_tree_for_user(user, name)
    return {**tree, "role": "admin", "person_count": 1, "member_count": 1, "limit": FREE_PERSON_LIMIT}


@api_router.post("/trees/{tid}/upgrade")
async def upgrade_tree(tid: str, user=Depends(get_current_user)):
    """Activate Pro plan for a tree. (Payment via Midtrans handled separately.)"""
    tree, role = await resolve_tree(user, tid)
    require_role_t(role, ["admin"])
    await db.trees.update_one({"id": tid}, {"$set": {"plan": "pro", "upgraded_at": now_utc()}})
    return {"ok": True, "plan": "pro"}


@api_router.get("/trees/{tid}/members")
async def list_members(tid: str, user=Depends(get_current_user)):
    tree, role = await resolve_tree(user, tid)
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
