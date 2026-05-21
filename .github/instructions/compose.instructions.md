---
description: "Use when creating or editing compose.yaml. Covers service structure, manager URLs, node configuration, volumes, restart policy, and infrastructure requirements."
applyTo: "compose.yaml"
---

# compose.yaml Rules

## Startup Command

Always use `--build` when starting services:

```bash
docker compose up -d --build
```

- `--build` rebuilds the image only when `Dockerfile` or `devices/requirements.txt` has changed.
- After the first `docker compose up -d --build`, containers auto-restart on PC reboot because services use `restart: unless-stopped`.
- Use `docker compose down` only when intentionally stopping the system.

## What Must NOT Be Changed

The following are fixed by the MADSci framework or by this Docker Compose architecture:

- `restart: unless-stopped` on all managers and nodes
- `command:` for manager services
- `depends_on:` structure for managers
- Infrastructure image versions: `mongo:8.0`, `redis:7.4`, `postgres:17`
- Right-hand side of `volumes:` paths inside containers
- Infrastructure port numbers: `27017`, `6379`, `5432`

## What CAN Be Changed

| Item | When to change |
|------|----------------|
| Left side of `volumes:` (`.:/home/madsci/<lab_name>`) | When renaming the project folder |
| `working_dir:` | Must match the project path inside the container |
| `build: .` | Only if the Dockerfile is moved |
| `${MONGODB_PORT:-27017}` etc. | When ports conflict on the host PC |
| Node services | When adding, removing, renaming, or changing node ports |

## Service Structure

All MADSci managers and nodes use the shared anchor:

```yaml
x-madsci-service: &madsci-service
  build: .
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

Each manager/node service uses `<<: *madsci-service` to inherit this configuration.
Do not repeat inherited settings unless the service has a real override.

A named bridge network must be declared:

```yaml
networks:
  madsci_net:
    driver: bridge
```

## Required Infrastructure Services

The following infrastructure services are required. They do not use the shared anchor, but they must be on `madsci_net`.

| Service | Image | Purpose |
|---------|-------|---------|
| `madsci_mongodb` | `mongo:8.0` | Event, experiment, data, workcell storage |
| `madsci_redis` | `redis:7.4` | Workcell and location manager state |
| `madsci_postgres` | `postgres:17` | Resource manager relational data |

## Manager Commands

Do not change manager commands.

| Service | command |
|---------|---------|
| `lab_manager` | `python -m madsci.squid.lab_server` |
| `event_manager` | `python -m madsci.event_manager.event_server` |
| `experiment_manager` | `python -m madsci.experiment_manager.experiment_server` |
| `resource_manager` | `python -m madsci.resource_manager.resource_server` |
| `data_manager` | `python -m madsci.data_manager.data_server` |
| `workcell_manager` | `python -m madsci.workcell_manager.workcell_server` |
| `location_manager` | `python -m madsci.location_manager.location_server` |

## depends_on Rules

Do not change manager `depends_on` unless the MADSci service topology changes.

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

## URL Rules

| Context | URL format |
|---------|------------|
| Container to other container | `http://<service_name>:<port>/` |
| Container's own bind address | `http://0.0.0.0:<port>/` |
| Windows to container | `http://localhost:<port>/` |

Rules:
- A service's own `*_SERVER_URL` must use `http://0.0.0.0:<port>/`
- URLs to other services must use Docker service names
- Do not use `localhost` for container-to-container communication
- Keep fixed Docker-internal URLs in `compose.yaml`, not `.env`
- `settings.yaml` may use `http://localhost:<port>/` for host-side access

## Manager Environment Rules

Use this table when creating or editing manager services.

