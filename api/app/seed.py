"""Idempotent seed script.

Populates 3 plans (Free / Basic / Pro) and a demo user (Free, 20 credits).
Optionally writes a couple of placeholder Image rows so the dashboard isn't
empty on first visit (these are NOT actual files on disk).

Run via: `python -m app.seed`
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from app.config import get_settings
from app.database import session_scope
from app.models.config import Config
from app.models.plan import Plan
from app.models.user import User
from app.models.upload_credit import UploadCreditTransaction
from app.security import hash_password

log = logging.getLogger("seed")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


PLANS_SEED = [
    {
        "name": "Free",
        "price_xu": 0,
        "initial_uploads": 20,
        "retention_days": 3,
        "image_quality": Plan.QUALITY_OPTIMIZED if hasattr(Plan, "QUALITY_OPTIMIZED") else 0,
        "sort_order": 0,
    },
    {
        "name": "Basic",
        "price_xu": 100000 * 100,  # 100000 VND = 10_000_000 xu
        "initial_uploads": 200,
        "retention_days": 10,
        "image_quality": 0,
        "sort_order": 1,
    },
    {
        "name": "Pro",
        "price_xu": 500000 * 100,  # 500000 VND = 50_000_000 xu
        "initial_uploads": 1000,
        "retention_days": 30,
        "image_quality": 1,
        "sort_order": 2,
    },
]


def seed_plans() -> dict[str, int]:
    """Insert plans if missing. Returns mapping name -> id."""
    name_to_id: dict[str, int] = {}
    with session_scope() as db:
        for spec in PLANS_SEED:
            existing = db.scalar(select(Plan).where(Plan.name == spec["name"]))
            if existing:
                name_to_id[spec["name"]] = existing.id
                continue
            plan = Plan(
                name=spec["name"],
                price=spec["price_xu"],
                initial_uploads=spec["initial_uploads"],
                retention_days=spec["retention_days"],
                image_quality=spec["image_quality"],
                sort_order=spec["sort_order"],
            )
            db.add(plan)
            db.flush()
            name_to_id[spec["name"]] = plan.id
            log.info("seeded plan %s (id=%s)", plan.name, plan.id)
    return name_to_id


def seed_demo_user(plan_id: int) -> int:
    settings = get_settings()
    with session_scope() as db:
        existing = db.scalar(select(User).where(User.email == settings.demo_user_email.lower()))
        if existing:
            log.info("demo user already exists (id=%s)", existing.id)
            return existing.id
        user = User(
            email=settings.demo_user_email.lower(),
            password_hash=hash_password(settings.demo_user_password),
            name=settings.demo_user_name,
            plan_id=plan_id,
            upload_credits=20,
        )
        db.add(user)
        db.flush()
        # Audit row for the initial grant
        db.add(
            UploadCreditTransaction(
                user_id=user.id,
                type=UploadCreditTransaction.TYPE_PLAN_GRANT,
                amount=20,
                balance_after=20,
                reference_type="plan",
                reference_id=plan_id,
            )
        )
        log.info("seeded demo user %s (id=%s)", user.email, user.id)
        return user.id


def main() -> None:
    plan_ids = seed_plans()
    demo_user_id = seed_demo_user(plan_ids["Free"])
    seed_sepay_config()
    log.info(
        "seed complete. plans=%s demo_user_id=%s",
        {n: i for n, i in plan_ids.items()},
        demo_user_id,
    )


def seed_sepay_config() -> None:
    """Insert placeholder SePay settings vào bảng ``configs`` nếu chưa có.

    Đây là **single source of truth** cho mọi tham số SePay — KHÔNG đọc env.
    Production: UPDATE trực tiếp các row này trong DB (qua Adminer / SQL client)
    thay vì restart container.

    Seed chạy idempotent — chỉ insert nếu chưa có, không ghi đè giá trị user đã sửa.
    """
    defaults = [
        (Config.KEY_SEPAY_BANK, "MBBank", "Mã ngân hàng nhận tiền (theo SePay QR)."),
        (Config.KEY_SEPAY_ACCOUNT, "0000000000", "Số tài khoản nhận tiền — CẦN thay giá trị thật trước khi lên prod."),
        (Config.KEY_SEPAY_ACCOUNT_NAME, "NGUYEN VAN A", "Tên chủ tài khoản nhận tiền."),
        (Config.KEY_SEPAY_TEMPLATE, "compact", "Template QR VietQR: compact | print | qr_only."),
        (Config.KEY_SEPAY_QR_TTL_MINUTES, "15", "Thời gian QR hết hạn (phút)."),
        (Config.KEY_SEPAY_STORE, "", "Tên cửa hàng hiển thị trên VietQR (query param ``store``). Để trống = không gửi."),
        (Config.KEY_SEPAY_WEBHOOK_API_KEY, "", "API key cho header Authorization: Apikey <key>. Để trống = tắt phương thức này."),
        (Config.KEY_SEPAY_WEBHOOK_SECRET, "", "HMAC secret cho header X-SePay-Signature. Để trống = tắt phương thức này."),
    ]
    with session_scope() as db:
        for key, value, desc in defaults:
            existing = db.get(Config, key)
            if existing:
                continue
            db.add(Config(config_key=key, config_value=value, description=desc))
            log.info("seeded config %s = %r", key, value)


if __name__ == "__main__":
    main()