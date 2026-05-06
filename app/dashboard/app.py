"""FastAPI dashboard application factory."""

from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

from app.config import Settings

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

security = HTTPBasic()


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="Domain Cleanup Dashboard", docs_url=None, redoc_url=None)
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

    def _auth(credentials: HTTPBasicCredentials = Depends(security)) -> str:
        ok_user = secrets.compare_digest(credentials.username, settings.dashboard_username)
        ok_pass = secrets.compare_digest(credentials.password, settings.dashboard_password)
        if not ok_user or not ok_pass:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Basic"},
            )
        return credentials.username

    from app.dashboard.routes import register_routes

    register_routes(app, templates, settings, _auth)
    return app
