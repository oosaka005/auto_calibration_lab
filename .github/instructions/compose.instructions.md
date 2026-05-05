---
description: "Use when creating or editing compose.yaml. Covers service structure, volumes, restart policy, node configuration, and infrastructure requirements."
applyTo: "compose.yaml"
---

# compose.yaml Rules

## What Must NOT Be Changed (MADSci Framework Rules)

The following are fixed by the MADSci framework. Changing them will break the system:

- `restart: unless-stopped` — required on all services for 24/7 lab automation
- `command:` for managers — fixed entry points defined by MADSci (see Manager Commands below)
- `depends_on:` structure — defines startup order required by MADSci
- Infrastructure image versions (`mongo:8.0`, `redis:7.4`, `postgres:17`)
- Right-hand side of `volumes:` (paths inside the container, e.g. `/home/madsci/...`)
- Infrastructure port numbers (27017, 6379, 5432)

## What CAN Be Changed (Project-Specific Settings)

| Item | When to change |
|------|----------------|
| Left side of `volumes:` (`.:/home/madsci/<lab_name>`) | When renaming the project folder |
| `working_dir:` | Must match the left side of `volumes:` above |
| `image: ghcr.io/ad-sdl/madsci:latest` | When pinning to a specific version (recommended for production) |
| `${MONGODB_PORT:-27017}` etc. | When ports conflict with other services on the host PC |

## The Only Section to Add Freely: Nodes

New nodes can be added under `# ---- Nodes ----`. The format is fixed:

```yaml
<node_service_name>:
  <<: *madsci-service
  container_name: <node_service_name>
  command: python modules/<node_name>/<node_name>.py
  depends_on:
    - event_manager
  ports:
    - "<port>:<port>"
  environment:
    - NODE_NAME=<node_service_name>
    - NODE_MODULE_NAME=<module_name>
    - NODE_URL=http://0.0.0.0:<port>/
    - EVENT_SERVER_URL=http://event_manager:8001/
    - RESOURCE_SERVER_URL=http://resource_manager:8003/
```

Rules for node entries:
- `NODE_NAME` must exactly match the key in `workcell_nodes` in `settings.yaml`
- `NODE_URL` must use `0.0.0.0` (not `localhost`) so the node is reachable from outside the container
- `workcell_nodes` in `settings.yaml` should use `http://localhost:<port>/` (Windows side)
- Each node must use a unique port number
- `command:` path must be relative to `working_dir` and point to the node's Python file
- Always include `depends_on: - event_manager`
- Always include `EVENT_SERVER_URL` and `RESOURCE_SERVER_URL` pointing to container names

## Service Structure

All MADSci services use a shared anchor for common configuration:

```yaml
x-madsci-service: &madsci-service
  image: ghcr.io/ad-sdl/madsci:latest
  env_file:
    - ./.env
  volumes:
    - .:/home/madsci/<lab_name>
    - ./.madsci:/home/madsci/.madsci
  restart: unless-stopped
  working_dir: /home/madsci/<lab_name>
  networks:
    - madsci_net
```

Each manager/node service uses `<<: *madsci-service` to inherit this configuration. `restart: unless-stopped` is inherited from this anchor — do NOT add it again individually to managers or nodes.

A named bridge network must be declared at the end of the file:

```yaml
networks:
  madsci_net:
    driver: bridge
```

## Required Infrastructure Services

The following infrastructure services are required. They do NOT use the shared anchor:

| Service | Image | Purpose |
|---------|-------|---------|
| `madsci_mongodb` | `mongo:8.0` | Event, experiment, data, workcell storage |
| `madsci_redis` | `redis:7.4` | Workcell and location manager state |
| `madsci_postgres` | `postgres:17` | Resource manager relational data |

## Manager Commands (Fixed — Do Not Change)

| Service | command |
|---------|---------|
| `lab_manager` | `python -m madsci.squid.lab_server` |
| `event_manager` | `python -m madsci.event_manager.event_server` |
| `experiment_manager` | `python -m madsci.experiment_manager.experiment_server` |
| `resource_manager` | `python -m madsci.resource_manager.resource_server` |
| `data_manager` | `python -m madsci.data_manager.data_server` |
| `workcell_manager` | `python -m madsci.workcell_manager.workcell_server` |
| `location_manager` | `python -m madsci.location_manager.location_server` |

