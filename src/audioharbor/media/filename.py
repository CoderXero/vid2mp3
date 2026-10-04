import re
import unicodedata
from pathlib import Path


def safe_component(value: str, fallback: str = "untitled", limit: int = 160) -> str:
    value = unicodedata.normalize("NFKC", value or fallback).replace("\x00", "")
    value = re.sub(r"[\\/:*?\"<>|\r\n\t]+", "_", value)
    value = re.sub(r"\.{2,}", ".", value).strip(" .") or fallback
    if value.upper() in {"CON", "PRN", "AUX", "NUL"} or value.startswith("."): value = "_" + value.lstrip(".")
    raw = value.encode("utf-8")[:limit]
    return raw.decode("utf-8", "ignore").rstrip(" .") or fallback


def output_name(title: str, service: str, media_id: str, playlist: str | None = None, index: int | None = None) -> Path:
    suffix = f"[{safe_component(service)}-{safe_component(media_id, 'unknown', 80)}]"
    base = f"{safe_component(title)} {suffix}.mp3"
    return Path(f"{index:03d} - {base}" if playlist and index is not None else base)

