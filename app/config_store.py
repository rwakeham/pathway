import json
import os
import uuid
from pathlib import Path
from typing import Optional

DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data"))
CONFIG_FILE = DATA_DIR / "config.json"
ICONS_DIR = DATA_DIR / "icons"


def _ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ICONS_DIR.mkdir(parents=True, exist_ok=True)


def _default_config() -> dict:
    return {
        "admin_password_hash": None,
        "session_secret": os.urandom(32).hex(),
        "services": [],
    }


def load_config() -> dict:
    _ensure_dirs()
    if not CONFIG_FILE.exists():
        cfg = _default_config()
        save_config(cfg)
        return cfg
    with open(CONFIG_FILE) as f:
        return json.load(f)


def save_config(cfg: dict):
    _ensure_dirs()
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def get_services(cfg: dict) -> list[dict]:
    return cfg.get("services", [])


def get_service(cfg: dict, service_id: str) -> Optional[dict]:
    return next((s for s in cfg.get("services", []) if s["id"] == service_id), None)


def upsert_service(cfg: dict, service: dict) -> dict:
    """Insert or update a service by id. Returns the service."""
    services = cfg.setdefault("services", [])
    idx = next((i for i, s in enumerate(services) if s["id"] == service["id"]), None)
    if idx is None:
        services.append(service)
    else:
        services[idx] = service
    return service


def delete_service(cfg: dict, service_id: str) -> bool:
    services = cfg.get("services", [])
    before = len(services)
    cfg["services"] = [s for s in services if s["id"] != service_id]
    return len(cfg["services"]) < before


def new_service(
    name: str,
    url: str,
    description: str = "",
    source: str = "manual",
    container_name: Optional[str] = None,
    enabled: bool = True,
    order: int = 0,
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "name": name,
        "url": url,
        "description": description,
        "icon_filename": None,
        "enabled": enabled,
        "source": source,
        "container_name": container_name,
        "order": order,
    }


def merge_auto_detected(cfg: dict, detected: list[dict]):
    """Merge auto-detected containers into config without overwriting user edits."""
    existing_by_container = {
        s["container_name"]: s
        for s in cfg.get("services", [])
        if s.get("container_name")
    }
    max_order = max((s.get("order", 0) for s in cfg.get("services", [])), default=-1)
    for d in detected:
        cname = d["container_name"]
        if cname in existing_by_container:
            # Update mutable auto fields only
            existing_by_container[cname]["_docker_status"] = d.get("_docker_status")
        else:
            max_order += 1
            svc = new_service(
                name=d["name"],
                url=d["url"],
                description=d.get("description", ""),
                source="auto",
                container_name=cname,
                order=max_order,
            )
            svc["_docker_status"] = d.get("_docker_status")
            upsert_service(cfg, svc)

    # Update status for all auto services no longer running
    detected_names = {d["container_name"] for d in detected}
    for svc in cfg.get("services", []):
        if svc.get("source") == "auto" and svc.get("container_name") not in detected_names:
            svc["_docker_status"] = "stopped"
