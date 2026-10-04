import socket
import time

from sqlalchemy import select

from audioharbor.config import Settings
from audioharbor.db.models import Job, JobEntry, SessionLocal
from audioharbor.db.repositories import claim_task, derive_job_state

from .pipeline import process_task


def run_worker(settings: Settings) -> None:
    owner = f"{socket.gethostname()}:{__import__('os').getpid()}"; settings.prepare()
    while True:
        with SessionLocal() as db:
            task = claim_task(db, owner)
            if task:
                entry_job = db.scalar(select(Job).join(JobEntry, JobEntry.job_id == Job.id).where(JobEntry.task_id == task.id))
                if entry_job: process_task(db, task, entry_job.options_json, settings, entry_job.id); entry_job.state = derive_job_state(db, entry_job); db.commit()
            else: time.sleep(1)
