"""APScheduler-based cleanup runner.

Deletes from disk + marks DB row deleted for any image whose expires_at is in
the past and which has not yet been soft-deleted. Runs every `WORKER_INTERVAL_MINUTES`
minutes (default 60). Processes in batches of `WORKER_BATCH_SIZE` (default 100).

Invoked by the `worker` container via:
    python -m app.tasks.cleanup_runner
"""
from __future__ import annotations

import logging
import signal
import sys
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy import select

from app.config import get_settings
from app.database import session_scope
from app.models.image import Image
from app.models.usage_event import UsageEvent
from app.services.storage import get_storage


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [cleanup] %(message)s")
log = logging.getLogger("cleanup")

# Print to stdout immediately so docker logs shows our startup even if logging
# misconfigures for any reason.
print("[cleanup] worker process starting", flush=True)


def cleanup_once() -> int:
    """One pass. Returns number of images cleaned up."""
    settings = get_settings()
    storage = get_storage()
    cleaned = 0
    batch = settings.worker_batch_size

    with session_scope() as db:
        now = datetime.utcnow()
        rows = db.execute(
            select(Image.id, Image.storage_key, Image.size_bytes, Image.user_id)
            .where(Image.expires_at <= now, Image.deleted_at.is_(None))
            .order_by(Image.id.asc())
            .limit(batch)
        ).all()
        if not rows:
            return 0
        ids = [r[0] for r in rows]
        # Soft-delete in bulk
        db.query(Image).filter(Image.id.in_(ids)).update(
            {Image.deleted_at: now}, synchronize_session=False
        )
        # Audit rows
        for image_id, storage_key, size_bytes, user_id in rows:
            db.add(
                UsageEvent(
                    user_id=user_id,
                    event_type=UsageEvent.TYPE_IMAGE_EXPIRED,
                    bytes=size_bytes or 0,
                    metadata_json={"image_id": image_id, "storage_key": storage_key},
                )
            )
        log.info("soft-deleted %d expired image rows", len(ids))

    # Disk cleanup happens after commit (we don't want to lose the file if
    # the DB transaction fails).
    ext_guesses = ("jpg", "jpeg", "png", "gif", "webp")
    for _image_id, storage_key, _size, _uid in rows:
        for ext in ext_guesses:
            try:
                if storage.exists(storage_key, ext):
                    storage.delete(storage_key, ext)
                    cleaned += 1
                    break
            except Exception as exc:  # noqa: BLE001
                log.warning("failed to delete %s.%s: %s", storage_key, ext, exc)
    log.info("removed %d files from disk", cleaned)
    return cleaned


def main() -> None:
    settings = get_settings()
    print(f"[cleanup] settings ok, interval={settings.worker_interval_minutes}min batch={settings.worker_batch_size}", flush=True)
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        cleanup_once,
        trigger="interval",
        minutes=settings.worker_interval_minutes,
        id="cleanup",
        max_instances=1,
        coalesce=True,
    )
    log.info(
        "scheduler started: cleanup every %d min, batch %d",
        settings.worker_interval_minutes,
        settings.worker_batch_size,
    )
    print("[cleanup] scheduler configured, entering main loop", flush=True)

    def _shutdown(signum, _frame):
        log.info("received signal %s, shutting down", signum)
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # Run once at start, then continue with the interval.
    try:
        cleanup_once()
    except Exception as exc:  # noqa: BLE001
        log.exception("initial cleanup failed: %s", exc)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()