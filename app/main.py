"""Pathway — Docker navigation dashboard."""

import asyncio
import logging
import mimetypes
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Optional

from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .auth import (
    SESSION_COOKIE,
    authenticate,
    change_password,
    complete_setup,
    create_session_token,
    is_setup_complete,
    require_auth,
    verify_session_token,
)
from .config_store import (
    DATA_DIR,
    ICONS_DIR,
    delete_service,
    get_service,
    get_services,
    load_config,
    merge_auto_detected,
    new_service,
    save_config,
    upsert_service,
)
from .docker_monitor import get_container_statuses, scan_containers
from .health_checker import get_all_statuses, poll_health_checks

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
POLL_INTERVAL = 30  # seconds


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run initial scan then poll in background
    asyncio.create_task(_poll_docker())
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


async def _poll_docker():
    while True:
        try:
            detected = scan_containers()
            cfg = load_config()
            merge_auto_detected(cfg, detected)
            save_config(cfg)
            await poll_health_checks(get_services(cfg))
        except Exception as e:
            log.error("Poll error: %s", e)
        await asyncio.sleep(POLL_INTERVAL)


# ---------------------------------------------------------------------------
# Icon serving
# ---------------------------------------------------------------------------


@app.get("/icons/{filename}")
async def serve_icon(filename: str):
    path = ICONS_DIR / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404)
    mime, _ = mimetypes.guess_type(str(path))
    return FileResponse(str(path), media_type=mime or "application/octet-stream")


# ---------------------------------------------------------------------------
# Frontend pages
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    return FileResponse(str(STATIC_DIR / "admin.html"))


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------


@app.get("/api/auth/status")
async def auth_status(pathway_session: Optional[str] = Cookie(default=None)):
    setup = is_setup_complete()
    if not setup:
        return {"setup_required": True, "authenticated": False}
    if pathway_session:
        cfg = load_config()
        secret = cfg.get("session_secret", "")
        if verify_session_token(secret, pathway_session):
            return {"setup_required": False, "authenticated": True}
    return {"setup_required": False, "authenticated": False}


@app.post("/api/auth/setup")
async def setup(response: Response, password: str = Form(...)):
    if is_setup_complete():
        raise HTTPException(status_code=400, detail="Already configured")
    if len(password) < 4:
        raise HTTPException(status_code=422, detail="Password too short (min 4 chars)")
    complete_setup(password)
    cfg = load_config()
    token = create_session_token(cfg["session_secret"])
    response.set_cookie(SESSION_COOKIE, token, httponly=True, max_age=86400, samesite="lax")
    return {"ok": True}


@app.post("/api/auth/login")
async def login(response: Response, password: str = Form(...)):
    token = authenticate(password)
    if not token:
        raise HTTPException(status_code=401, detail="Invalid password")
    response.set_cookie(SESSION_COOKIE, token, httponly=True, max_age=86400, samesite="lax")
    return {"ok": True}


@app.post("/api/auth/logout")
async def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Public API — dashboard data
# ---------------------------------------------------------------------------


@app.get("/api/services")
async def list_services():
    cfg = load_config()
    services = get_services(cfg)
    enabled = [s for s in services if s.get("enabled", True)]

    # Enrich with live Docker status for auto services
    auto_names = [s["container_name"] for s in enabled if s.get("container_name")]
    if auto_names:
        statuses = get_container_statuses(auto_names)
        for svc in enabled:
            if svc.get("container_name"):
                svc["_docker_status"] = statuses.get(svc["container_name"], "unknown")

    # Enrich with HTTP health check results
    health_statuses = get_all_statuses()
    for svc in enabled:
        if svc.get("health_check_url"):
            svc["_health_status"] = health_statuses.get(svc["id"], "pending")

    enabled.sort(key=lambda s: s.get("order", 0))
    return enabled


# ---------------------------------------------------------------------------
# Admin API — requires auth
# ---------------------------------------------------------------------------

AuthDep = Annotated[None, Depends(require_auth)]


