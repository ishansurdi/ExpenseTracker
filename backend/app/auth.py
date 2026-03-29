from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe

import bcrypt
from jose import jwt
from passlib.context import CryptContext

from app.config import settings


legacy_password_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
	# Use bcrypt directly to avoid passlib+bcrypt backend compatibility issues.
	return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
	if not password_hash:
		return False

	try:
		# Modern hashes in this app are bcrypt ($2a$ / $2b$ / $2y$).
		if password_hash.startswith(("$2a$", "$2b$", "$2y$")):
			return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))

		# Backward compatibility for any old pbkdf2_sha256 hashes.
		if password_hash.startswith("$pbkdf2-sha256$"):
			return legacy_password_context.verify(plain_password, password_hash)
	except Exception:
		return False

	return False


def hash_refresh_token(refresh_token: str) -> str:
	return sha256(refresh_token.encode("utf-8")).hexdigest()


def create_access_token(subject: str, role: str) -> str:
	expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
	payload = {
		"sub": str(subject),
		"role": role,
		"exp": expires_at,
	}
	return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def create_refresh_token() -> str:
	return token_urlsafe(48)


def get_refresh_expiry(days: int = 7) -> datetime:
	return datetime.now(timezone.utc) + timedelta(days=days)
