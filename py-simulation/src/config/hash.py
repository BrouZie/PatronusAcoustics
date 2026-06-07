import hashlib
import json

from .models import Config


def config_hash(config: Config, length: int = 12) -> str:
    d = config.model_dump(mode="json")
    raw = json.dumps(d, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()[:length]
