from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
	app_name: str = "Reimbursement API"
	app_env: str = "dev"
	secret_key: str = "replace_this_in_production"
	access_token_expire_minutes: int = 60
	database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/reimbursement"
	cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5500,http://127.0.0.1:5500,http://localhost:5173,http://127.0.0.1:5173,null"

	model_config = SettingsConfigDict(
		env_file="backend/.env.example",
		env_file_encoding="utf-8",
		case_sensitive=False,
		extra="ignore",
	)


settings = Settings()
