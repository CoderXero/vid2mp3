from dataclasses import dataclass


@dataclass
class MediaInfo:
    media_id: str
    title: str
    uploader: str | None = None
    webpage_url: str | None = None
    duration: float | None = None
    playlist_title: str | None = None
    playlist_id: str | None = None
    index: int | None = None


class Adapter:
    service = "youtube"
    def classify_url(self, url: str) -> dict: raise NotImplementedError
    def discover(self, url: str, playlist_mode: str): raise NotImplementedError
    def resolve_media(self, url: str) -> dict: raise NotImplementedError

