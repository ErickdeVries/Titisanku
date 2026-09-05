"""Seed a realistic 3-generation family to visually verify the tidy tree layout.
Run: python /app/backend/tests/seed_tree_visual.py
Cleanup: python /app/backend/tests/seed_tree_visual.py --cleanup
"""
import os, sys, json, uuid, secrets
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
STAMP = "/tmp/keturunanku_visual_seed.json"


def now():
    return datetime.now(timezone.utc)


def person(tid, uid, name, gender, birth=None):
    return {"id": str(uuid.uuid4()), "tree_id": tid, "name": name, "gender": gender,
            "birth_date": birth, "is_alive": True, "is_root": False, "is_adopted": False,
            "created_by": uid, "created_at": now(), "deleted_at": None}


def spouse(tid, a, b, md="1985-06-20"):
    return {"id": str(uuid.uuid4()), "tree_id": tid, "person_id": a, "related_person_id": b,
            "relation_type": "spouse", "marriage_date": md, "divorce_date": None,
            "created_at": now(), "deleted_at": None}


def parent(tid, p, c):
    return {"id": str(uuid.uuid4()), "tree_id": tid, "person_id": p, "related_person_id": c,
            "relation_type": "parent", "created_at": now(), "deleted_at": None}


def seed():
    uid = f"user_VIS{uuid.uuid4().hex[:6]}"
    token = secrets.token_hex(16)
    tid = f"tree_VIS{uuid.uuid4().hex[:8]}"
    ppl, rels = [], []

    # Gen -1: grandparents (couple) + a sibling of grandpa with own spouse
    iqbal = person(tid, uid, "M. Iqbal Eppy", "male", "1950-01-01"); iqbal["is_root"] = True
    deliana = person(tid, uid, "Deliana Matondang", "female", "1953-01-01")
    anwar = person(tid, uid, "Anwar Ismail", "male", "1948-01-01")
    siti = person(tid, uid, "Siti Bariah", "female", "1950-01-01")
    ppl += [iqbal, deliana, anwar, siti]
    rels += [spouse(tid, iqbal["id"], deliana["id"]),
             spouse(tid, anwar["id"], siti["id"])]

    # Gen 0: children of iqbal+deliana (Erick focus + siblings), Erick married to Mahdiana
    erick = person(tid, uid, "Erick De Vries", "male", "1980-03-01")
    mahdiana = person(tid, uid, "Mahdiana Harahap", "female", "1982-05-01")
    veronica = person(tid, uid, "Veronica De Vries", "female", "1983-07-01")
    antony = person(tid, uid, "Antony De Vries", "male", "1985-09-01")
    chairil = person(tid, uid, "Chairil Anwar", "male", "1978-02-01")
    ppl += [erick, mahdiana, veronica, antony, chairil]
    rels += [spouse(tid, erick["id"], mahdiana["id"], "2005-06-20")]
    for c in (erick, veronica, antony):
        rels += [parent(tid, iqbal["id"], c["id"]), parent(tid, deliana["id"], c["id"])]
    # chairil is child of anwar+siti (a cousin's parent line)
    rels += [parent(tid, anwar["id"], chairil["id"]), parent(tid, siti["id"], chairil["id"])]

    # Gen +1: 6 children of erick + mahdiana
    kids = ["Siti Anissa Devries", "Fatimah Azzahro", "Syafana Hanifah Devries",
            "Ahmad Rofii Devries", "Putri Yaomi Devries", "Abi Satria Mandala"]
    for i, kn in enumerate(kids):
        g = "female" if i in (0, 1, 2, 4) else "male"
        k = person(tid, uid, kn, g, f"200{i}-01-01")
        ppl.append(k)
        rels += [parent(tid, erick["id"], k["id"]), parent(tid, mahdiana["id"], k["id"])]

    db.users.insert_one({"user_id": uid, "email": f"VIS_{uuid.uuid4().hex[:6]}@ex.com",
                         "name": "VIS_Admin", "picture": None, "role": "admin", "created_at": now()})
    db.user_sessions.insert_one({"session_token": token, "user_id": uid,
                                 "created_at": now(), "expires_at": now() + timedelta(days=7)})
    db.trees.insert_one({"id": tid, "name": "Keluarga De Vries", "owner_id": uid,
                         "plan": "free", "root_person_id": iqbal["id"], "created_at": now()})
    db.tree_members.insert_one({"id": str(uuid.uuid4()), "tree_id": tid, "user_id": uid,
                                "role": "admin", "joined_at": now()})
    db.people.insert_many(ppl)
    db.relations.insert_many(rels)
    stamp = {"user_id": uid, "token": token, "tree_id": tid, "focus": erick["id"]}
    with open(STAMP, "w") as f:
        json.dump(stamp, f)
    print(json.dumps(stamp))


def cleanup():
    try:
        s = json.load(open(STAMP))
    except FileNotFoundError:
        return
    db.trees.delete_many({"id": s["tree_id"]})
    db.tree_members.delete_many({"tree_id": s["tree_id"]})
    db.people.delete_many({"tree_id": s["tree_id"]})
    db.relations.delete_many({"tree_id": s["tree_id"]})
    db.user_sessions.delete_many({"session_token": s["token"]})
    db.users.delete_many({"user_id": s["user_id"]})
    os.remove(STAMP)
    print("cleaned")


if __name__ == "__main__":
    cleanup() if "--cleanup" in sys.argv else seed()
