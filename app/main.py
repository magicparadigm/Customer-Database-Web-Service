from pathlib import Path

from fastapi import FastAPI, status
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import api_customers, web_customers

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title=settings.app_name,
    description="Customer records over a JSON API and a staff web UI.",
    version="0.1.0",
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(web_customers.router)
app.include_router(api_customers.router)


@app.get("/", include_in_schema=False)
def index():
    return RedirectResponse("/customers", status_code=status.HTTP_302_FOUND)


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"status": "ok"}
