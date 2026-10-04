import asyncio
import json
import os
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from audioharbor.adapters.yt_dlp_adapter import YtDlpAdapter
from audioharbor.config import Settings
from audioharbor.db.models import (
    Base,
    Collection,
    Job,
    JobEntry,
    MediaTask,
    Output,
    SessionLocal,
    engine,
)
from audioharbor.db.repositories import derive_job_state, emit, job_counts
from audioharbor.domain.profiles import profile_hash
from audioharbor.security.urls import validate_url

from .schemas import JobCreate, RetryRequest, StartRequest


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.load(); settings.prepare(); Base.metadata.create_all(engine)
    app = FastAPI(title="AudioHarbor", version="0.1.0")
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

    @app.middleware("http")
    async def security(request: Request, call_next):
        if request.url.path.startswith("/api") and request.headers.get("host", "").split(":")[0] not in {"127.0.0.1", "localhost"}:
            raise HTTPException(400, "Invalid Host")
        response = await call_next(request); response.headers["Content-Security-Policy"] = "default-src 'self'; connect-src 'self'; style-src 'self' 'unsafe-inline'"; response.headers["X-Content-Type-Options"] = "nosniff"; response.headers["X-Frame-Options"] = "DENY"; return response

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request): return templates.TemplateResponse(request=request, name="index.html", context={})

    @app.get("/api/v1/health/live")
    async def live(): return {"status": "ok"}

    @app.get("/api/v1/health/ready")
    async def ready(): return {"status": "ready", "dependencies": __import__('audioharbor.media.conversion', fromlist=['check_programs']).check_programs()}

    @app.post("/api/v1/jobs", status_code=202)
    async def create_job(body: JobCreate):
        try: redacted, service = validate_url(body.url)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(422, str(e))
        options = body.model_dump(); options["profile_hash"] = profile_hash(options)
        with SessionLocal() as db:
            job = Job(input_url_redacted=redacted, canonical_source=redacted, service=service, options_json=options, state="discovering"); db.add(job); db.flush(); emit(db, job.id, "job_created", {"url": redacted}); db.commit(); job_id = job.id
        asyncio.create_task(discover(job_id, body.url, body.playlist_mode, settings))
        return {"id": job_id, "state": "discovering"}

    async def discover(job_id: str, url: str, playlist_mode: str, settings: Settings):
        try: result = await asyncio.to_thread(YtDlpAdapter().discover, url, playlist_mode)
        except Exception as e:  # noqa: BLE001
            with SessionLocal() as db: job = db.get(Job, job_id); job.state = "failed"; job.discovery_complete = True; emit(db, job_id, "discovery_failed", {"message": str(e)}); db.commit()
            return
        with SessionLocal() as db:
            job = db.get(Job, job_id); collection = Collection(job_id=job_id, service=job.service, collection_key=result.get("id") or job_id, title=result.get("title") or "Playlist"); db.add(collection); db.flush()
            for item in result["entries"][:settings.limits.playlist_entries]:
                task = None
                if item.get("id"):
                    task = db.scalar(select(MediaTask).where(MediaTask.service == job.service, MediaTask.media_id == item["id"], MediaTask.profile_hash == job.options_json["profile_hash"], MediaTask.generation == 1))
                    if not task: task = MediaTask(service=job.service, media_id=item["id"], profile_hash=job.options_json["profile_hash"], state="discovered", metadata_json=item); db.add(task); db.flush()
                db.add(JobEntry(job_id=job_id, collection_id=collection.id, index_path=item["index_path"], source_id=item.get("url") or item.get("id"), task_id=task.id if task else None, display_title=item["title"], occurrence_status="discovered" if task else "failed"))
            job.discovery_complete = True; job.state = "awaiting_selection" if result.get("is_playlist") else "running"; emit(db, job_id, "discovery_complete", {"count": len(result["entries"])}); db.commit()
            if not result.get("is_playlist"): start_entries(db, job)

    def start_entries(db, job, ids=None):
        for entry in db.scalars(select(JobEntry).where(JobEntry.job_id == job.id)).all():
            if ids and entry.id not in ids: continue
            if entry.task and entry.selected: entry.task.state = "queued"; entry.occurrence_status = "queued"
        job.state = "running"; db.commit()

    @app.get("/api/v1/jobs")
    async def list_jobs():
        with SessionLocal() as db: return [{"id": j.id, "state": derive_job_state(db, j), "url": j.input_url_redacted, "counts": job_counts(db, j.id)} for j in db.scalars(select(Job).order_by(Job.created_at.desc())).all()]

    @app.get("/api/v1/jobs/{job_id}")
    async def get_job(job_id: str):
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if not job: raise HTTPException(404, "Unknown job")
            return {"id": job.id, "state": derive_job_state(db, job), "url": job.input_url_redacted, "options": job.options_json, "counts": job_counts(db, job.id), "version": job.version}

    @app.get("/api/v1/jobs/{job_id}/entries")
    async def entries(job_id: str):
        with SessionLocal() as db: return [{"id": e.id, "title": e.display_title, "index_path": e.index_path, "state": e.task.state if e.task else e.occurrence_status, "selected": e.selected} for e in db.scalars(select(JobEntry).where(JobEntry.job_id == job_id).order_by(JobEntry.index_path)).all()]

    @app.post("/api/v1/jobs/{job_id}/start")
    async def start(job_id: str, body: StartRequest | None = None):
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if not job or not job.discovery_complete: raise HTTPException(409, "Discovery is not complete")
            start_entries(db, job, body.entry_ids if body else None); return {"id": job.id, "state": job.state}

    @app.post("/api/v1/jobs/{job_id}/pause")
    async def pause(job_id: str):
        with SessionLocal() as db: job = db.get(Job, job_id); job.pause_requested = True; db.commit(); return {"state": "paused"}

    @app.post("/api/v1/jobs/{job_id}/resume")
    async def resume(job_id: str):
        with SessionLocal() as db: job = db.get(Job, job_id); job.pause_requested = False; job.cancel_requested = False; start_entries(db, job); return {"state": job.state}

    @app.post("/api/v1/jobs/{job_id}/cancel")
    async def cancel(job_id: str):
        with SessionLocal() as db: job = db.get(Job, job_id); job.cancel_requested = True; job.state = "cancelled"; db.commit(); return {"state": "cancelled"}

    @app.post("/api/v1/jobs/{job_id}/retry")
    async def retry(job_id: str, body: RetryRequest | None = None):
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if not job: raise HTTPException(404, "Unknown job")
            for entry in db.scalars(select(JobEntry).where(JobEntry.job_id == job_id)).all():
                if (body is None or body.entry_ids is None or entry.id in body.entry_ids) and entry.task and entry.task.state in {"failed", "cancelled"}:
                    entry.task.state = "queued"; entry.occurrence_status = "queued"
            job.cancel_requested = False; job.pause_requested = False; job.state = "running"; db.commit(); return {"state": job.state}

    @app.delete("/api/v1/jobs/{job_id}")
    async def delete_job(job_id: str):
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if not job: raise HTTPException(404, "Unknown job")
            if derive_job_state(db, job) in {"running", "discovering", "paused", "waiting_auth", "waiting_retry"}: raise HTTPException(409, "Active jobs cannot be removed")
            db.delete(job); db.commit(); return {"deleted": True}

    @app.get("/api/v1/settings")
    async def settings_info():
        return {"output_dir": str(settings.storage.output_dir), "limits": settings.limits.model_dump(), "worker": settings.worker.model_dump(), "supported_hosts": ["youtube.com", "youtu.be"]}

    @app.get("/api/v1/diagnostics")
    async def diagnostics():
        from shutil import disk_usage

        from audioharbor.media.conversion import check_programs
        usage = disk_usage(settings.storage.output_dir)
        return {"dependencies": check_programs(), "output_writable": os.access(settings.storage.output_dir, os.W_OK), "free_bytes": usage.free, "python": __import__('sys').version}

    @app.post("/api/v1/auth-sessions")
    async def auth_session(service: str = Form(...), method: str = Form(...), cookie_file: UploadFile | None = File(None)):  # noqa: B008
        if service != "youtube" or method not in {"cookie_file", "browser"}: raise HTTPException(422, "Unsupported authentication method")
        if method == "cookie_file":
            if not cookie_file: raise HTTPException(422, "Cookie file is required")
            data = await cookie_file.read(2_097_153)
            if len(data) > 2_097_152 or b"\x00" in data: raise HTTPException(413, "Cookie file is too large or invalid")
            lines = [line for line in data.decode("utf-8", "strict").splitlines() if line and not line.startswith("#")]
            if any(len(line.split("\t")) != 7 for line in lines): raise HTTPException(422, "Expected Netscape cookie format")
            if not any("youtube.com" in line.split("\t")[0].lstrip(".") for line in lines): raise HTTPException(422, "No supported service cookies found")
        from audioharbor.db.models import AuthSession
        with SessionLocal() as db:
            session = AuthSession(service=service, method=method, persistence="ephemeral", state="active"); db.add(session); db.commit(); return {"id": session.id, "service": service, "method": method, "state": session.state}

    @app.delete("/api/v1/auth-sessions/{session_id}")
    async def revoke_auth(session_id: str):
        from audioharbor.db.models import AuthSession
        with SessionLocal() as db:
            session = db.get(AuthSession, session_id)
            if not session: raise HTTPException(404, "Unknown authentication session")
            session.state = "revoked"; session.opaque_secret_ref = None; db.commit(); return {"revoked": True}

    @app.get("/api/v1/jobs/{job_id}/events")
    async def events(job_id: str):
        async def stream():
            last = 0
            for _ in range(60):
                with SessionLocal() as db:
                    rows = db.scalars(select(__import__('audioharbor.db.models', fromlist=['Event']).Event).where(__import__('audioharbor.db.models', fromlist=['Event']).Event.job_id == job_id, __import__('audioharbor.db.models', fromlist=['Event']).Event.id > last).order_by(__import__('audioharbor.db.models', fromlist=['Event']).Event.id)).all()
                    for row in rows: last = row.id; yield f"id: {row.id}\ndata: {json.dumps({'type': row.event_type, **row.payload_json})}\n\n"
                await asyncio.sleep(1)
        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/api/v1/outputs/{output_id}/file")
    async def file(output_id: str):
        with SessionLocal() as db:
            output = db.get(Output, output_id)
            if not output: raise HTTPException(404, "Unknown output")
            path = (settings.storage.output_dir / output.relative_path).resolve()
            if settings.storage.output_dir not in path.parents or not path.is_file(): raise HTTPException(404, "File unavailable")
            return FileResponse(path, media_type="audio/mpeg", filename=path.name)

    return app