@app.get("/api/admin/services")
async def admin_list_services(_: AuthDep):
    cfg = load_config()
    services = get_services(cfg)

    auto_names = [s["container_name"] for s in services if s.get("container_name")]
    if auto_names:
        statuses = get_container_statuses(auto_names)
        for svc in services:
            if svc.get("container_name"):
                svc["_docker_status"] = statuses.get(svc["container_name"], "unknown")

    health_statuses = get_all_statuses()
    for svc in services:
        if svc.get("health_check_url"):
            svc["_health_status"] = health_statuses.get(svc["id"], "pending")

    services.sort(key=lambda s: s.get("order", 0))
    return services


@app.post("/api/admin/services", status_code=201)
async def create_service(
    _: AuthDep,
    name: str = Form(...),
    url: str = Form(...),
    description: str = Form(""),
    enabled: bool = Form(True),
    health_check_url: str = Form(""),
    health_check_pattern: str = Form(""),
    icon: Optional[UploadFile] = File(default=None),
):
    cfg = load_config()
    max_order = max((s.get("order", 0) for s in cfg.get("services", [])), default=-1)
    svc = new_service(
        name=name,
        url=url,
        description=description,
        enabled=enabled,
        order=max_order + 1,
        health_check_url=health_check_url.strip() or None,
        health_check_pattern=health_check_pattern.strip() or None,
    )

    if icon and icon.filename:
        svc["icon_filename"] = await _save_icon(svc["id"], icon)

    upsert_service(cfg, svc)
    save_config(cfg)
    return svc


@app.put("/api/admin/services/{service_id}")
async def update_service(
    service_id: str,
    _: AuthDep,
    name: Optional[str] = Form(default=None),
    url: Optional[str] = Form(default=None),
    description: Optional[str] = Form(default=None),
    enabled: Optional[bool] = Form(default=None),
    order: Optional[int] = Form(default=None),
    health_check_url: Optional[str] = Form(default=None),
    health_check_pattern: Optional[str] = Form(default=None),
    icon: Optional[UploadFile] = File(default=None),
):
    cfg = load_config()
    svc = get_service(cfg, service_id)
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found")

    if name is not None:
        svc["name"] = name
    if url is not None:
        svc["url"] = url
    if description is not None:
        svc["description"] = description
    if enabled is not None:
        svc["enabled"] = enabled
    if order is not None:
        svc["order"] = order
    if health_check_url is not None:
        svc["health_check_url"] = health_check_url.strip() or None
    if health_check_pattern is not None:
        svc["health_check_pattern"] = health_check_pattern.strip() or None

    if icon and icon.filename:
        # Remove old icon if exists
        if svc.get("icon_filename"):
            old = ICONS_DIR / svc["icon_filename"]
            if old.exists():
                old.unlink()
        svc["icon_filename"] = await _save_icon(service_id, icon)

    upsert_service(cfg, svc)
    save_config(cfg)
    return svc


@app.delete("/api/admin/services/{service_id}", status_code=204)
async def remove_service(service_id: str, _: AuthDep):
    cfg = load_config()
    svc = get_service(cfg, service_id)
    if svc and svc.get("icon_filename"):
        icon_path = ICONS_DIR / svc["icon_filename"]
        if icon_path.exists():
            icon_path.unlink()
    if not delete_service(cfg, service_id):
        raise HTTPException(status_code=404, detail="Service not found")
    save_config(cfg)


@app.post("/api/admin/scan")
async def trigger_scan(_: AuthDep):
    detected = scan_containers()
    cfg = load_config()
    merge_auto_detected(cfg, detected)
    save_config(cfg)
    return {"detected": len(detected)}


@app.put("/api/admin/password")
async def update_password(_: AuthDep, new_password: str = Form(...)):
    if len(new_password) < 4:
        raise HTTPException(status_code=422, detail="Password too short (min 4 chars)")
    change_password(new_password)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _save_icon(service_id: str, upload: UploadFile) -> str:
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(upload.filename).suffix.lower() or ".png"
    filename = f"{service_id}{ext}"
    data = await upload.read()
    (ICONS_DIR / filename).write_bytes(data)
    return filename
