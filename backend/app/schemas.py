from datetime import datetime

from pydantic import BaseModel, Field


class CompanySignupRequest(BaseModel):
	company_name: str = Field(min_length=2, max_length=150)
	country_name: str = Field(min_length=2, max_length=120)
	currency_code: str = Field(min_length=1, max_length=10)
	currency_name: str | None = Field(default=None, max_length=120)
	currency_symbol: str | None = Field(default=None, max_length=20)
	admin_full_name: str = Field(min_length=2, max_length=150)
	admin_email: str = Field(min_length=5, max_length=255)
	password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
	identifier: str = Field(min_length=2, max_length=255)
	password: str = Field(min_length=8, max_length=128)


class UserSummary(BaseModel):
	id: str
	login_id: str
	full_name: str
	email: str
	role: str
	company_id: str


class CompanySummary(BaseModel):
	id: str
	name: str
	slug: str
	country_name: str
	currency_code: str
	currency_name: str | None = None
	currency_symbol: str | None = None


class AuthResponse(BaseModel):
	access_token: str
	refresh_token: str
	token_type: str = "bearer"
	user: UserSummary
	company: CompanySummary


class SignupResponse(BaseModel):
	message: str
	access_token: str
	refresh_token: str
	token_type: str = "bearer"
	user: UserSummary
	company: CompanySummary


class ErrorResponse(BaseModel):
	detail: str
	timestamp: datetime | None = None
