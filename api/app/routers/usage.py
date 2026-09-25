"""Usage + plans."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.models.usage_event import UsageEvent
from app.schemas.common import OkEnvelope
from app.schemas.usage import PlanOut, UsageCounter, UsageOut
from app.services.plan_service import list_plans


router = APIRouter(tags=["usage-plans"])


EVENT_LABELS = {
    UsageEvent.TYPE_UPLOAD: "uploads",
    UsageEvent.TYPE_API_REQUEST: "api_requests",
    UsageEvent.TYPE_DELETE: "deletes",
    UsageEvent.TYPE_FAILED_UPLOAD: "failed_uploads",
    UsageEvent.TYPE_IMAGE_EXPIRED: "image_expired",
}


@router.get("/usage", response_model=OkEnvelope[UsageOut])
def usage(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> OkEnvelope[UsageOut]:
    rows = db.execute(
        select(UsageEvent.event_type, func.count(UsageEvent.id), func.coalesce(func.sum(UsageEvent.bytes), 0))
        .where(UsageEvent.user_id == current.id)
        .group_by(UsageEvent.event_type)
    ).all()
    counters = []
    for et, count, total_bytes in rows:
        counters.append(
            UsageCounter(
                event_type=et,
                event_type_label=EVENT_LABELS.get(et, f"event_{et}"),
                count=count,
                bytes_total=total_bytes or 0,
            )
        )
    counters.sort(key=lambda c: c.event_type)
    return OkEnvelope(
        data=UsageOut(
            counters=counters,
            upload_credits_remaining=current.upload_credits,
            plan_name=current.plan.name,
        )
    )


@router.get("/plans", response_model=OkEnvelope[list[PlanOut]])
def plans_list(db: Session = Depends(get_db)) -> OkEnvelope[list[PlanOut]]:
    rows = list(list_plans(db))
    return OkEnvelope(data=[PlanOut.model_validate(p) for p in rows])