# configflow â€” User Manual

**Version:** 0.2.2  
**Author:** sreeyenan  
**Release Date:** May 19, 2026

---

## Installation

### Basic Installation (Config Loading Only)

```cmd
pip install configuration_core
```

### With API Support (FastAPI + Pydantic)

```cmd
pip install configuration_core[api]
```

### With Everything (API + Cython Protection)

```cmd
pip install configuration_core[all]
```

Verify:
```python
from configflow import load_config_from_path, ConfigLoader, ConfigStore
print("configflow OK")

# If you installed [api]:
from configflow import create_crud_router, create_config_router
print("API features OK")
```

---

## Quick Reference

### Core Config Operations

**CRUD Operations:**
- `store.get_config()` â€” read cached config
- `store.get_config(refresh=True)` â€” reload from DB
- `store.patch_config({"key": "value"})` â€” merge partial update
- `store.update_config(new_config)` â€” replace entire config
- `store.delete_config()` â€” delete all versions

**Environment Variables:**
- JSON â†’ DB: stores raw `${VAR}` placeholders (unresolved)
- DB â†’ `get_config()`: returns resolved values from current env
- DB stores templates; each service resolves at runtime

### NEW: API Factories (v0.2.0)

**Generic CRUD:**
- `create_crud_router()` â€” Generate full CRUD API for any table
- `create_table_initializer()` â€” Generate CREATE TABLE SQL with MergeTree support
- `create_materialized_view_sql()` â€” Generate MATERIALIZED VIEW SQL

**Config Management:**
- `create_config_router()` â€” Generate config management API with versioning

---

## Table of Contents

