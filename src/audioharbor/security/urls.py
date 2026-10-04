import socket
from ipaddress import ip_address
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from audioharbor.domain.errors import AudioHarborError

ALLOWED_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "music.youtube.com"}


def redact_url(url: str) -> str:
    p = urlsplit(url); query = parse_qs(p.query, keep_blank_values=True)
    query = {k: v for k, v in query.items() if k in {"v", "list", "index"}}
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(query, doseq=True), ""))


def validate_url(value: str) -> tuple[str, str]:
    if len(value) > 4096 or any(ord(c) < 32 for c in value): raise AudioHarborError("INVALID_URL", "Enter a valid HTTPS URL.")
    p = urlsplit(value)
    try: port = p.port
    except ValueError as e: raise AudioHarborError("INVALID_URL", "Only standard HTTPS URLs are accepted.") from e
    if p.scheme != "https" or p.username or p.password or port: raise AudioHarborError("INVALID_URL", "Only standard HTTPS URLs are accepted.")
    host = (p.hostname or "").lower().rstrip(".")
    if host not in ALLOWED_HOSTS: raise AudioHarborError("UNSUPPORTED_HOST", "This hosting service is not enabled.")
    try:
        addresses = {ip_address(x[4][0]) for x in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    except OSError as e: raise AudioHarborError("INVALID_URL", "The host could not be resolved.", True) from e
    if any(a.is_private or a.is_loopback or a.is_link_local or a.is_reserved or a.is_unspecified for a in addresses):
        raise AudioHarborError("INVALID_URL", "Private and local network destinations are not allowed.")
    return redact_url(value), "youtube"
