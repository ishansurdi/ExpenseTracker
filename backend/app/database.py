from collections.abc import Generator

from fastapi import HTTPException, status
from psycopg import connect
from psycopg import OperationalError
from psycopg.rows import dict_row

from app.config import settings


def _normalize_database_url(url: str) -> str:
	return url.replace("postgresql+psycopg://", "postgresql://", 1)


def get_connection():
	return connect(_normalize_database_url(settings.database_url), row_factory=dict_row)


def get_db() -> Generator:
	try:
		connection = get_connection()
	except OperationalError as exc:
		raise HTTPException(
			status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
			detail="Database connection failed. Check DATABASE_URL credentials and PostgreSQL status.",
		) from exc
	try:
		yield connection
	finally:
		connection.close()
