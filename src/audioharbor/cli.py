import argparse

from audioharbor.config import Settings
from audioharbor.db.models import Base, engine
from audioharbor.media.conversion import check_programs


def main() -> None:
    parser = argparse.ArgumentParser(prog="audioharbor"); sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor"); serve = sub.add_parser("serve"); serve.add_argument("--reload", action="store_true"); sub.add_parser("worker"); sub.add_parser("start")
    args = parser.parse_args(); settings = Settings.load()
    if args.command == "doctor":
        settings.prepare(); Base.metadata.create_all(engine); print(f"state: {settings.state_dir}\noutput: {settings.storage.output_dir}")
        for name, path in check_programs().items(): print(f"{name}: {path or 'MISSING'}")
        return
    if args.command == "worker":
        from audioharbor.worker.scheduler import run_worker
        run_worker(settings)
        return
    if args.command == "serve":
        import uvicorn
        uvicorn.run("audioharbor.web.app:create_app", host=settings.server.host, port=settings.server.port, factory=True, reload=args.reload)
        return
    if args.command == "start":
        import multiprocessing

        import uvicorn

        from audioharbor.worker.scheduler import run_worker
        child = multiprocessing.Process(target=run_worker, args=(settings,), daemon=True); child.start()
        try: uvicorn.run("audioharbor.web.app:create_app", host=settings.server.host, port=settings.server.port, factory=True)
        finally: child.terminate(); child.join(10)
