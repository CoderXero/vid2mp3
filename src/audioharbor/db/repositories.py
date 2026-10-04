from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Event, Job, JobEntry, MediaTask


def emit(db: Session, job_id: str, event_type: str, payload: dict) -> Event:
    e = Event(job_id=job_id, event_type=event_type, payload_json=payload); db.add(e); return e


def job_counts(db: Session, job_id: str) -> dict:
    rows = db.scalars(select(JobEntry).where(JobEntry.job_id == job_id)).all()
    counts = {"discovered": 0, "selected": 0, "completed": 0, "failed": 0, "skipped": 0}
    for r in rows:
        counts["discovered"] += 1; counts["selected"] += int(r.selected)
        if r.occurrence_status == "succeeded": counts["completed"] += 1
        if r.occurrence_status in ("failed", "unavailable"): counts["failed"] += 1
        if r.occurrence_status == "skipped": counts["skipped"] += 1
    return counts


def derive_job_state(db: Session, job: Job) -> str:
    rows = db.scalars(select(JobEntry).where(JobEntry.job_id == job.id, JobEntry.selected.is_(True))).all()
    if job.cancel_requested: return "cancelled"
    if job.pause_requested: return "paused"
    if not job.discovery_complete: return job.state
    if not rows: return "completed"
    states = {r.task.state if r.task else r.occurrence_status for r in rows}
    if states & {"downloading", "converting", "resolving", "verifying", "queued"}: return "running"
    if states <= {"succeeded", "skipped"}: return "completed"
    if states & {"waiting_auth", "waiting_retry", "waiting_user"}: return "waiting_user"
    return "completed_with_errors"


def claim_task(db: Session, owner: str, lease_seconds: int = 60):
    now_utc = datetime.now(UTC)
    task = db.scalar(select(MediaTask).where(MediaTask.state == "queued", (MediaTask.next_attempt_at.is_(None)) | (MediaTask.next_attempt_at <= now_utc)).with_for_update().limit(1))
    if not task: return None
    task.lease_owner = owner; task.lease_until = datetime.fromtimestamp(now_utc.timestamp() + lease_seconds, UTC); task.heartbeat_at = now_utc
    task.state = "resolving"; task.attempt_count += 1; db.commit(); return task

