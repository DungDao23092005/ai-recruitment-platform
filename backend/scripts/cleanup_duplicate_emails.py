"""Duplicate email cleanup script.

This script identifies and anonymizes ghost duplicate users:
- Users with is_deleted=true whose email is also owned by an is_deleted=false user
- Only confirmed ghost duplicates are affected
- The non-deleted (active) account keeps the original email
- The deleted (ghost) account gets anonymized email: deleted_{uuid}@anonymized.local

Usage:
    python backend/scripts/cleanup_duplicate_emails.py          # Dry run
    python backend/scripts/cleanup_duplicate_emails.py --apply  # Perform anonymization
"""

import argparse
import sys
import uuid
from typing import List, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.user import User
from app.database.session import async_session_factory
from app.core.config import settings


async def find_duplicate_ghost_users(session: AsyncSession) -> List[Tuple[User, User]]:
    """Find ghost duplicate users where:
    - One user has is_deleted=True (ghost)
    - Another user has the same email with is_deleted=False (active)

    Returns list of (ghost_user, active_user) tuples.
    """
    # Find all emails that have both deleted and non-deleted users
    stmt = select(User.email).where(
        User.is_deleted == False  # noqa: E712
    ).distinct()
    result = await session.execute(stmt)
    active_emails = {row[0] for row in result.all()}

    ghost_users = []
    for email in active_emails:
        # Find ghost users with this email
        stmt = select(User).where(
            User.email == email,
            User.is_deleted == True  # noqa: E712
        )
        result = await session.execute(stmt)
        ghosts = result.scalars().all()

        # Find the active user
        stmt = select(User).where(
            User.email == email,
            User.is_deleted == False  # noqa: E712
        )
        result = await session.execute(stmt)
        active_user = result.scalar_one_or_none()

        if active_user:
            for ghost in ghosts:
                ghost_users.append((ghost, active_user))

    return ghost_users


async def anonymize_ghost_user(session: AsyncSession, ghost_user: User) -> None:
    """Anonymize a ghost user's email."""
    ghost_user.email = f"deleted_{ghost_user.id}@anonymized.local"
    # Ensure is_deleted is still True
    ghost_user.is_deleted = True
    await session.commit()
    await session.refresh(ghost_user)


async def dry_run() -> int:
    """Perform a dry run - print what would be done without modifying."""
    async with async_session_factory() as session:
        ghost_users = await find_duplicate_ghost_users(session)

        if not ghost_users:
            print("No ghost duplicate users found.")
            return 0

        print(f"Found {len(ghost_users)} ghost duplicate user(s) to anonymize:")
        print()
        for ghost_user, active_user in ghost_users:
            print(f"  Ghost User ID: {ghost_user.id}")
            print(f"  Ghost User Email: {ghost_user.email}")
            print(f"  Active User ID: {active_user.id}")
            print(f"  Active User Email: {active_user.email}")
            print(f"  Will anonymize ghost to: deleted_{ghost_user.id}@anonymized.local")
            print()

        return len(ghost_users)


async def apply_changes() -> int:
    """Apply the anonymization changes."""
    async with async_session_factory() as session:
        ghost_users = await find_duplicate_ghost_users(session)

        if not ghost_users:
            print("No ghost duplicate users found.")
            return 0

        print(f"Anonymizing {len(ghost_users)} ghost duplicate user(s)...")
        print()

        for ghost_user, active_user in ghost_users:
            print(f"  Anonymizing ghost user {ghost_user.id} ({ghost_user.email})")
            print(f"    Active user: {active_user.id} ({active_user.email})")
            await anonymize_ghost_user(session, ghost_user)
            print(f"    -> Anonymized to: deleted_{ghost_user.id}@anonymized.local")
            print()

        print(f"Successfully anonymized {len(ghost_users)} ghost duplicate user(s).")
        return len(ghost_users)


def main():
    parser = argparse.ArgumentParser(
        description="Cleanup duplicate email ghost users",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python backend/scripts/cleanup_duplicate_emails.py
      Run in dry-run mode (no changes made)

  python backend/scripts/cleanup_duplicate_emails.py --apply
      Apply anonymization changes to ghost duplicate users
"""
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes (default is dry-run)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    try:
        if args.apply:
            count = asyncio.run(apply_changes())
            print(f"\nSuccessfully processed {count} ghost duplicate user(s).")
        else:
            count = asyncio.run(dry_run())
            print(f"\nDry run complete. {count} ghost duplicate user(s) would be anonymized.")
            print("Run with --apply to apply changes.")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    import asyncio
    main()
