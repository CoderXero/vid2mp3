from .errors import AudioHarborError


def classify_provider_error(status: int | None, message: str = "") -> AudioHarborError:
    low = message.lower()
    if status == 401 or any(x in low for x in ("sign in", "login required", "authentication required")): return AudioHarborError("AUTH_REQUIRED", "Authentication is required.")
    if status == 429: return AudioHarborError("RATE_LIMITED", "The provider is rate limiting requests.", True)
    if status in {408, 500, 502, 503, 504}: return AudioHarborError("TRANSIENT_NETWORK", "The provider returned a temporary error.", True)
    if status in {404, 410}: return AudioHarborError("UNAVAILABLE", "The media is unavailable.")
    if status == 403: return AudioHarborError("AUTH_REQUIRED" if any(x in low for x in ("expired", "private", "session")) else "FORBIDDEN", "Access was denied.")
    if status == 400: return AudioHarborError("INVALID_SOURCE", "The source is invalid.")
    return AudioHarborError("UNKNOWN", "The provider returned an unclassified error.")

