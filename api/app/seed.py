"""Create a demo account so the app can be tried without registering.

    python -m app.seed

Idempotent: running it twice resets the demo password rather than failing, so
it is safe to call from a setup script.
"""

from __future__ import annotations

import asyncio
import os

from sqlalchemy import select

from app.db import SessionFactory, create_all
from app.models import User
from app.security import hash_password

DEMO_EMAIL = os.getenv("DEMO_EMAIL", "demo@recall.study")
DEMO_NAME = os.getenv("DEMO_NAME", "Demo Student")

# Deliberately a known, weak-but-long value: this account exists to be shared.
# It is 12+ characters so it satisfies the same rule as any other account —
# seeding a row that the registration endpoint would have rejected is how a
# fixture stops representing reality.
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "study-out-loud-2026")


async def seed() -> None:
    await create_all()

    async with SessionFactory() as db:
        user = await db.scalar(select(User).where(User.email == DEMO_EMAIL))

        if user is None:
            user = User(
                email=DEMO_EMAIL,
                display_name=DEMO_NAME,
                password_hash=hash_password(DEMO_PASSWORD),
            )
            db.add(user)
            action = "created"
        else:
            user.password_hash = hash_password(DEMO_PASSWORD)
            action = "password reset"

        await db.commit()

    print(f"demo account {action}:")
    print(f"  email    {DEMO_EMAIL}")
    print(f"  password {DEMO_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(seed())