| Service | Required environment |
|---------|----------------------|
| `lab_manager` | `LAB_SERVER_URL=http://0.0.0.0:8000/`, `EVENT_SERVER_URL=http://event_manager:8001/`, `EXPERIMENT_SERVER_URL=http://experiment_manager:8002/`, `RESOURCE_SERVER_URL=http://resource_manager:8003/`, `DATA_SERVER_URL=http://data_manager:8004/`, `WORKCELL_SERVER_URL=http://workcell_manager:8005/`, `LOCATION_SERVER_URL=http://location_manager:8006/` |
| `event_manager` | `EVENT_SERVER_URL=http://0.0.0.0:8001/`, `EVENT_MONGO_DB_URL=mongodb://madsci_mongodb:27017/` |
| `experiment_manager` | `EXPERIMENT_SERVER_URL=http://0.0.0.0:8002/`, `EXPERIMENT_MONGO_DB_URL=mongodb://madsci_mongodb:27017/`, `EVENT_SERVER_URL=http://event_manager:8001/` |
| `resource_manager` | `RESOURCE_SERVER_URL=http://0.0.0.0:8003/`, `RESOURCE_DB_URL=postgresql://madsci:madsci@madsci_postgres:5432/madsci_resources`, `EVENT_SERVER_URL=http://event_manager:8001/` |
| `data_manager` | `DATA_SERVER_URL=http://0.0.0.0:8004/`, `DATA_MONGO_DB_URL=mongodb://madsci_mongodb:27017/`, `EVENT_SERVER_URL=http://event_manager:8001/` |
| `workcell_manager` | `WORKCELL_SERVER_URL=http://0.0.0.0:8005/`, `WORKCELL_MONGO_DB_URL=mongodb://madsci_mongodb:27017/`, `WORKCELL_REDIS_HOST=madsci_redis`, `EVENT_SERVER_URL=http://event_manager:8001/`, `RESOURCE_SERVER_URL=http://resource_manager:8003/`, `DATA_SERVER_URL=http://data_manager:8004/`, `LOCATION_SERVER_URL=http://location_manager:8006/`, `WORKCELL_NODES=<node map>` |
| `location_manager` | `LOCATION_SERVER_URL=http://0.0.0.0:8006/`, `LOCATION_REDIS_HOST=madsci_redis`, `EVENT_SERVER_URL=http://event_manager:8001/`, `RESOURCE_SERVER_URL=http://resource_manager:8003/` |

Infrastructure services do not use manager URL environment variables.

## Node Environment Rules

New nodes can be added under `# ---- Nodes ----`.

Node template:

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
    - PYTHONPATH=/home/madsci/<lab_name>
    - NODE_NAME=<node_service_name>
    - NODE_MODULE_NAME=<module_name>
    - NODE_URL=http://0.0.0.0:<port>/
    - EVENT_SERVER_URL=http://event_manager:8001/
    - RESOURCE_SERVER_URL=http://resource_manager:8003/
    - DATA_SERVER_URL=http://data_manager:8004/
```

Rules:
- `NODE_NAME` must exactly match the key in `settings.yaml` `workcell_nodes`
- `NODE_URL` must use `http://0.0.0.0:<port>/`
- `settings.yaml` `workcell_nodes` should use `http://localhost:<port>/`
- Each node must use a unique port
- `command:` path must be relative to `working_dir`
- Always include `PYTHONPATH=<working_dir>`
- Always include `EVENT_SERVER_URL`
- Include `RESOURCE_SERVER_URL` if the node uses resources
- Include `DATA_SERVER_URL` if the node handles datapoints, files, plots, workflow outputs, or feed-forward data
- Add other manager URLs only if the node code explicitly uses those clients
- Update `WORKCELL_NODES` whenever a node is added, removed, renamed, or its port changes

## WORKCELL_NODES

`workcell_manager` runs inside Docker, so it must reach nodes using Docker service names.

```yaml
workcell_manager:
  environment:
    - WORKCELL_NODES={"<node_service_name>":"http://<node_service_name>:<port>/", "<node2>":"http://<node2>:<port>/"}
```

Rules:
- Key must exactly match the node service name and `NODE_NAME`
- Value must use the Docker service name as the hostname
- `settings.yaml` `workcell_nodes` entries remain `http://localhost:<port>/` for host-side access
- Update `WORKCELL_NODES` whenever a node is added, removed, renamed, or its port changes

## `.env` Rules

`.env` is loaded into every MADSci manager/node container.

Use `.env` only for:
- secrets
- local-only overrides
- lab-specific external device IPs
- values that must not be committed

Do not put these in `.env`:
- Docker-internal manager URLs
- MongoDB URLs
- PostgreSQL URLs
- Redis hosts
- `localhost` URLs for container services

## Lab Health Checks

The Lab Health panel sends health-check requests from inside the `lab_manager` container.
Manager URLs used by `lab_manager` must use Docker service names, not `localhost`.
