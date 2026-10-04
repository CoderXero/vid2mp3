import json
import os
import subprocess
import sys

from audioharbor.domain.errors import AudioHarborError

from .base import Adapter


class YtDlpAdapter(Adapter):
    def __init__(self, timeout: int = 30): self.timeout = timeout

    def _run(self, args: list[str], timeout: int | None = None) -> list[dict]:
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONNOUSERSITE": "1"}
        cmd = [sys.executable, "-m", "yt_dlp", "--ignore-config", "--no-warnings", "--skip-download", "--flat-playlist", "--dump-single-json", *args]
        try: p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout or self.timeout, env=env, check=False)
        except subprocess.TimeoutExpired as e: raise AudioHarborError("TRANSIENT_NETWORK", "Extractor timed out.", True) from e
        if p.returncode: raise self._error(p.stderr)
        try: return [json.loads(p.stdout)]
        except json.JSONDecodeError as e: raise AudioHarborError("INVALID_SOURCE", "Extractor returned invalid metadata.") from e

    def _error(self, text: str) -> AudioHarborError:
        low = text.lower()
        if "sign in" in low or "login" in low or "authentication" in low: return AudioHarborError("AUTH_REQUIRED", "The provider requires authentication.")
        if "private" in low or "unavailable" in low or "video unavailable" in low: return AudioHarborError("UNAVAILABLE", "The media is unavailable.")
        if "429" in low or "too many requests" in low: return AudioHarborError("RATE_LIMITED", "The provider is rate limiting requests.", True)
        if "drm" in low: return AudioHarborError("DRM_UNSUPPORTED", "DRM-protected media is not supported.")
        return AudioHarborError("INVALID_SOURCE", "The media could not be inspected.")

    def discover(self, url: str, playlist_mode: str):
        args = [url]
        if playlist_mode == "video_only": args += ["--no-playlist"]
        data = self._run(args, timeout=600)[0]
        entries = data.get("entries") or [data]
        result = []
        for i, entry in enumerate(entries):
            if not entry: result.append({"title": "Unavailable item", "id": None, "index_path": [i]}); continue
            result.append({"title": entry.get("title") or "Untitled", "id": entry.get("id"), "url": entry.get("url") or entry.get("webpage_url"), "index_path": [i], "duration": entry.get("duration")})
        return {"title": data.get("title") or "Playlist", "id": data.get("id"), "entries": result, "is_playlist": bool(data.get("entries"))}

    def resolve_media(self, url: str) -> dict:
        return self._run([url], timeout=120)[0]

