"""Admin script for users. Run on a machine that has SUPABASE_DB_URL; there is deliberately no HTTP endpoint.

  python -m app.auth.manage create-user --email pm@example.com --name "Pat Manager" [--role pm|admin]
  python -m app.auth.manage set-password --email pm@example.com
  python -m app.auth.manage deactivate --email pm@example.com      (also: activate)
  python -m app.auth.manage list-users

Passwords are typed at a hidden prompt, never passed as arguments (they would land in shell history).
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys

import psycopg
from psycopg.rows import dict_row

from app.auth import service
from app.config import load_env


def ask_password() -> str:
    first = getpass.getpass("Password (at least 12 characters): ")
    if first != getpass.getpass("Repeat password: "):
        sys.exit("The passwords do not match.")
    return first


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-user")
    c.add_argument("--email", required=True)
    c.add_argument("--name", required=True)
    c.add_argument("--role", default="pm", choices=["pm", "admin"])
    for name in ("set-password", "deactivate", "activate"):
        sub.add_parser(name).add_argument("--email", required=True)
    sub.add_parser("list-users")
    args = ap.parse_args(argv)

    load_env()
    if not os.environ.get("SUPABASE_DB_URL"):
        sys.exit("SUPABASE_DB_URL is not set in .env")
    conn = psycopg.connect(os.environ["SUPABASE_DB_URL"], row_factory=dict_row, autocommit=True)
    try:
        if args.cmd == "create-user":
            user = service.create_user(conn, args.email, args.name, ask_password(), args.role)
            print(f"Created {user['role']} {user['email']}")
        elif args.cmd == "set-password":
            service.set_password(conn, args.email, ask_password())
            print("Password changed; the user's sessions were signed out.")
        elif args.cmd in ("deactivate", "activate"):
            service.set_active(conn, args.email, args.cmd == "activate")
            print(f"{args.cmd.capitalize()}d {args.email}")
        else:
            for u in service.list_users(conn):
                state = "active" if u["active"] else "INACTIVE"
                last = u["last_login_at"].strftime("%Y-%m-%d %H:%M") if u["last_login_at"] else "never"
                print(f"{u['email']:<36} {u['role']:<6} {state:<9} last login {last}  {u['display_name']}")
    except ValueError as e:
        sys.exit(str(e))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
