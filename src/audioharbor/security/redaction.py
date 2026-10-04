import re


def sanitize_message(value: str) -> str:
    value = re.sub(r"(?i)(cookie|authorization|password|signature|token)\s*[:=]\s*[^\s,;]+", r"\1=[redacted]", value)
    value = re.sub(r"https?://[^\s]+[?][^\s]+", "[signed URL redacted]", value)
    return value[:2000]

