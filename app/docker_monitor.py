"""Docker socket integration — auto-detect containers with published ports."""

import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

# Ports that are unlikely to be user-facing web interfaces
_SKIP_PORTS = {2375, 2376, 2377}  # Docker daemon ports

# Our own container name (set via env or detected)
_OWN_SERVICE = os.environ.get("COMPOSE_SERVICE_NAME", "pathway")


def _host_ip() -> str:
    """Return the HOST_IP environment variable, or log an error if not set."""
    ip = os.environ.get("HOST_IP", "").strip()
    if not ip:
        log.error(
            "HOST_IP environment variable is not set. "
            "Container URLs using 0.0.0.0 bindings will be incorrect. "
            "Set HOST_IP to the LAN IP of the Docker host."
        )
        return "localhost"
    return ip


def _get_docker_client():
    try:
        import docker
        return docker.from_env()
    except Exception as e:
        log.warning("Docker socket unavailable: %s", e)
        return None


def _container_status(container) -> str:
    try:
        status = container.status  # running, exited, paused, restarting, etc.
        if status == "running":
            return "healthy"
        elif status in ("exited", "dead"):
            return "stopped"
        else:
            return status
    except Exception:
        return "unknown"


def _friendly_name(container) -> str:
    """Extract a human-readable name from container labels or container name."""
    labels = container.labels or {}
    # Docker Compose service label
    name = labels.get("com.docker.compose.service")
    if name:
        return name.replace("-", " ").replace("_", " ").title()
    # Fall back to container name (strip leading slash)
    name = container.name.lstrip("/")
    return name.replace("-", " ").replace("_", " ").title()


def _container_name(container) -> str:
    labels = container.labels or {}
    return labels.get("com.docker.compose.service") or container.name.lstrip("/")


def _published_ports(container) -> list[tuple[str, int]]:
    """Return sorted list of (host_ip, port) for each published port on this container."""
    ports = []
    try:
        port_bindings = container.ports or {}
        for _container_port, bindings in port_bindings.items():
            if not bindings:
                continue
            for b in bindings:
                host_port = b.get("HostPort")
                if host_port:
                    p = int(host_port)
                    if p not in _SKIP_PORTS:
                        ports.append((b.get("HostIp", "0.0.0.0"), p))
    except Exception:
        pass
    return sorted(set(ports), key=lambda x: x[1])


def scan_containers() -> list[dict]:
    """Return list of service dicts for all running containers with published ports."""
    client = _get_docker_client()
    if client is None:
        return []

    fallback_ip = _host_ip()
    results = []

    try:
        containers = client.containers.list()
    except Exception as e:
        log.error("Failed to list containers: %s", e)
        return []

    for c in containers:
        try:
            cname = _container_name(c)
            # Skip ourselves
            if cname == _OWN_SERVICE or c.name.lstrip("/") == _OWN_SERVICE:
                continue

            ports = _published_ports(c)
            if not ports:
                continue

            binding_ip, primary_port = ports[0]
            # 0.0.0.0 means "all interfaces" — use our detected/configured host IP
            host = fallback_ip if binding_ip in ("0.0.0.0", "", "::") else binding_ip
            url = f"http://{host}:{primary_port}"

            results.append(
                {
                    "name": _friendly_name(c),
                    "url": url,
                    "description": f"Port {primary_port}",
                    "container_name": cname,
                    "_docker_status": _container_status(c),
                }
            )
        except Exception as e:
            log.warning("Error processing container %s: %s", c.id[:12], e)

    client.close()
    return results


def get_container_statuses(container_names: list[str]) -> dict[str, str]:
    """Return {container_name: status} for the given names."""
    client = _get_docker_client()
    if client is None:
        return {}

    result = {}
    try:
        containers = client.containers.list(all=True)
        for c in containers:
            cname = _container_name(c)
            if cname in container_names:
                result[cname] = _container_status(c)
    except Exception as e:
        log.error("Failed to get statuses: %s", e)
    finally:
        client.close()

    return result
