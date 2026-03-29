from datetime import datetime, timezone
from re import sub

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.auth import create_access_token, create_refresh_token, get_refresh_expiry, hash_password, hash_refresh_token, verify_password
from app.database import get_db
from app.schemas import AuthResponse, CompanySignupRequest, CompanySummary, LoginRequest, SignupResponse, UserSummary


router = APIRouter(prefix="/auth", tags=["Authentication"])


def slugify_company_name(company_name: str) -> str:
	normalized = sub(r"[^a-z0-9]+", "-", company_name.lower()).strip("-")
	return normalized or "company"


def generate_login_id(connection, role: str) -> str:
	if role == "admin":
		sequence_name = "admin_login_seq"
		prefix = "A"
	elif role == "manager":
		sequence_name = "manager_login_seq"
		prefix = "MAN"
	else:
		sequence_name = "employee_login_seq"
		prefix = "E"

	with connection.cursor() as cursor:
		cursor.execute(f"SELECT nextval('{sequence_name}') AS sequence_value")
		sequence_value = cursor.fetchone()["sequence_value"]

	return f"{prefix}{sequence_value:04d}"


def create_auth_session(connection, user_id: str, refresh_token: str, request: Request) -> None:
	refresh_token_hash = hash_refresh_token(refresh_token)

	with connection.cursor() as cursor:
		cursor.execute(
			"""
			INSERT INTO auth_sessions (user_id, refresh_token_hash, user_agent, ip_address, expires_at)
			VALUES (%s, %s, %s, %s, %s)
			""",
			(
				user_id,
				refresh_token_hash,
				request.headers.get("user-agent"),
				request.client.host if request.client else None,
				get_refresh_expiry(),
			),
		)


def build_auth_response(user_row: dict, company_row: dict) -> dict:
	access_token = create_access_token(subject=user_row["id"], role=user_row["role"])
	refresh_token = create_refresh_token()

	return {
		"access_token": access_token,
		"refresh_token": refresh_token,
		"user": UserSummary(
			id=str(user_row["id"]),
			login_id=user_row["login_id"],
			full_name=user_row["full_name"],
			email=user_row["email"],
			role=user_row["role"],
			company_id=str(user_row["company_id"]),
		),
		"company": CompanySummary(
			id=str(company_row["id"]),
			name=company_row["name"],
			slug=company_row["slug"],
			country_name=company_row["country_name"],
			currency_code=company_row["currency_code"],
			currency_name=company_row["currency_name"],
			currency_symbol=company_row["currency_symbol"],
		),
	}


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
def signup_company(payload: CompanySignupRequest, request: Request, db=Depends(get_db)):
	company_slug = slugify_company_name(payload.company_name)

	try:
		with db.cursor() as cursor:
			cursor.execute("SELECT id FROM companies WHERE slug = %s", (company_slug,))
			if cursor.fetchone():
				raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Company slug already exists")

			cursor.execute("SELECT id FROM users WHERE email = %s", (payload.admin_email.lower(),))
			if cursor.fetchone():
				raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered")

			cursor.execute(
				"""
				INSERT INTO companies (name, slug, country_name, currency_code, currency_name, currency_symbol)
				VALUES (%s, %s, %s, %s, %s, %s)
				RETURNING id, name, slug, country_name, currency_code, currency_name, currency_symbol
				""",
				(
					payload.company_name,
					company_slug,
					payload.country_name,
					payload.currency_code,
					payload.currency_name,
					payload.currency_symbol,
				),
			)
			company_row = cursor.fetchone()

			login_id = generate_login_id(db, "admin")
			cursor.execute(
				"""
				INSERT INTO users (company_id, login_id, full_name, email, password_hash, role, is_email_verified)
				VALUES (%s, %s, %s, %s, %s, 'admin', TRUE)
				RETURNING id, company_id, login_id, full_name, email, role
				""",
				(
					company_row["id"],
					login_id,
					payload.admin_full_name,
					payload.admin_email.lower(),
					hash_password(payload.password),
				),
			)
			user_row = cursor.fetchone()

			auth_payload = build_auth_response(user_row, company_row)
			create_auth_session(db, user_row["id"], auth_payload["refresh_token"], request)
			db.commit()

			return {
				"message": f"Company created successfully. Admin login ID: {user_row['login_id']}",
				**auth_payload,
			}
	except HTTPException:
		db.rollback()
		raise
	except Exception as exc:
		db.rollback()
		raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Signup failed: {exc}") from exc


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request, db=Depends(get_db)):
	identifier = payload.identifier.strip()
	identifier_lower = identifier.lower()

	try:
		with db.cursor() as cursor:
			cursor.execute(
				"""
				SELECT id, company_id, login_id, full_name, email, password_hash, role, is_active
				FROM users
				WHERE lower(email) = %s OR login_id = %s
				LIMIT 1
				""",
				(identifier_lower, identifier),
			)
			user_row = cursor.fetchone()

			login_success = bool(user_row and user_row["is_active"] and verify_password(payload.password, user_row["password_hash"]))

			cursor.execute(
				"""
				INSERT INTO login_audit_logs (user_id, email_attempted, was_successful, ip_address, user_agent, attempted_at)
				VALUES (%s, %s, %s, %s, %s, %s)
				""",
				(
					user_row["id"] if user_row else None,
					identifier_lower,
					login_success,
					request.client.host if request.client else None,
					request.headers.get("user-agent"),
					datetime.now(timezone.utc),
				),
			)

			if not login_success:
				db.commit()
				raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

			cursor.execute(
				"""
				SELECT id, name, slug, country_name, currency_code, currency_name, currency_symbol
				FROM companies
				WHERE id = %s
				LIMIT 1
				""",
				(user_row["company_id"],),
			)
			company_row = cursor.fetchone()

			cursor.execute(
				"UPDATE users SET last_login_at = %s, updated_at = %s WHERE id = %s",
				(datetime.now(timezone.utc), datetime.now(timezone.utc), user_row["id"]),
			)

			auth_payload = build_auth_response(user_row, company_row)
			create_auth_session(db, user_row["id"], auth_payload["refresh_token"], request)
			db.commit()
			return auth_payload
	except HTTPException:
		raise
	except Exception as exc:
		db.rollback()
		raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Login failed: {exc}") from exc
