from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routes.admin_dashboard import router as admin_dashboard_router
from app.routes.auth import router as auth_router


app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(admin_dashboard_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Reimbursement backend is running"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
