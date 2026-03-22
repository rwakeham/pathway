import hashlib
import hmac
import time
from typing import Optional

import bcrypt
from fastapi import Cookie, HTTPException, Request, status

from .config_store import load_config, save_config

SESSION_COOKIE = "pathway_session"
SESSION_TTL = 86400  # 24 hours


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def _make_token(secret: str, expiry: int) -> str:
    payload = f"{expiry}"
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{expiry}.{sig}"


def create_session_token(secret: str) -> str:
    expiry = int(time.time()) + SESSION_TTL
    return _make_token(secret, expiry)


def verify_session_token(secret: str, token: str) -> bool:
    try:
        expiry_str, sig = token.rsplit(".", 1)
        expiry = int(expiry_str)
        if time.time() > expiry:
            return False
        expected_sig = hmac.new(secret.encode(), expiry_str.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected_sig)
    except Exception:
        return False


def is_setup_complete() -> bool:
    cfg = load_config()
    return bool(cfg.get("admin_password_hash"))


def complete_setup(password: str):
    cfg = load_config()
    cfg["admin_password_hash"] = hash_password(password)
    save_config(cfg)


def authenticate(password: str) -> Optional[str]:
    """Returns session token if password is correct, else None."""
    cfg = load_config()
    stored = cfg.get("admin_password_hash")
    if not stored:
        return None
    if verify_password(password, stored):
        return create_session_token(cfg["session_secret"])
    return None


def change_password(new_password: str):
    cfg = load_config()
    cfg["admin_password_hash"] = hash_password(new_password)
    save_config(cfg)


def require_auth(pathway_session: Optional[str] = Cookie(default=None)):
    """FastAPI dependency that raises 401 if not authenticated."""
    if not pathway_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    cfg = load_config()
    secret = cfg.get("session_secret", "")
    if not verify_session_token(secret, pathway_session):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
