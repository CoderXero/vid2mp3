import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from audioharbor.domain.errors import AudioHarborError


def check_programs() -> dict[str, str | None]:
    return {name: shutil.which(name) for name in ("ffmpeg", "ffprobe", "yt-dlp")}


def convert_to_mp3(source: Path, destination: Path, options: dict) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    profile = []
    if options.get("quality_mode", "vbr") == "cbr": profile = ["-b:a", f"{options.get('cbr_bitrate', 192)}k"]
    else: profile = ["-q:a", str(options.get("vbr_quality", 2))]
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), "-vn", "-map_metadata", "-1", "-codec:a", "libmp3lame", *profile, str(destination)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=options.get("conversion_timeout", 7200), check=False)
    if p.returncode or not destination.exists() or destination.stat().st_size == 0: raise AudioHarborError("CONVERSION_FAILED", "FFmpeg could not create a valid MP3.")


def verify_mp3(path: Path) -> tuple[int, float]:
    p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name,duration", "-of", "json", str(path)], capture_output=True, text=True, check=False)
    if p.returncode or path.stat().st_size == 0: raise AudioHarborError("CONVERSION_FAILED", "The generated file failed verification.")
    try: stream = json.loads(p.stdout)["streams"][0]; duration = float(stream["duration"])
    except (KeyError, IndexError, ValueError, json.JSONDecodeError) as e: raise AudioHarborError("CONVERSION_FAILED", "The generated file has no usable audio.") from e
    if stream.get("codec_name") != "mp3" or duration <= 0: raise AudioHarborError("CONVERSION_FAILED", "The generated file is not a playable MP3.")
    h = hashlib.sha256();
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""): h.update(chunk)
    return path.stat().st_size, duration

