import asyncio, os, uuid, sys
from datetime import datetime, timezone, timedelta
import httpx
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
BASE = "http://localhost:8001/api"


def now():
    return datetime.now(timezone.utc)


async def seed_user(role="admin", name="Admin Test"):
    uid = f"user_{uuid.uuid4().hex[:12]}"
    token = uuid.uuid4().hex
    email = f"{uid}@test.dev"
    await db.users.insert_one({"user_id": uid, "email": email, "name": name, "picture": None, "role": role, "created_at": now()})
    await db.user_sessions.insert_one({"session_token": token, "user_id": uid, "created_at": now(), "expires_at": now() + timedelta(days=7)})
    return uid, token, email


async def main():
    created_users = []
    uid, token, email = await seed_user()
    created_users.append(uid)
    h = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=BASE, headers=h, timeout=30) as c:
        # Create a tree
        r = await c.post("/trees", json={"name": "Keluarga Uji"})
        assert r.status_code == 200, r.text
        tree = r.json()
        tid = tree["id"]
        print("PASS create tree", tid, "role", tree["role"], "count", tree["person_count"])

        # list trees
        r = await c.get("/trees")
        assert r.status_code == 200 and any(t["id"] == tid for t in r.json()), r.text
        print("PASS list trees", len(r.json()))

        # get tree data
        r = await c.get("/tree", params={"tree_id": tid})
        assert r.status_code == 200, r.text
        data = r.json()
        root = data["root_id"]
        assert root and data["role"] == "admin" and data["limit"] == 50
        print("PASS get tree root", root, "limit", data["limit"])

        # add a relative
        r = await c.post("/people/add-relative", params={"tree_id": tid}, json={
            "focus_id": root, "direction": "child", "person": {"name": "Anak 1"}})
        assert r.status_code == 200, r.text
        print("PASS add-relative")

        # backup
        r = await c.get("/backup", params={"tree_id": tid})
        assert r.status_code == 200 and len(r.json()["people"]) == 2, r.text
        print("PASS backup people", len(r.json()["people"]))

        # chat send + get
        r = await c.post("/chat", params={"tree_id": tid}, json={"message": "Halo keluarga"})
        assert r.status_code == 200, r.text
        r = await c.get("/chat", params={"tree_id": tid})
        assert r.status_code == 200 and len(r.json()["messages"]) == 1, r.text
        print("PASS chat", r.json()["room_id"] == tid)

        # limit test: bump plan back to free & set count high via inserting to threshold
        # simulate reaching limit
        docs = []
        for i in range(48):  # already 2 people -> add 48 = 50
            docs.append({"id": str(uuid.uuid4()), "tree_id": tid, "name": f"P{i}", "is_alive": True, "is_root": False, "deleted_at": None, "created_at": now()})
        await db.people.insert_many(docs)
        r = await c.post("/people/add-relative", params={"tree_id": tid}, json={
            "focus_id": root, "direction": "child", "person": {"name": "Over Limit"}})
        assert r.status_code == 402 and "LIMIT_REACHED" in r.json()["detail"], r.text
        print("PASS limit reached 402")

        # upgrade to pro
        r = await c.post(f"/trees/{tid}/upgrade")
        assert r.status_code == 200 and r.json()["plan"] == "pro", r.text
        r = await c.post("/people/add-relative", params={"tree_id": tid}, json={
            "focus_id": root, "direction": "child", "person": {"name": "After Pro"}})
        assert r.status_code == 200, r.text
        print("PASS upgrade unlocks add")

        # members
        r = await c.get(f"/trees/{tid}/members")
        assert r.status_code == 200 and len(r.json()["members"]) == 1, r.text
        print("PASS members", r.json()["members"][0]["is_owner"])

        # cross-tenant isolation: second user cannot access tid
        uid2, token2, _ = await seed_user(name="Other")
        created_users.append(uid2)
        async with httpx.AsyncClient(base_url=BASE, headers={"Authorization": f"Bearer {token2}"}, timeout=30) as c2:
            r = await c2.get("/tree", params={"tree_id": tid})
            assert r.status_code == 403, r.text
            print("PASS cross-tenant isolation 403")

    # cleanup
    await db.people.delete_many({"tree_id": tid})
    await db.relations.delete_many({"tree_id": tid})
    await db.family_chat.delete_many({"tree_id": tid})
    await db.trees.delete_many({"id": tid})
    await db.tree_members.delete_many({"tree_id": tid})
    await db.app_notifications.delete_many({"tree_id": tid})
    for u in created_users:
        await db.users.delete_many({"user_id": u})
        await db.user_sessions.delete_many({"user_id": u})
        await db.trees.delete_many({"owner_id": u})
        await db.tree_members.delete_many({"user_id": u})
    print("\nALL TESTS PASSED — cleaned up")


asyncio.run(main())