## depends_on Rules (Fixed — Do Not Change)

| Service | depends_on |
|---------|------------|
| `lab_manager` | `event_manager` |
| `event_manager` | `madsci_mongodb` |
| `experiment_manager` | `madsci_mongodb`, `lab_manager` |
| `resource_manager` | `madsci_postgres`, `event_manager` |
| `data_manager` | `madsci_mongodb`, `event_manager` |
| `location_manager` | `madsci_redis`, `event_manager`, `resource_manager` |
| `workcell_manager` | `madsci_redis`, `madsci_mongodb`, `resource_manager`, `event_manager`, `location_manager` |
| nodes | `event_manager` |

## Volumes

Each MADSci service requires two volume mounts (inherited via `*madsci-service`):
1. Project code: `.:/home/madsci/<lab_name>` — makes your code visible inside the container
2. Runtime data: `./.madsci:/home/madsci/.madsci` — persists logs, backups, and DB data on the host PC

Infrastructure services only need one volume for their own data directory.

## Network Architecture (Bridge Network)

This project uses a **bridge network** (`madsci_net`) instead of `network_mode: host`.

**Why:** `network_mode: host` is Linux-only and does not work on Docker Desktop for Windows.
The bridge network approach works on both Linux and Windows.

### Three rules that must be followed together:

| Rule | Purpose |
|------|---------|
| `networks: - madsci_net` on every service | Enables container-to-container DNS resolution by container name |
| `ports: - "<port>:<port>"` on every manager/node | Exposes the service to Windows `localhost` |
| `{PREFIX}_SERVER_URL=http://0.0.0.0:<port>/` in `environment:` | Makes the server bind to all interfaces, not just `127.0.0.1` |

### URL conventions

| Context | URL format |
|---------|------------|
| Container → other container | `http://<container_name>:<port>/` (e.g. `http://event_manager:8001/`) |
| Container's own bind address | `http://0.0.0.0:<port>/` |
| Windows → container (notebooks, scripts) | `http://localhost:<port>/` |

> **Note:** `settings.yaml` uses `http://localhost:<port>/` throughout (Windows-side URLs).
> The `environment:` in `compose.yaml` overrides the bind address to `0.0.0.0` and
> inter-container URLs to container names. This is why both files are needed.

### Manager environment variables

Each manager service must declare its own `SERVER_URL` and the URLs of services it connects to:

| Manager | Required environment variables |
|---------|--------------------------------|
| `event_manager` | `EVENT_SERVER_URL=http://0.0.0.0:8001/`, `EVENT_MONGO_DB_URL=mongodb://madsci_mongodb:27017/` |
| `resource_manager` | `RESOURCE_SERVER_URL=http://0.0.0.0:8003/`, `RESOURCE_DB_URL=postgresql://madsci:madsci@madsci_postgres:5432/madsci_resources`, `EVENT_SERVER_URL=http://event_manager:8001/` |
| `data_manager` | `DATA_SERVER_URL=http://0.0.0.0:8004/`, `DATA_MONGO_DB_URL=mongodb://madsci_mongodb:27017/`, `EVENT_SERVER_URL=http://event_manager:8001/` |
| `workcell_manager` | `WORKCELL_SERVER_URL=http://0.0.0.0:8005/`, `WORKCELL_MONGO_DB_URL=mongodb://madsci_mongodb:27017/`, `WORKCELL_REDIS_HOST=madsci_redis`, `EVENT_SERVER_URL=http://event_manager:8001/`, `RESOURCE_SERVER_URL=http://resource_manager:8003/`, `LOCATION_SERVER_URL=http://location_manager:8006/` |
| `location_manager` | `LOCATION_SERVER_URL=http://0.0.0.0:8006/`, `LOCATION_REDIS_HOST=madsci_redis`, `EVENT_SERVER_URL=http://event_manager:8001/`, `RESOURCE_SERVER_URL=http://resource_manager:8003/` |

> **Infrastructure services** (`madsci_mongodb`, `madsci_redis`, `madsci_postgres`) do not use
> the `*madsci-service` anchor, but must still be added to `madsci_net` explicitly:
> ```yaml
> networks:
>   - madsci_net
> ```
