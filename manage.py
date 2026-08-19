"""Small admin CLI.

    python manage.py createuser [--username U] [--email E] [--password P]
    python manage.py listusers
    python manage.py seed [--count 25]

Omit --password and you'll be prompted without echo.
"""

import argparse
import getpass
import sys

from sqlalchemy import select

from app.auth import hash_password
from app.db import SessionLocal
from app.models import Customer, User


def cmd_createuser(args: argparse.Namespace) -> int:
    username = args.username or input("Username: ").strip()
    email = args.email or input("Email: ").strip()
    password = args.password

    if not password:
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Confirm password: "):
            print("Passwords do not match.", file=sys.stderr)
            return 1

    if len(password) < 8:
        print("Password must be at least 8 characters.", file=sys.stderr)
        return 1

    with SessionLocal() as db:
        clash = db.scalar(
            select(User).where((User.username == username) | (User.email == email))
        )
        if clash is not None:
            print(f"A user with that username or email already exists (id={clash.id}).",
                  file=sys.stderr)
            return 1

        user = User(username=username, email=email, hashed_password=hash_password(password))
        db.add(user)
        db.commit()
        print(f"Created user {user.username!r} (id={user.id}).")
    return 0


def cmd_listusers(_args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        users = list(db.scalars(select(User).order_by(User.id)))
        if not users:
            print("No users yet. Run: python manage.py createuser")
            return 0
        for u in users:
            state = "active" if u.is_active else "disabled"
            print(f"{u.id:>4}  {u.username:<20} {u.email:<30} {state}")
    return 0


def cmd_seed(args: argparse.Namespace) -> int:
    """Insert sample customers so the UI has something to show."""
    firsts = ["Ada", "Grace", "Alan", "Katherine", "Linus", "Barbara", "Edsger",
              "Margaret", "Donald", "Radia", "Ken", "Frances"]
    lasts = ["Lovelace", "Hopper", "Turing", "Johnson", "Torvalds", "Liskov",
             "Dijkstra", "Hamilton", "Knuth", "Perlman", "Thompson", "Allen"]
    companies = ["Northwind Ltd", "Acme Industrial", "Contoso", "Initech",
                 "Globex", "Umbrella Supply", None]

    created = 0
    with SessionLocal() as db:
        for i in range(args.count):
            first = firsts[i % len(firsts)]
            last = lasts[(i * 5) % len(lasts)]
            email = f"{first.lower()}.{last.lower()}{i}@example.com"
            if db.scalar(select(Customer).where(Customer.email == email)):
                continue
            db.add(Customer(
                first_name=first,
                last_name=last,
                email=email,
                phone=f"+1 555 {1000 + i:04d}",
                company=companies[i % len(companies)],
                city=["Boston", "Austin", "Seattle", "Denver"][i % 4],
                country="USA",
                is_active=(i % 7 != 0),
            ))
            created += 1
        db.commit()
    print(f"Seeded {created} customer(s).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Customer Database admin commands")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("createuser", help="Create a staff login")
    p.add_argument("--username")
    p.add_argument("--email")
    p.add_argument("--password", help="Prompted for if omitted")
    p.set_defaults(func=cmd_createuser)

    p = sub.add_parser("listusers", help="List staff logins")
    p.set_defaults(func=cmd_listusers)

    p = sub.add_parser("seed", help="Insert sample customers")
    p.add_argument("--count", type=int, default=25)
    p.set_defaults(func=cmd_seed)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
