"""Simple credential helpers for the Streamlit dashboard."""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Mapping

import streamlit as st

logger = logging.getLogger(__name__)

# Fallback used only when secrets.toml is absent (e.g. local dev without
# the secrets file). In production, .streamlit/secrets.toml takes precedence
# and this value is never reached.
_FALLBACK_AUTH_CONFIG = {
    "username": "Linda-Jane",
    "password_sha256": "8c3eedfc21859a0f3436cfcc631b1346fd13d9648313602bcf518af7741c097f",
}


def hash_password(password: str) -> str:
    """Hash a plaintext password using SHA-256."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def resolve_auth_config(secrets: Mapping | None = None) -> dict[str, str]:
    """
    Load auth config from Streamlit secrets.

    Falls back to the built-in defaults only when no secrets source is
    available (i.e. running locally without secrets.toml). Logs a warning
    when the fallback is used so it is visible in server logs.
    """
    if secrets is not None:
        secret_source = secrets
        using_fallback = not secret_source.get("auth")
    else:
        try:
            secret_source = st.secrets
            using_fallback = not st.secrets.get("auth")
        except Exception:
            secret_source = {}
            using_fallback = True

    if using_fallback:
        logger.warning(
            "auth: no [auth] section found in secrets — using built-in "
            "fallback credentials. Add .streamlit/secrets.toml for production."
        )

    config = _FALLBACK_AUTH_CONFIG.copy()
    auth_section = secret_source.get("auth", {})
    config["username"] = str(auth_section.get("username", config["username"]))
    config["password_sha256"] = str(
        auth_section.get("password_sha256", config["password_sha256"])
    )
    return config


def check_credentials(
    username: str,
    password: str,
    secrets: Mapping | None = None,
) -> bool:
    """Return True when the supplied credentials match the configured values."""
    config = resolve_auth_config(secrets)
    supplied_username = username.strip()
    supplied_password_hash = hash_password(password)

    return hmac.compare_digest(supplied_username, config["username"]) and hmac.compare_digest(
        supplied_password_hash,
        config["password_sha256"],
    )
