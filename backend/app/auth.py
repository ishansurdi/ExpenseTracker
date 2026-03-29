from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe

from jose import jwt
from passlib.context import CryptContext

from app.config import settings


password_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
	return password_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
	return password_context.verify(plain_password, password_hash)


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
