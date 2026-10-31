"""Reset (or create) a password admin: `uv run admin-password --email you@example.com`.
Run from an admin machine with the prod DATABASE_URL, like sync-config. The password is read from a
prompt (getpass) so it never lands in shell history."""

import argparse
import getpass
import sys

from sqlalchemy.orm import sessionmaker

from questtour.auth.passwords import (
    MIN_PASSWORD_LENGTH,
    find_admin,
    hash_password,
    normalize_email,
)
from questtour.db import make_engine
from questtour.models import AdminUser
from questtour.settings import get_settings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="admin-password")
    ap.add_argument("--email", required=True)
    args = ap.parse_args(argv)
    pw = getpass.getpass("New password: ")
    if len(pw) < MIN_PASSWORD_LENGTH or pw != getpass.getpass("Repeat: "):
        print(f"passwords differ or shorter than {MIN_PASSWORD_LENGTH} characters", file=sys.stderr)
        return 1
    with sessionmaker(make_engine(get_settings()), expire_on_commit=False)() as db:
        user = find_admin(db, args.email)
        if user is None:
            db.add(AdminUser(email=normalize_email(args.email), password_hash=hash_password(pw)))
        else:
            user.password_hash = hash_password(pw)
        db.commit()
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
