# configflow

Shared config loader, environment variable resolver, and generic CRUD API factory for Analytic AI services.

## What it does

- **File-based config loading** – load JSON config files with automatic `${ENV_VAR}` placeholder resolution
- **ClickHouse-backed config store** – versioned config management with live updates (no redeployment needed)
- **Generic CRUD API factory** – create full REST APIs for any ClickHouse table in one function call
- **Config Management API** – standardized config endpoints with versioning and reload support
- **Environment variable resolution** – supports `${VAR}` and `${VAR:default}` patterns
- **ClickHouse table utilities** – create tables with MergeTree engines, materialized views, projections

## Installation

### Basic Installation (Config Loading Only)

```bash
pip install configuration_core
```

### With API Support (FastAPI + Pydantic)

```bash
pip install configuration_core[api]
```

### With Everything (API + Cython Protection)

```bash
pip install configuration_core[all]
```

## Quick Start

### File-based Config Loading

```python
from pathlib import Path
from configflow import load_config_from_path

# Load JSON config with automatic ${ENV_VAR} resolution
config = load_config_from_path(Path("config/config.json"))
print(config["database"]["host"])  # Resolved from environment
```

### ClickHouse-backed Config Store

```python
from configflow import ConfigStore, load_config_from_path

# Load initial config from file (once at startup)
cfg = load_config_from_path(Path("config/config.json"))

# Create versioned config store backed by ClickHouse
store = ConfigStore(
    initial_config=cfg,
    clickhouse_params=cfg["clickhouse"],
    config_name="my_service_config",
    environment="production",
)

# Get live config from database (cached after first call)
live_config = store.get_config()

# Update config at runtime (no redeployment needed)
store.patch_config({"threshold": 0.95})

# Reload from database
fresh_config = store.get_config(refresh=True)
```

### Generic CRUD API (NEW in v0.2.0)

```python
from fastapi import FastAPI
from configflow import create_crud_router
from clickhouse_core import ClickHouseConfig, get_client

app = FastAPI()

# Create full CRUD API for any ClickHouse table
crud_router = create_crud_router(
    table_name="users",
    clickhouse_client=get_client(ClickHouseConfig.from_env()),
    primary_key="user_id",
)

app.include_router(crud_router, prefix="/api/users", tags=["Users"])

# Now you have:
# GET /api/users?limit=10&offset=0
# GET /api/users/{user_id}
# POST /api/users
# PUT /api/users/{user_id}
# DELETE /api/users/{user_id}
```

### Config Management API (NEW in v0.2.0)

```python
from fastapi import FastAPI
from configflow import create_config_router, ConfigStore

app = FastAPI()

store = ConfigStore(
    initial_config=cfg,
    clickhouse_params=cfg["clickhouse"],
    config_name="service_config",
)

# Add standardized config endpoints
config_router = create_config_router(store)
app.include_router(config_router, prefix="/api/config", tags=["Config"])

# Provides:
# GET /api/config - Get current config
# PATCH /api/config - Partial update
# PUT /api/config - Full replace
# POST /api/config/reload - Reload from database
```

## Dependencies

- **clickhouse-core** (≥0.2.4) – shared ClickHouse connectivity library
- **fastapi** (≥0.100.0) – optional, for API features
- **pydantic** (≥2.0.0) – optional, for API features

## Configuration

Environment variables for ClickHouse connection (inherited from clickhouse-core):

- `CLICKHOUSE_HOST`
- `CLICKHOUSE_PORT`
- `CLICKHOUSE_DATABASE`
- `CLICKHOUSE_USERNAME`
- `CLICKHOUSE_PASSWORD`
- `CLICKHOUSE_PROTOCOL` (tcp|http)
- `CLICKHOUSE_SECURE` (true/false)

## Documentation

For detailed usage, API reference, and advanced features, see:

- **[User Manual](configflow_USER_MANUAL.md)** – comprehensive guide with examples
- **[Environment Variables](ENVIRONMENT_VARIABLES.md)** – all supported environment variables
- **[ClickHouse Support](CLICKHOUSE_SUPPORT.md)** – ClickHouse-specific features
- **[Migration Guide](MIGRATION_GUIDE.md)** – upgrading from previous versions
- **[Changelog](CHANGELOG.md)** – version history and changes

## Key Features

### Recommended Usage Pattern

> Use `load_config_from_path` only once at **service startup** to read connection parameters.  
> After that, always use `ConfigStore.get_config()` to get live config from the database.

**Why?**

| | JSON file | ConfigStore (DB) |
|---|---|---|
| When to use | Startup only | All runtime reads |
| Supports live updates | ❌ No – requires redeploy | ✅ Yes – patch at runtime |
| Versioned history | ❌ No | ✅ Yes – full version history |
| Shared across pods | ❌ No – each pod reads its own file | ✅ Yes – all pods share one DB |

### Environment Variable Resolution

- Supports `${VAR}` and `${VAR:default}` patterns in JSON config files
- Variables are resolved at config read time
- DB stores raw placeholders; resolution happens on each `get_config()` call
- Same config works across all environments (dev/staging/prod)

### Generic CRUD API Factory

- Generate full REST APIs for any ClickHouse table
- Automatic query building with filters, pagination, sorting
- Type-safe Pydantic models generated from table schema
- Customizable routes and permissions

## License

See [LICENSE](LICENSE) file for details.

## Author

**sreeyenan** (sreeyenanek@gmail.com)

## Version

Current version: **0.2.2**

