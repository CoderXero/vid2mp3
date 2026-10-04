import os
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _xdg(name: str, fallback: str) -> Path:
    return Path(os.environ.get(name, str(Path.home() / fallback))).expanduser()


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(8787, ge=1, le=65535)


class StorageConfig(BaseModel):
    model_config = ConfigDict(validate_default=True)
    output_dir: Path = Path("~/Downloads")
    minimum_free_bytes: int = Field(1_073_741_824, ge=0)
    history_days: int = Field(90, ge=1, le=3650)
    partial_retention_hours: int = Field(24, ge=1, le=720)

    @field_validator("output_dir")
    @classmethod
    def expand(cls, value: Path) -> Path:
        return value.expanduser().resolve()


class WorkerConfig(BaseModel):
    download_concurrency: int = Field(1, ge=1, le=3)
    conversion_concurrency: int = Field(1, ge=1, le=3)
    socket_timeout_seconds: int = Field(30, ge=5, le=300)
    max_attempts: int = Field(5, ge=1, le=5)


class LimitsConfig(BaseModel):
    playlist_entries: int = Field(1000, ge=1, le=10000)
    playlist_depth: int = Field(5, ge=0, le=20)
    collection_nodes: int = Field(20, ge=1, le=1000)
    media_duration_seconds: int = Field(21600, ge=1)
    source_bytes: int = Field(2_147_483_648, ge=1)


class MediaConfig(BaseModel):
    format: Literal["mp3"] = "mp3"
    quality_mode: Literal["vbr", "cbr"] = "vbr"
    vbr_quality: int = Field(2, ge=0, le=9)
    cbr_bitrate: Literal[128, 192, 256, 320] = 192
    embed_artwork: bool = False


class Settings(BaseModel):
    server: ServerConfig = ServerConfig()
    storage: StorageConfig = StorageConfig()
    worker: WorkerConfig = WorkerConfig()
    limits: LimitsConfig = LimitsConfig()
    media: MediaConfig = MediaConfig()
    state_dir: Path
    config_dir: Path
    cache_dir: Path

    @classmethod
    def load(cls) -> "Settings":
        config_dir = _xdg("XDG_CONFIG_HOME", ".config") / "audioharbor"
        state_dir = _xdg("XDG_STATE_HOME", ".local/state") / "audioharbor"
        cache_dir = _xdg("XDG_CACHE_HOME", ".cache") / "audioharbor"
        path = config_dir / "config.toml"
        raw = tomllib.loads(path.read_text()) if path.exists() else {}
        values = {k: v for k, v in raw.items() if k in {"server", "storage", "worker", "limits", "media"}}
        return cls(**values, state_dir=state_dir, config_dir=config_dir, cache_dir=cache_dir)

    def prepare(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.storage.output_dir.mkdir(parents=True, exist_ok=True)
        if os.geteuid() == 0:
            raise RuntimeError("AudioHarbor must not run as root")
