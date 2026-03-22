# Pathway

A self-hosted navigation dashboard for your home server or Docker environment. Pathway automatically discovers containers with published ports and presents them as a clean service grid — no manual config required to get started.

## Features

- **Auto-discovery** — scans the Docker socket every 30 s and adds new containers automatically
- **Health checks** — probes an HTTP endpoint per service; optional response pattern (regex) catches services that are technically up but returning errors
- **Admin panel** — password-protected UI to add, edit, reorder, and disable services
- **Custom icons** — upload a logo per service
- **Single container** — one image, no external database

## Quick start

```yaml
# docker-compose.yml
services:
  pathway:
    image: pathway
    ports:
      - "80:80"
    volumes:
      - ./data:/app/data
      - /var/run/docker.sock:/var/run/docker.sock:ro
    restart: unless-stopped
```

```bash
docker compose up -d
```

Open `http://<host>` in your browser. On first visit you will be prompted to set an admin password.

## Managing the container

| Action | Command |
|---|---|
| Start | `docker compose up -d` |
| Stop | `docker compose down` |
| Restart | `docker compose restart pathway` |
| View logs | `docker compose logs -f pathway` |
| Rebuild after code changes | `docker compose up -d --build` |

The compose file sets `restart: unless-stopped`, so Pathway will start automatically when Docker starts. To ensure Docker itself starts on boot:

```bash
# systemd-based systems (Ubuntu, Debian, Fedora, etc.)
sudo systemctl enable docker

# Verify it's enabled
sudo systemctl is-enabled docker
```

If you ever stop the container intentionally with `docker compose down`, it will not restart until you run `docker compose up -d` again.

## Building from source

```bash
docker build -t pathway .
```

Or run directly (requires Python 3.12+):

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Configuration

All configuration is stored in `/app/data/config.json` inside the container, which maps to `./data/config.json` on the host with the compose file above.

### Health checks

Each service can have an HTTP health check URL. The probe is GET-only, follows redirects, and accepts any HTTP response as "healthy" (a 401 still means the service is reachable).

| Field | Description |
|---|---|
| **Health check URL** | Endpoint to probe every 30 s (e.g. `http://host:8096/health/alive`) |
| **Response pattern** | Optional Python regex. If set, the response body must match (`re.search`) to be considered healthy. Useful for services that return HTTP 200 but report an error in the body. |

Example patterns:

| Service | Pattern |
|---|---|
| JSON `{"status":"ok"}` | `"status"\s*:\s*"ok"` |
| Plex identity endpoint | `MediaContainer` |
| Plain-text version string | `^\d+\.\d+` |

### Docker auto-discovery

Pathway connects to the Docker socket and lists running containers. Any container that exposes at least one published host port is added as a service. Containers without published ports, and Pathway itself, are ignored.

The `COMPOSE_SERVICE_NAME` environment variable controls which container name is treated as "self" (defaults to `pathway`).

## Volumes

| Path | Purpose |
|---|---|
| `/app/data` | Persisted config and uploaded icons |
| `/var/run/docker.sock` | Docker socket (read-only) for auto-discovery |

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `COMPOSE_SERVICE_NAME` | `pathway` | Container name to skip during auto-discovery |
| `HOST_IP` | *(auto)* | IP used when Docker reports `0.0.0.0` for a port binding. Set this to the LAN IP your browser uses to reach the host if auto-detected URLs are wrong. |

## Admin panel

Navigate to `/admin`. Features:

- Add services manually with a name, URL, description, icon, and health check settings
- Edit or delete any service (auto-detected or manual)
- Toggle services on/off without deleting them
- Drag to reorder the dashboard grid
- Trigger an immediate Docker rescan
- Change the admin password
