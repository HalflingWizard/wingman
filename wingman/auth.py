"""Local password authentication and session helpers."""

import hashlib
import hmac
import json
import secrets
from pathlib import Path


class AuthStore:
    def __init__(self, path: str) -> None:
        self.path = Path(path)

    @property
    def configured(self) -> bool:
        return self.path.exists()

    def set_password(self, password: str) -> None:
        if len(password) < 12:
            raise ValueError("Password must be at least 12 characters")
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"salt": salt.hex(), "digest": digest.hex()}), encoding="utf-8"
        )
        self.path.chmod(0o600)

    def verify(self, password: str) -> bool:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            digest = hashlib.pbkdf2_hmac(
                "sha256", password.encode(), bytes.fromhex(data["salt"]), 310_000
            )
            return hmac.compare_digest(digest.hex(), data["digest"])
        except (OSError, KeyError, ValueError, json.JSONDecodeError):
            return False


def new_session() -> tuple[str, str]:
    return secrets.token_urlsafe(32), secrets.token_urlsafe(32)
