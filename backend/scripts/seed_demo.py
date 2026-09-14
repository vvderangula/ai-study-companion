"""Create demo accounts (learner + admin) for evaluators.

Usage (from backend/):  python -m scripts.seed_demo
Idempotent: existing accounts are left untouched. Passwords come from env or defaults below.
"""

from __future__ import annotations

import os

from app.core import db as dbm
from app.core.auth import hash_password
from app.models import User

ACCOUNTS = [
    ("Demo Learner", os.environ.get("DEMO_LEARNER_EMAIL", "demo@example.com"), os.environ.get("DEMO_LEARNER_PASSWORD", "demo12345"), "learner"),
    ("Demo Admin", os.environ.get("DEMO_ADMIN_EMAIL", "admin@example.com"), os.environ.get("DEMO_ADMIN_PASSWORD", "admin12345"), "admin"),
]


def main() -> None:
    dbm.init_db()
    for name, email, password, role in ACCOUNTS:
        existing = dbm.find_one(dbm.USERS, {"email": email})
        if existing:
            if existing.get("role") != role:
                dbm.update(dbm.USERS, {"_id": existing["_id"]}, {"role": role})
            print(f"exists: {email} ({role})")
            continue
        dbm.insert(dbm.USERS, User(full_name=name, email=email, password_hash=hash_password(password), role=role).to_doc())
        print(f"created: {email} / {password} ({role})")


if __name__ == "__main__":
    main()
