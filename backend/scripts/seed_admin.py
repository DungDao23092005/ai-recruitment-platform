#!/usr/bin/env python
"""
Development admin account seeder.

Creates the development admin account through the project's existing
ORM/repository/security infrastructure. This script is idempotent and safe.

Usage:
    python -m scripts.seed_admin

Environment:
    Requires DATABASE_URL to be set (uses app.core.config.settings)
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.config import settings
from app.core.security import get_password_hash
from app.database.session import async_session_factory
from app.domain.enums import UserRole
from app.models import User


ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "Password123!"


async def seed_admin() -> None:
    """Create the development admin account if it doesn't exist."""
    print(f"Connecting to database: {settings.database_uri.split('@')[-1] if '@' in settings.database_uri else settings.database_uri}")

    async with async_session_factory() as session:
        # Check if admin user already exists
        result = await session.execute(
            select(User).where(User.email == ADMIN_EMAIL)
        )
        existing_user = result.scalars().first()

        if existing_user:
            if existing_user.role == UserRole.ADMIN:
                print(f"[OK] Admin user already exists: {ADMIN_EMAIL} (role: admin)")
                return
            else:
                # CASE C: admin@example.com exists with non-admin role
                raise RuntimeError(
                    f"Conflict: User {ADMIN_EMAIL} already exists with role '{existing_user.role.value}'. "
                    "Cannot promote existing non-admin user to admin. "
                    "Resolve the conflict manually before seeding."
                )

        # CASE A: Create new admin user
        admin_user = User(
            email=ADMIN_EMAIL,
            password_hash=get_password_hash(ADMIN_PASSWORD),
            role=UserRole.ADMIN,
            is_active=True,
        )
        session.add(admin_user)
        await session.commit()
        await session.refresh(admin_user)

        print(f"[OK] Created admin user: {ADMIN_EMAIL} (role: admin, id: {admin_user.id})")


def main() -> None:
    """Entry point for the seeder script."""
    print("=" * 60)
    print("Development Admin Seeder")
    print("=" * 60)

    try:
        asyncio.run(seed_admin())
        print("=" * 60)
        print("Seeding completed successfully.")
        print("=" * 60)
    except RuntimeError as e:
        print("=" * 60)
        print(f"Seeding failed: {e}")
        print("=" * 60)
        raise SystemExit(1) from e
    except Exception as e:
        print("=" * 60)
        print(f"Unexpected error during seeding: {e}")
        print("=" * 60)
        raise


if __name__ == "__main__":
    main()