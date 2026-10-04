from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class JobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=1, max_length=4096)
    playlist_mode: Literal["all", "video_only"] = "all"
    quality_mode: Literal["vbr", "cbr"] = "vbr"
    vbr_quality: int = Field(2, ge=0, le=9)
    cbr_bitrate: Literal[128, 192, 256, 320] = 192
    embed_artwork: bool = False


class StartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entry_ids: list[str] | None = None


class RetryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entry_ids: list[str] | None = None

