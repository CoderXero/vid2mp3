import hashlib
import json


def profile_hash(options: dict) -> str:
    material = {k: options.get(k) for k in ("quality_mode", "vbr_quality", "cbr_bitrate", "embed_artwork")}
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()[:24]

