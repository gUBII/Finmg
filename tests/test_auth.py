"""Tests for dashboard auth helpers."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.auth.auth import check_credentials, hash_password, resolve_auth_config


class TestAuthHelpers:

    def test_hash_password_matches_expected_value(self):
        assert (
            hash_password("bling")
            == "8c3eedfc21859a0f3436cfcc631b1346fd13d9648313602bcf518af7741c097f"
        )

    def test_resolve_auth_config_prefers_provided_secrets(self):
        config = resolve_auth_config(
            {"auth": {"username": "Example", "password_sha256": "abc123"}}
        )
        assert config == {"username": "Example", "password_sha256": "abc123"}

    def test_check_credentials_accepts_matching_values(self):
        secrets = {
            "auth": {
                "username": "Linda-Jane",
                "password_sha256": hash_password("bling"),
            }
        }
        assert check_credentials("Linda-Jane", "bling", secrets=secrets) is True
        assert check_credentials("Linda-Jane", "wrong", secrets=secrets) is False