1. [Core Functionality](#core-functionality)
   - File-based Config Loading
   - ClickHouse-backed ConfigStore
2. [API Features (NEW)](#api-features-new)
   - Generic CRUD API Factory
   - Config Management API
3. [ClickHouse Table Creation](#clickhouse-table-creation-new)
   - MergeTree Engines
   - Materialized Views
   - Advanced Features
4. [Complete Examples](#complete-examples)

---

---

# PART 1: Core Functionality

## What This Library Does

`configflow` provides four main capabilities:

1. **File-based config loading** â€” load a JSON config file, auto-resolving `${ENV_VAR}` placeholders
2. **ClickHouse-backed config store** â€” store and manage versioned configs in a ClickHouse table
3. **Generic CRUD API factory** (NEW) â€” generate full REST APIs for any ClickHouse table
4. **Config management API** (NEW) â€” standardized config endpoints across all services

---

## âš¡ Recommended Usage Pattern

> **Recommendation:** Use `load_config_from_path` only once at **service startup** to read connection
> parameters from the JSON file. After that, always use `ConfigStore.get_config()` to get live config
> from the database â€” never read the JSON file again at runtime.

```python
from pathlib import Path
from configflow import load_config_from_path, ConfigStore

# âœ… Step 1: Load the JSON file ONCE at startup (bootstrap only)
#    This reads connection params and initial config values from disk.
cfg = load_config_from_path(Path("engine/config/config.json"))

# âœ… Step 2: Create ConfigStore â€” from here on, live config comes from DB
#    If no config exists in DB yet, it seeds the DB with cfg automatically.
store = ConfigStore(
    initial_config=cfg,
    clickhouse_params=cfg["clickhouse"],   # host/port/user/pass from the file
    config_name="engine_config",
    environment="production",
)

# âœ… Step 3: Always get live config from DB (not the file)
live_cfg = store.get_config()   # reads from ClickHouse (cached after first call)
print(live_cfg["threshold"])

# âœ… Step 4: Update config at runtime â€” no file changes needed
store.patch_config({"threshold": 0.95})

# âŒ AVOID: reading the JSON file repeatedly at runtime
# cfg = load_config_from_path(...)  â† do NOT call this after startup
```

**Why this pattern?**

| | JSON file | `ConfigStore` (DB) |
|---|---|---|
| When to use | Startup only | All runtime reads |
| Supports live updates | âŒ No â€” requires redeploy | âœ… Yes â€” patch at runtime |
| Versioned history | âŒ No | âœ… Yes â€” full version history |
| Shared across pods | âŒ No â€” each pod reads its own file | âœ… Yes â€” all pods share one DB |
| `${ENV_VAR}` resolution | âœ… Yes (at file-read time) | âœ… Stored raw, resolved on read |
| Environment portability | âŒ File contains specific values | âœ… Same DB config works across all envs |

---

## Public API

| Symbol | Type | Purpose |
|---|---|---|
| `load_config_from_path` | function | Load a JSON file into a dict |
| `load_json_config` | function | Load JSON with automatic path fallback |
| `ConfigLoader` | class | Object-oriented wrapper for `load_json_config` |
| `ConfigStore` | class | Versioned config store backed by ClickHouse |
| `resolve_env_vars` | function | Resolve `${VAR}` placeholders in any dict/string |

---

## 1. `load_config_from_path`

Loads a JSON file from a given path. All `${VAR}` and `${VAR:default}` placeholders in values are resolved from environment variables.

```python
from pathlib import Path
from configflow import load_config_from_path

cfg = load_config_from_path(Path("myservice/config/config.json"))
print(cfg)
# {'host': 'localhost', 'port': 9000, ...}
```

**Returns:** `dict` â€” empty `{}` if file does not exist.

---

## 2. `load_json_config`

Loads a JSON config with fallback logic:
1. Try the path you provide (if any)
2. Fall back to `config.json` in current working directory

```python
from configflow import load_json_config

# With explicit path
cfg = load_json_config(config_path="engine/config/config.json")

# Auto-discover from cwd
cfg = load_json_config()

# Specify a working directory to search in
from pathlib import Path
cfg = load_json_config(cwd=Path("/app/engine"))
```

---

## 3. `ConfigLoader`

Object-oriented wrapper â€” useful when passing the loader around as a dependency.

```python
from configflow import ConfigLoader

loader = ConfigLoader(config_path="engine/config/config.json")
cfg = loader.load()
print(cfg["clickhouse"]["host"])
```

---

## 4. `resolve_env_vars`

Recursively walks any dict/list/string and replaces `${VAR}` or `${VAR:default}` with the actual environment variable value.

```python
from configflow import resolve_env_vars
import os

os.environ["DB_HOST"] = "prod-server"

raw = {
    "host": "${DB_HOST}",
    "port": "${DB_PORT:9000}",      # uses default 9000 if DB_PORT not set
    "nested": {"name": "${APP_NAME:myapp}"}
}

resolved = resolve_env_vars(raw)
# {'host': 'prod-server', 'port': '9000', 'nested': {'name': 'myapp'}}
```

**Supported syntax:**

| Placeholder | Behaviour |
|---|---|
| `${VAR}` | Replaced with env var value; unchanged if not set |
| `${VAR:default}` | Replaced with env var value; uses `default` if not set |

---

## 5. `ConfigStore`

Stores versioned configurations in a ClickHouse `configs` table. On first use it seeds the table with your initial config. Subsequent calls load from the database.

### Constructor

```python
ConfigStore(
    initial_config: dict,          # used to seed if no config exists in DB
    clickhouse_params: dict,       # host/port/database/username/password
    backend: str = "clickhouse",   # only "clickhouse" supported
    config_name: str = "engine_config",
    environment: str = "default",
)
```

**Default behavior:**

- **`seed_db=True`** â€” when seeding (first run with no DB row) the library stores the **raw
  JSON payload** you passed as `initial_config` into ClickHouse. Placeholders like
  `${VAR}` are **preserved in the DB record**; the DB stores the original JSON as
  authored (unresolved).
  
- **`resolve_on_read=True`** â€” when loading payloads from the DB the library **resolves
  `${VAR}` / `${VAR:default}` placeholders** against the current process environment
  before returning/caching the value. This means **callers always get resolved values** at
  runtime even though the DB stores raw placeholders.

**Key insight:** The DB acts as a template store (preserves placeholders), and each service
reads + resolves the template against its own environment at runtime.

**Optional flags for special cases:**

- Set `seed_db=False` to skip writing to DB on startup (useful for unit tests, CI, read-only deployments)
- Set `resolve_on_read=False` to get raw placeholders from DB (useful for debugging, config validation tools)

### Basic Usage

```python
from configflow import ConfigStore

store = ConfigStore(
    initial_config={"feature_x": True, "threshold": 0.9},
    clickhouse_params={
        "host": "localhost",
        "port": 9000,
        "database": "default",
        "username": "admin",
        "password": "admin",
    },
    config_name="engine_config",
    environment="production",
)

# Read config
cfg = store.get_config()
print(cfg["threshold"])  # 0.9

# Force re-read from DB (skip cache)
cfg = store.get_config(refresh=True)
```

### Methods

#### `get_config(refresh=False) â†’ dict`
Returns the current config. Uses cache unless `refresh=True`.

```python
cfg = store.get_config()
cfg = store.get_config(refresh=True)  # re-reads from ClickHouse
```

#### `create_config(payload: dict)`
Inserts a fresh config (version 1) into the database.

```python
store.create_config({"threshold": 0.95, "debug": False})
```

#### `update_config(payload: dict)`
Replaces the latest version's payload entirely.

```python
store.update_config({"threshold": 0.99, "debug": True})
```

#### `patch_config(patch: dict) â†’ dict`
Deep-merges the patch into the current config (only updates the keys you provide).

```python
# Current: {"threshold": 0.9, "debug": False, "retries": 3}
updated = store.patch_config({"debug": True})
# Result:  {"threshold": 0.9, "debug": True, "retries": 3}
```

#### `update_config_version(version: int, payload: dict)`
Updates a specific historical version.

```python
store.update_config_version(version=2, payload={"threshold": 0.8})
```

#### `patch_config_version(version: int, patch: dict) â†’ dict`
Deep-merges patch into a specific historical version.

```python
store.patch_config_version(version=1, patch={"retries": 5})
```

#### `delete_config()`
Deletes all versions of the config for this `config_name` + `environment`.

```python
store.delete_config()
```

---

## CRUD Operations Summary

`ConfigStore` provides full CRUD (Create, Read, Update, Delete) operations for managing configs:

| Operation | Method | Description |
|---|---|---|
| **Read** | `get_config()` | Get cached config |
| **Reload/Refresh** | `get_config(refresh=True)` | Force re-read from DB, bypass cache |
| **Create** | `create_config(payload)` | Insert new config (version 1) |
| **Update** | `update_config(payload)` | Replace entire latest config |
| **Patch** | `patch_config(patch)` | Merge partial changes into latest config |
| **Delete** | `delete_config()` | Remove all versions for this config_name + environment |
| **Update Version** | `update_config_version(v, payload)` | Replace a specific historical version |
| **Patch Version** | `patch_config_version(v, patch)` | Merge changes into specific version |

### Reload/Refresh Config

When you need to pick up changes made to the DB (e.g., by another service or manual update):

```python
# Initial read (cached)
cfg = store.get_config()

# ... later, after DB is updated externally ...

# Force reload from DB
fresh_cfg = store.get_config(refresh=True)  # clears cache, re-reads DB, resolves env vars
```

**What happens on reload:**
1. Clears in-memory cache
2. Re-runs DB query to fetch latest payload
3. Resolves any `${VAR}` placeholders against **current** environment variables
4. Updates cache with new values

---

## How Environment Variable Resolution Works

Understanding when placeholders are resolved vs stored:

### 1ï¸âƒ£ First Run (Seeding): JSON â†’ DB

**Your JSON file** (with placeholders):
```json
{
  "clickhouse": {
    "host": "${CH_HOST:localhost}",
    "user": "${CH_USER}"
  },
  "threshold": 0.9
}
```

**Environment at startup:**
```bash
CH_HOST=prod-server
CH_USER=admin
```

**What gets stored in ClickHouse `configs` table:**
```json
{
  "clickhouse": {
    "host": "${CH_HOST:localhost}",
    "user": "${CH_USER}"
  },
  "threshold": 0.9
}
```

âœ… **Placeholders are preserved in the DB** (raw JSON, not resolved values)

### 2ï¸âƒ£ Reading from DB: `get_config()` Returns Resolved Values

**What's in the DB:**
```json
{"clickhouse": {"host": "${CH_HOST:localhost}", "user": "${CH_USER}"}}
```

**Environment at runtime (second deployment):**
```bash
CH_HOST=new-server
CH_USER=alice
```

**What `store.get_config()` returns:**
```json
{"clickhouse": {"host": "new-server", "user": "alice"}}
```

âœ… **Placeholders are resolved on read** (with `resolve_on_read=True` default)

### Why This Design?

| Benefit | Explanation |
|---|---|
| **Environment independence** | Same DB config works across dev/staging/prod with different env vars |
| **Portability** | Export DB config to any environment; it adapts to local env vars |
| **Security** | Secrets (passwords) stay in environment variables, not persisted in DB |
| **Flexibility** | Change env vars without updating DB records |

### Example: Multi-Environment Usage

```python
# Production deployment
os.environ["CH_HOST"] = "prod-clickhouse.internal"
os.environ["CH_USER"] = "prod_user"
store = ConfigStore(initial_config=cfg, clickhouse_params=params)
cfg = store.get_config()  # returns prod values

# Staging deployment (same DB, different env)
os.environ["CH_HOST"] = "staging-clickhouse.internal"
os.environ["CH_USER"] = "staging_user"
store = ConfigStore(initial_config=cfg, clickhouse_params=params)
cfg = store.get_config()  # returns staging values from same DB record
```

---

## Environment Variable Overrides for ConfigStore

Instead of passing `clickhouse_params`, you can set these environment variables:

| Variable | Description |
|---|---|
| `CLICKHOUSE_HOST` | ClickHouse hostname |
| `CLICKHOUSE_PORT` | Port (default 9000) |
| `CLICKHOUSE_DATABASE` | Database name |
| `CLICKHOUSE_USERNAME` | Username |
| `CLICKHOUSE_PASSWORD` | Password |
| `DEFAULT_BACKEND` | Backend type (only `clickhouse`) |
| `ENVIRONMENT` | Config environment name (e.g. `production`) |

---

## Error Handling

```python
from configflow import ConfigStore

try:
    store = ConfigStore(initial_config={}, clickhouse_params={...})
    cfg = store.get_config()
except RuntimeError as exc:
    print(f"Config error: {exc}")
```

---

# PART 2: API Features (NEW in v0.2.0)

## 1. Generic CRUD API Factory

### Overview

The `create_crud_router()` function generates a complete REST API for any ClickHouse table with:
- âœ… Full CRUD operations (Create, Read, Update, Delete)
- âœ… Pagination and filtering
- âœ… Version history (optional)
- âœ… Request validation (Pydantic models)
- âœ… Comprehensive error handling
- âœ… Composite primary key support

**Code Reduction**: Replace 200-400 lines of custom endpoint code with one function call.

### Basic Usage

```python
from fastapi import FastAPI, Depends
from pydantic import BaseModel
from configflow import create_crud_router
from engine.services.clickhouse_client import get_clickhouse_client

# Define Pydantic models
class WidgetCreate(BaseModel):
    widget_id: str
    name: str
    value: float

class WidgetUpdate(BaseModel):
    name: str | None = None
    value: float | None = None

class WidgetResponse(BaseModel):
    widget_id: str
    name: str
    value: float
    created_at: str

# Create router - ONE FUNCTION CALL
router = create_crud_router(
    table_name="widgets",
    primary_key="widget_id",
    client_dependency=get_clickhouse_client,
    response_model=WidgetResponse,
    create_model=WidgetCreate,
    update_model=WidgetUpdate,
)

# Mount in FastAPI app
app = FastAPI()
app.include_router(router, prefix="/widgets")
```

**Generated Endpoints:**
```
POST   /widgets/                  - Create new record
GET    /widgets/                  - List all (with pagination & filtering)
GET    /widgets/{widget_id}       - Get by ID
PUT    /widgets/{widget_id}       - Update record
DELETE /widgets/{widget_id}       - Delete record
```

### Advanced Configuration

```python
router = create_crud_router(
    # Required
    table_name="events",
    primary_key="event_id",                    # Or ["user_id", "event_id"] for composite
    client_dependency=get_clickhouse_client,
    
    # Pydantic models (optional)
    response_model=EventResponse,
    create_model=EventCreate,
    update_model=EventUpdate,
    list_model=EventListResponse,
    
    # Router settings
    router_prefix="/events",
    router_tags=["events"],
    
    # Query & filtering
    order_by="timestamp DESC",
    filterable_fields=["event_type", "user_id"],
    
    # Features
    enable_history=True,
    timestamp_field="timestamp",
    
    # Custom validation
    custom_validators={
        "event_type": validate_event_type,
        "email": validate_email,
    },
)
```

### Filtering & Pagination

```bash
# List with filters
GET /events/?event_type=click&user_id=123&limit=50&offset=0

# Pagination
GET /events/?limit=100&offset=200
```

### Composite Primary Keys

```python
router = create_crud_router(
    table_name="user_permissions",
    primary_key=["user_id", "resource_id"],  # Composite key
    ...
)

# Generated endpoints:
# GET    /user-permissions/{user_id}/{resource_id}
# PUT    /user-permissions/{user_id}/{resource_id}
# DELETE /user-permissions/{user_id}/{resource_id}
```

### Version History

```python
router = create_crud_router(
    table_name="widget_query",
    primary_key="widget_id",
    enable_history=True,
    timestamp_field="created_at",
    ...
)

# Adds endpoint:
# GET /widget-query/{widget_id}/history
```

### Custom Validators

```python
def validate_email(email: str) -> str:
    if "@" not in email:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid email")
    return email.lower()

router = create_crud_router(
    table_name="users",
    custom_validators={"email": validate_email},
    ...
)
```

---

## 2. Config Management API Factory

### Overview

The `create_config_router()` function generates a standardized config management API for `ConfigStore` instances:
- âœ… Full config CRUD
- âœ… Section-based updates
- âœ… Version management
- âœ… Reload callbacks (e.g., recreate connection pools)
- âœ… Database introspection

### Basic Usage

```python
from configflow import ConfigStore, create_config_router
from engine.config import reload_settings
from engine.models.config_model import RootConfig

# ConfigStore already initialized
store = ConfigStore(
    initial_config=config,
    clickhouse_params=config["clickhouse"],
    config_name="engine_config",
)

# Create router - ONE FUNCTION CALL
router = create_config_router(
    config_store=store,
    config_model=RootConfig,             # Optional Pydantic validation
    reload_callback=reload_settings,     # Optional callback
)

# Mount in FastAPI app
app.include_router(router, prefix="/config")
```

**Generated Endpoints:**
```
# Core CRUD
GET    /config/                          - Get full config
PUT    /config/                          - Replace full config
PATCH  /config/                          - Merge partial update
POST   /config/reload                    - Reload from database

# Section Management
GET    /config/{section}                 - Get specific section
PUT    /config/{section}                 - Update specific section
DELETE /config/{section}                 - Delete section

# Version Management
GET    /config/versions                  - List all versions
GET    /config/versions/{version}        - Get specific version
PUT    /config/versions/{version}        - Update version in-place
PATCH  /config/versions/{version}        - Patch version in-place

# Database Introspection
GET    /config/database/current          - Get current DB config
```

### Usage Examples

```bash
# Get full config
GET /config/

# Update config (merge)
PATCH /config/
{"logging": {"level": "DEBUG"}, "debug": true}

# Update specific section
PUT /config/clickhouse
{"host": "new-host", "port": 9000}

# Reload config (triggers callback)
POST /config/reload

# List versions
GET /config/versions

# Get specific version
GET /config/versions/5
```

### Reload Callback

```python
def reload_settings():
    """Called after config changes - recreate connection pools, etc."""
    global db_clients_pool
    db_clients_pool = create_connection_pool(new_config)
    logger.info("Connection pools recreated")

router = create_config_router(
    config_store=store,
    reload_callback=reload_settings,  # Executed after PUT/PATCH/reload
)
```

### Authentication

```python
from fastapi import Depends

def validate_master(token: str = Header(...)):
    if token != os.getenv("MASTER_TOKEN"):
        raise HTTPException(status_code=403, detail="Forbidden")
    return True

router = create_config_router(
    config_store=store,
    auth_dependency=validate_master,  # Applied to all endpoints
)
```

### Multi-Service Setup

Each service manages its own config using the same API pattern:

```python
# engine_analytic_ai/engine/handlers/config_handler.py
store = ConfigStore(..., config_name="engine_config")
router = create_config_router(store)

# etl_analytic_ai/etl/handlers/config_handler.py
store = ConfigStore(..., config_name="etl_config")
router = create_config_router(store)

# nlq_analytic_ai/nlq/handlers/config_handler.py
store = ConfigStore(..., config_name="nlq_config")
router = create_config_router(store)

# âœ… Same API, different configs in same ClickHouse table
```

---

# PART 3: ClickHouse Table Creation (NEW in v0.2.0)

## 1. Table Initialization Helper

### Overview

The `create_table_initializer()` function generates CREATE TABLE SQL with full support for:
- âœ… All MergeTree engine variants
- âœ… Partitioning
- âœ… Primary keys and ORDER BY
- âœ… TTL policies
- âœ… Table settings
- âœ… Proper ClickHouse syntax

### Basic MergeTree Table

```python
from configflow import create_table_initializer

sql = create_table_initializer(
    table_name="events",
    columns={
        "event_id": "String",
        "user_id": "String",
        "timestamp": "DateTime",
        "data": "String",
    },
    engine="MergeTree()",
    order_by=["user_id", "timestamp"],
)

# Execute with ClickHouse client
client.execute(sql)
```

**Generated SQL:**
```sql
CREATE TABLE IF NOT EXISTS events
(
    event_id String,
    user_id String,
    timestamp DateTime,
    data String
)
ENGINE = MergeTree()
ORDER BY (user_id, timestamp)
```

### ReplacingMergeTree (Deduplication)

```python
sql = create_table_initializer(
    table_name="user_profiles",
    columns={
        "user_id": "String",
        "name": "String",
        "email": "String",
        "updated_at": "DateTime",
    },
    engine="ReplacingMergeTree(updated_at)",  # Keeps newest version
    order_by="user_id",
    partition_by="toYYYYMM(updated_at)",
)
```

**Generated SQL:**
```sql
CREATE TABLE IF NOT EXISTS user_profiles
(
    user_id String,
    name String,
    email String,
    updated_at DateTime
)
ENGINE = ReplacingMergeTree(updated_at)
PARTITION BY toYYYYMM(updated_at)
ORDER BY (user_id)
```

### AggregatingMergeTree (Pre-aggregation)

```python
sql = create_table_initializer(
    table_name="user_stats",
    columns={
        "user_id": "String",
        "event_count": "AggregateFunction(count, UInt64)",
        "last_seen": "AggregateFunction(max, DateTime)",
        "date": "Date",
    },
    engine="AggregatingMergeTree()",
    order_by=["user_id", "date"],
    partition_by="toYYYYMM(date)",
)
```

### SummingMergeTree (Summing Metrics)

```python
sql = create_table_initializer(
    table_name="metrics",
    columns={
        "metric_name": "String",
        "timestamp": "DateTime",
        "value": "Float64",
    },
    engine="SummingMergeTree()",
    order_by=["metric_name", "timestamp"],
    partition_by="toYYYYMM(timestamp)",
)
```

### With TTL (Time-to-Live)

```python
sql = create_table_initializer(
    table_name="logs",
    columns={
        "log_id": "String",
        "message": "String",
        "timestamp": "DateTime",
    },
    engine="MergeTree()",
    order_by="timestamp",
    ttl="timestamp + INTERVAL 90 DAY",  # Auto-delete after 90 days
    settings={"index_granularity": 8192},
)
```

**Generated SQL:**
```sql
CREATE TABLE IF NOT EXISTS logs
(
    log_id String,
    message String,
    timestamp DateTime
)
ENGINE = MergeTree()
ORDER BY (timestamp)
TTL timestamp + INTERVAL 90 DAY
SETTINGS index_granularity = 8192
```

### Advanced Example: All Features

```python
sql = create_table_initializer(
    table_name="user_events",
    columns={
        "user_id": "String",
        "event_id": "String",
        "event_type": "LowCardinality(String)",  # Memory optimization
        "timestamp": "DateTime",
        "properties": "String",
        "country": "LowCardinality(String)",
    },
    engine="ReplacingMergeTree(timestamp)",
    order_by=["user_id", "timestamp"],
    partition_by="toYYYYMM(timestamp)",
    primary_key=["user_id"],  # Optional: different from ORDER BY
    ttl="timestamp + INTERVAL 365 DAY",
    settings={
        "index_granularity": 8192,
        "ttl_only_drop_parts": 1,  # Drop whole partitions, not individual rows
    },
    comment="User events with 1-year retention",
)
```

---

## 2. Materialized Views

### Overview

The `create_materialized_view_sql()` function generates MATERIALIZED VIEW SQL for:
- âœ… Real-time aggregations
- âœ… Pre-computed statistics
- âœ… Data transformations
- âœ… Automatic updates on INSERT

### Basic Materialized View

```python
from configflow import create_materialized_view_sql

# Target table (must exist first)
target_sql = create_table_initializer(
    table_name="user_stats",
    columns={
        "user_id": "String",
        "event_count": "UInt64",
        "last_seen": "DateTime",
    },
    engine="SummingMergeTree()",
    order_by="user_id",
)
client.execute(target_sql)

# Materialized view
mv_sql = create_materialized_view_sql(
    view_name="user_stats_mv",
    target_table="user_stats",
    select_query="""
        SELECT 
            user_id,
            count() as event_count,
            max(timestamp) as last_seen
        FROM events
        GROUP BY user_id
    """,
    populate=False,  # Don't backfill existing data
)
client.execute(mv_sql)
```

**Generated SQL:**
```sql
CREATE MATERIALIZED VIEW IF NOT EXISTS user_stats_mv
TO user_stats
AS
SELECT 
    user_id,
    count() as event_count,
    max(timestamp) as last_seen
FROM events
GROUP BY user_id
```

**How it works:**
- Every INSERT to `events` table automatically triggers the SELECT query
- Results are inserted into `user_stats` target table
- Real-time aggregation with no manual updates needed

### With POPULATE (Backfill Existing Data)

```python
mv_sql = create_materialized_view_sql(
    view_name="daily_metrics_mv",
    target_table="daily_metrics",
    select_query="""
        SELECT 
            toDate(timestamp) as date,
            count() as total_events,
            uniq(user_id) as unique_users
        FROM events
        GROUP BY date
    """,
    populate=True,  # âœ… Backfill with existing data
)
```

### Inline Engine (No Target Table)

```python
mv_sql = create_materialized_view_sql(
    view_name="event_summary_mv",
    target_table=None,  # No target
    engine="AggregatingMergeTree() ORDER BY (event_type, date)",
    select_query="""
        SELECT 
            event_type,
            toDate(timestamp) as date,
            countState() as count
        FROM events
        GROUP BY event_type, date
    """,
)
```

---

## 3. Complete ClickHouse Table Setup Example

### Scenario: Event Tracking System

```python
from configflow import (
    create_table_initializer,
    create_materialized_view_sql,
    create_crud_router
)
from clickhouse_core import ClickHouseClient

client = ClickHouseClient(config)

# Step 1: Create main events table
events_table_sql = create_table_initializer(
    table_name="events",
    columns={
        "event_id": "String",
        "user_id": "String",
        "event_type": "LowCardinality(String)",
        "timestamp": "DateTime",
        "properties": "String",
    },
    engine="MergeTree()",
    order_by=["user_id", "timestamp"],
    partition_by="toYYYYMM(timestamp)",
    ttl="timestamp + INTERVAL 90 DAY",
    settings={"index_granularity": 8192},
)
client.execute(events_table_sql)

# Step 2: Create aggregation target table
user_stats_table_sql = create_table_initializer(
    table_name="user_stats",
    columns={
        "user_id": "String",
        "event_count": "UInt64",
        "last_event_type": "String",
        "last_seen": "DateTime",
        "date": "Date",
    },
    engine="SummingMergeTree()",
    order_by=["user_id", "date"],
)
client.execute(user_stats_table_sql)

# Step 3: Create materialized view for real-time aggregation
user_stats_mv_sql = create_materialized_view_sql(
    view_name="user_stats_mv",
    target_table="user_stats",
    select_query="""
        SELECT 
            user_id,
            count() as event_count,
            argMax(event_type, timestamp) as last_event_type,
            max(timestamp) as last_seen,
            toDate(timestamp) as date
        FROM events
        GROUP BY user_id, date
    """,
)
client.execute(user_stats_mv_sql)

# Step 4: Create CRUD API for events table
from pydantic import BaseModel

class EventCreate(BaseModel):
    event_id: str
    user_id: str
    event_type: str
    properties: str

events_router = create_crud_router(
    table_name="events",
    primary_key="event_id",
    client_dependency=get_clickhouse_client,
    create_model=EventCreate,
    order_by="timestamp DESC",
    filterable_fields=["user_id", "event_type"],
    enable_history=True,
)

# Step 5: Create CRUD API for user stats (read-only)
user_stats_router = create_crud_router(
    table_name="user_stats",
    primary_key=["user_id", "date"],
    client_dependency=get_clickhouse_client,
    create_model=None,  # No create endpoint (auto-populated by MV)
    order_by="date DESC",
    filterable_fields=["user_id"],
)

# Mount routers
app.include_router(events_router, prefix="/events")
app.include_router(user_stats_router, prefix="/user-stats")
```

**Result:**
- âœ… Main events table with partitioning and TTL
- âœ… Real-time user statistics via materialized view
- âœ… Full REST API for events (POST, GET, PUT, DELETE)
- âœ… Read-only REST API for user stats
- âœ… Automatic aggregation on every INSERT
- âœ… 90-day data retention

---

# PART 4: Core Config Functionality

## Complete Example

```python
from pathlib import Path
from configflow import load_config_from_path, ConfigStore

# Step 1: Load base config from file
cfg = load_config_from_path(Path("engine/config/config.json"))

# Step 2: Create a ConfigStore using the clickhouse block from that file
store = ConfigStore(
    initial_config=cfg,
    clickhouse_params=cfg["clickhouse"],
    config_name="engine_config",
    environment="production",
)

# Step 3: Use the config
live_cfg = store.get_config()
print(live_cfg)

# Step 4: Update a single key without touching others
store.patch_config({"threshold": 0.95})
```
