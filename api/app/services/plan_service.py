"""Plan service — read plans, compute expiry from retention."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError, ErrorCode
from app.models.plan import Plan


def list_plans(db: Session) -> Iterable[Plan]:
    return db.scalars(select(Plan).order_by(Plan.sort_order.asc(), Plan.id.asc())).all()


def get_plan(db: Session, plan_id: int) -> Plan:
    plan = db.get(Plan, plan_id)
    if not plan:
        raise AppError(ErrorCode.NOT_FOUND if False else "PLAN_NOT_FOUND", "Plan not found")
    return plan


def get_plan_by_name(db: Session, name: str) -> Plan | None:
    return db.scalar(select(Plan).where(Plan.name == name))


def compute_expires_at(created_at: datetime, plan: Plan) -> datetime:
    from datetime import timedelta
    return created_at + timedelta(days=plan.retention_days)