import asyncio, os, uuid
from datetime import datetime, timezone, timedelta
import httpx
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
BASE = "http://localhost:8001/api"


def now():
    return datetime.now(timezone.utc)


async def main():
    uid = f"user_{uuid.uuid4().hex[:12]}"
    token = uuid.uuid4().hex
    await db.users.insert_one({"user_id": uid, "email": f"{uid}@t.dev", "name": "Sib Test", "role": "admin", "created_at": now()})
    await db.user_sessions.insert_one({"session_token": token, "user_id": uid, "created_at": now(), "expires_at": now() + timedelta(days=7)})
    h = {"Authorization": f"Bearer {token}"}
    tid = None
    async with httpx.AsyncClient(base_url=BASE, headers=h, timeout=30) as c:
        tree = (await c.post("/trees", json={"name": "Sib"})).json()
        tid = tree["id"]
        root = (await c.get("/tree", params={"tree_id": tid})).json()["root_id"]

        # Case A: sibling of root (no parents) -> explicit sibling relation
        r = await c.post("/people/add-relative", params={"tree_id": tid}, json={"focus_id": root, "direction": "sibling", "person": {"name": "Kakak Root"}})
        assert r.status_code == 200, r.text
        sib_root = r.json()["person"]["id"]
        data = (await c.get("/tree", params={"tree_id": tid})).json()
        sib_rel = [x for x in data["relations"] if x["relation_type"] == "sibling"]
        assert len(sib_rel) == 1 and {sib_rel[0]["person_id"], sib_rel[0]["related_person_id"]} == {root, sib_root}, sib_rel
        print("PASS sibling of root -> explicit sibling relation")

        # add a child to root, then a sibling of that child -> should share parent (root)
        child = (await c.post("/people/add-relative", params={"tree_id": tid}, json={"focus_id": root, "direction": "child", "person": {"name": "Anak 1"}})).json()["person"]["id"]
        r = await c.post("/people/add-relative", params={"tree_id": tid}, json={"focus_id": child, "direction": "sibling", "person": {"name": "Adik dari Anak"}})
        assert r.status_code == 200, r.text
        new_sib = r.json()["person"]["id"]
        data = (await c.get("/tree", params={"tree_id": tid})).json()
        # new_sib must have root as a parent (relation parent: person_id=root, related_person_id=new_sib)
        parent_rel = [x for x in data["relations"] if x["relation_type"] == "parent" and x["person_id"] == root and x["related_person_id"] == new_sib]
        assert len(parent_rel) == 1, [x for x in data["relations"] if x["related_person_id"] == new_sib]
        print("PASS sibling of child -> shares parent (root)")

        # add both mother & father to child, then sibling should link to BOTH parents
        c.headers.update(h)
        mom = (await c.post("/people/add-relative", params={"tree_id": tid}, json={"focus_id": child, "direction": "mother", "person": {"name": "Ibu"}})).json()["person"]["id"]
        dad = (await c.post("/people/add-relative", params={"tree_id": tid}, json={"focus_id": child, "direction": "father", "person": {"name": "Ayah"}})).json()["person"]["id"]
        r = await c.post("/people/add-relative", params={"tree_id": tid}, json={"focus_id": child, "direction": "sibling", "person": {"name": "Saudara Lengkap"}})
        assert r.status_code == 200, r.text
        full_sib = r.json()["person"]["id"]
        data = (await c.get("/tree", params={"tree_id": tid})).json()
        parents_of_full = {x["person_id"] for x in data["relations"] if x["relation_type"] == "parent" and x["related_person_id"] == full_sib}
        # child now has parents root, mom, dad -> sibling should link to all three
        assert {root, mom, dad}.issubset(parents_of_full), parents_of_full
        print("PASS sibling links to ALL parents:", parents_of_full)

    # cleanup
    await db.people.delete_many({"tree_id": tid})
    await db.relations.delete_many({"tree_id": tid})
    await db.trees.delete_many({"id": tid})
    await db.tree_members.delete_many({"tree_id": tid})
    await db.users.delete_many({"user_id": uid})
    await db.user_sessions.delete_many({"user_id": uid})
    print("\nSIBLING TESTS PASSED — cleaned up")


asyncio.run(main())
