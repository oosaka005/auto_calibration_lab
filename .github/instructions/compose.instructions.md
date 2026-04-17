---
description: "Use when creating or editing compose.yaml. Covers service structure, volumes, restart policy, node configuration, and infrastructure requirements."
applyTo: "compose.yaml"
---

# compose.yaml Rules

## What Must NOT Be Changed (MADSci Framework Rules)

The following are fixed by the MADSci framework. Changing them will break the system:

- `network_mode: host` — required so all services can reach each other via `localhost`
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
  environment:
    - NODE_NAME=<node_service_name>
    - NODE_MODULE_NAME=<module_name>
    - NODE_URL=http://localhost:<port>
  command: python modules/<node_name>/<node_name>.py
  depends_on:
    - event_manager
```

Rules for node entries:
- `NODE_NAME` must exactly match the key in `workcell_nodes` in `settings.yaml`
- `NODE_URL` must exactly match the URL in `workcell_nodes` in `settings.yaml`
- Each node must use a unique port number
- `command:` path must be relative to `working_dir` and point to the node's Python file
- Always include `depends_on: - event_manager`

## Service Structure

All MADSci services use a shared anchor for common configuration:

```yaml
x-madsci-service: &madsci-service
  image: ghcr.io/ad-sdl/madsci:latest
  network_mode: host
  env_file:
    - ./.env
  volumes:
    - .:/home/madsci/<lab_name>
    - ./.madsci:/home/madsci/.madsci
  restart: unless-stopped
  working_dir: /home/madsci/<lab_name>
```

Each manager/node service uses `<<: *madsci-service` to inherit this configuration. `restart: unless-stopped` is inherited from this anchor — do NOT add it again individually to managers or nodes.

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

## network_mode

Use `network_mode: host` for all MADSci services. This allows services to communicate via `localhost` without port mapping. Infrastructure services do not use `network_mode: host` and require explicit `ports:` entries instead.
