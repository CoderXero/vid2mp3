import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from audioharbor.adapters.yt_dlp_adapter import YtDlpAdapter
from audioharbor.config import Settings
from audioharbor.db.models import Attempt, JobEntry, MediaTask, Output, now
from audioharbor.db.repositories import emit
from audioharbor.domain.errors import AudioHarborError
from audioharbor.media.conversion import convert_to_mp3, verify_mp3
from audioharbor.media.filename import output_name


def _unique(root: Path, relative: Path) -> Path:
    candidate = root / relative
    if not candidate.exists(): return candidate
    for i in range(2, 10000):
        p = candidate.with_name(f"{candidate.stem} ({i}){candidate.suffix}")
        if not p.exists(): return p
    raise AudioHarborError("OUTPUT_PERMISSION_DENIED", "Could not reserve an output filename.")


def process_task(db: Session, task: MediaTask, job_options: dict, settings: Settings, job_id: str) -> None:
    staging_root = settings.storage.output_dir / ".audioharbor-tmp" / task.id
    staging_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    attempt = Attempt(task_id=task.id, phase="transfer", number=task.attempt_count, started_at=now()); db.add(attempt)
    try:
        entry = db.scalar(select(JobEntry).where(JobEntry.task_id == task.id, JobEntry.job_id == job_id))
        info = YtDlpAdapter(settings.worker.socket_timeout_seconds).resolve_media(entry.source_id or task.media_id)
        task.state = "downloading"; db.commit()
        source = staging_root / "source"
        cmd = ["yt-dlp", "--ignore-config", "--no-playlist", "--no-part", "--no-progress", "-f", "bestaudio/best", "--max-filesize", str(settings.limits.source_bytes), "-o", str(source), entry.source_id or task.media_id]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=7200, check=False, env={"PATH": os.environ.get("PATH", ""), "PYTHONNOUSERSITE": "1"})
        if p.returncode: raise AudioHarborError("TRANSIENT_NETWORK", "The media download failed.", True)
        actual = next((x for x in staging_root.iterdir() if x.name.startswith("source")), source)
        if not actual.exists(): raise AudioHarborError("INVALID_SOURCE", "No media was downloaded.")
        task.state = "converting"; db.commit()
        title = info.get("title") or entry.display_title
        playlist = info.get("playlist_title")
        target_relative = output_name(title, task.service, task.media_id, playlist, info.get("playlist_index"))
        mp3 = staging_root / "final.mp3"; convert_to_mp3(actual, mp3, job_options); task.state = "verifying"; db.commit()
        size, duration = verify_mp3(mp3)
        final = _unique(settings.storage.output_dir, target_relative); final.parent.mkdir(parents=True, exist_ok=True)
        os.replace(mp3, final)
        digest = hashlib.sha256(final.read_bytes()).hexdigest()
        output = Output(service=task.service, media_id=task.media_id, profile_hash=task.profile_hash, generation=task.generation, relative_path=str(final.relative_to(settings.storage.output_dir)), sha256=digest, size_bytes=size, duration_seconds=duration)
        db.add(output); db.flush(); task.output_id = output.id; task.state = "succeeded"; attempt.ended_at = now(); emit(db, job_id, "output_published", {"task_id": task.id, "path": output.relative_path}); db.commit()
    except AudioHarborError as e:
        task.state = "failed"; attempt.error_code = e.code; attempt.sanitized_message = e.message; attempt.retryable = e.retryable; attempt.ended_at = now(); db.commit()
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)

