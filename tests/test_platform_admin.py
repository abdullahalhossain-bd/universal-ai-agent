from datetime import datetime, timezone

import jwt
import pytest

from app.auth.admin_session import create_admin_access_token
from app.core.config import Settings, settings


def test_admin_access_token_has_expiry():
	token = create_admin_access_token(admin_id="admin-1")
	payload = jwt.decode(
		token,
		settings.jwt_secret_key,
		algorithms=[settings.jwt_algorithm],
	)

	assert payload["type"] == "platform_admin_session"
	assert payload["exp"] > datetime.now(timezone.utc).timestamp()


def test_production_settings_reject_default_jwt_secret():
	with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
		Settings(
			environment="production",
			database_url="postgresql://user:pass@localhost/db",
			credential_encryption_key=(
				"1Q5CMAJ3S3iemRmjauMWsPLeJmpY-VPO0J_9jHijTxs="
			),
			jwt_secret_key="dev-only-insecure-secret-change-me",
			cors_allow_origins="https://dashboard.example.com",
		)


def test_production_settings_reject_wildcard_cors():
	with pytest.raises(ValueError, match="CORS_ALLOW_ORIGINS"):
		Settings(
			environment="production",
			database_url="postgresql://user:pass@localhost/db",
			credential_encryption_key=(
				"1Q5CMAJ3S3iemRmjauMWsPLeJmpY-VPO0J_9jHijTxs="
			),
			jwt_secret_key="x" * 32,
			cors_allow_origins="*",
		)
