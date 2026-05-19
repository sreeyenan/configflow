# Migration Guide: config-core v0.2.0

## Overview

Version 0.2.0 introduces powerful API factory functions that eliminate 80-90% of boilerplate CRUD code. This guide shows you how to migrate from custom endpoint handlers to the new factory-based approach.

**Benefits of migrating:**
- âœ… 80-90% less code to maintain
- âœ… Consistent API patterns across services
- âœ… Built-in validation, error handling, pagination
- âœ… Automatic version history support
- âœ… Easier to add new tables/configs

---

## Installation

### Update config-core

```bash
# Navigate to libs/configflow
cd analytic_ai/libs/config_core

# Install with API support
pip install -e .[api]

# Or install everything
pip install -e .[all]
```

### Verify Installation

```python
from configflow import create_crud_router, create_config_router
print("âœ… API modules loaded successfully!")
```

---

## Migration Path 1: Generic Table CRUD

### Before: Custom Handler (400+ lines)

**Old: `engine/handlers/widget_query_handler.py`** (430 lines)

```python
from fastapi import APIRouter, HTTPException, Depends, Body
from clickhouse_core import ClickHouseClient

router = APIRouter(prefix="/widget-query", tags=["widget-query"])

@router.post("/")
async def create_widget_query(request: WidgetQueryCreate, client: CHClient = Depends(...)):
    # 50+ lines of validation, duplicate checking, insertion logic
    ...

@router.get("/{widget_id}")
async def get_widget_query(widget_id: str, client: CHClient = Depends(...)):
    # 40+ lines of query, error handling, response formatting
    ...

@router.put("/{widget_id}")
async def update_widget_query(widget_id: str, request: WidgetQueryUpdate, client: CHClient = Depends(...)):
    # 60+ lines of existence check, UPDATE query, error handling
    ...

@router.delete("/{widget_id}")
async def delete_widget_query(widget_id: str, client: CHClient = Depends(...)):
    # 40+ lines of existence check, DELETE query, error handling
    ...

@router.get("/")
async def list_widget_queries(limit: int = 100, offset: int = 0, client: CHClient = Depends(...)):
    # 50+ lines of pagination, filtering, response formatting
    ...

@router.get("/{widget_id}/history")
async def get_widget_query_history(widget_id: str, client: CHClient = Depends(...)):
    # 40+ lines of history query, response formatting
    ...

# Total: 430 lines of code
```

### After: Factory-Based (50 lines)

**New: `engine/handlers/widget_query_handler.py`** (50 lines)

```python
from fastapi import Depends
from pydantic import BaseModel, Field
from configflow import create_crud_router
from engine.services.clickhouse_client import get_clickhouse_client

# Define models (same as before)
class WidgetQueryCreate(BaseModel):
    widget_id: str
    query: str
    confirmation: str = "trial"

class WidgetQueryUpdate(BaseModel):
    query: str | None = None
    confirmation: str | None = None

class WidgetQueryResponse(BaseModel):
    widget_id: str
    query: str
    confirmation: str
    created_at: str

# Custom validator (optional)
def validate_confirmation(value: str) -> str:
    valid_values = ["trial", "modified", "confirmed"]
    if value.lower() not in valid_values:
        raise ValueError(f"Must be one of: {', '.join(valid_values)}")
    return value.lower()

# Create router - ONE FUNCTION CALL replaces 400+ lines!
router = create_crud_router(
    table_name="widget_query",
    primary_key="widget_id",
    client_dependency=get_clickhouse_client,
    response_model=WidgetQueryResponse,
    create_model=WidgetQueryCreate,
    update_model=WidgetQueryUpdate,
    router_prefix="/widget-query",
    router_tags=["widget-query"],
    order_by="created_at DESC",
    filterable_fields=["confirmation"],
    enable_history=True,
    custom_validators={"confirmation": validate_confirmation},
)

# âœ… All endpoints automatically generated!
# Total: 50 lines of code (88% reduction)
```

### Migration Steps

1. **Backup old handler**
   ```bash
   mv widget_query_handler.py widget_query_handler_OLD.py
   ```

2. **Create new handler using factory**
   - Copy the Pydantic models from old file
   - Add `create_crud_router()` call with configuration
   - Remove all custom endpoint functions

3. **Test endpoints**
   ```bash
   # All these should work exactly as before
   curl http://localhost:8000/widget-query/
   curl http://localhost:8000/widget-query/widget_123
   curl -X POST http://localhost:8000/widget-query/ -d '...'
   ```

4. **Remove old file once verified**
   ```bash
   rm widget_query_handler_OLD.py
   ```

---

## Migration Path 2: Config Management

### Before: Custom Config Handler (150+ lines)

**Old: `engine/handlers/config_handler.py`** (150 lines)

```python
from fastapi import APIRouter, HTTPException, Depends, Body
from engine.services.config_service import ConfigService

router = APIRouter(prefix="/config", tags=["config"])

@router.get("/")
def get_full_config():
    return ConfigService.read()

@router.put("/")
def replace_config(new_cfg: RootConfig = Body(...)):
    return ConfigService.write(new_cfg.dict())

@router.patch("/")
def update_config(patch: Dict = Body(...)):
    return ConfigService.write(patch)

@router.get("/versions")
async def get_config_versions(client: CHClient = Depends(...)):
    rows = client.execute("""
        SELECT config_name, environment, version, updated_at
        FROM configs
        WHERE config_name = 'engine_config'  # âŒ Hardcoded!
        ORDER BY version DESC
    """)
    # ... 20 more lines of formatting
    ...

# ... many more endpoints
# Total: 150 lines of code
```

### After: Factory-Based (20 lines)

**New: `engine/handlers/config_handler.py`** (20 lines)

```python
from configflow import create_config_router
from engine.config import config_store, reload_settings
from engine.models.config_model import RootConfig

# Create router - ONE FUNCTION CALL replaces 150+ lines!
router = create_config_router(
    config_store=config_store,           # âœ… Uses 'engine_config' automatically
    config_model=RootConfig,
    reload_callback=reload_settings,     # Recreates connection pools
    router_prefix="/config",
    router_tags=["config"],
    enable_section_endpoints=True,
    enable_version_endpoints=True,
    enable_database_endpoints=True,
)

# âœ… All endpoints automatically generated!
# Total: 20 lines of code (87% reduction)
```

### Migration Steps

1. **Backup old handler**
   ```bash
   mv config_handler.py config_handler_OLD.py
   ```

2. **Create new handler using factory**
   - Import `create_config_router` from configflow
   - Import `config_store` from your service's config module
   - Add `create_config_router()` call
   - Remove all custom endpoint functions

3. **Test endpoints**
   ```bash
   # All these should work exactly as before
   curl http://localhost:8000/config/
   curl http://localhost:8000/config/versions
   curl http://localhost:8000/config/clickhouse
   curl -X PATCH http://localhost:8000/config/ -d '{"debug": true}'
   curl -X POST http://localhost:8000/config/reload
   ```

4. **Remove ConfigService wrapper** (optional)
   - If your `config_service.py` just wraps ConfigStore methods, you can remove it
   - The factory talks directly to ConfigStore

5. **Remove old file once verified**
   ```bash
   rm config_handler_OLD.py
   ```

---

## Migration Path 3: Adding Config to New Services

### ETL Service Example

**File: `etl_analytic_ai/etl/handlers/config_handler.py`** (NEW)

```python
from configflow import create_config_router
from etl.config import config_store  # Uses 'etl_config' in database

router = create_config_router(
    config_store=config_store,
    router_prefix="/config",
    router_tags=["etl-config"],
)

# âœ… ETL service now has full config management in 10 lines!
```

### NLQ Service Example

**File: `nlq_analytic_ai/nlq/handlers/config_handler.py`** (NEW)

```python
from configflow import create_config_router
from nlq.config import config_store  # Uses 'nlq_config' in database

router = create_config_router(
    config_store=config_store,
    router_prefix="/config",
    router_tags=["nlq-config"],
)

# âœ… NLQ service now has full config management in 10 lines!
```

---

## Adding New Tables

### Example: User Permissions Table

Want to add CRUD for a new `user_permissions` table? Just define models and call the factory!

```python
from configflow import create_crud_router
from pydantic import BaseModel

class PermissionCreate(BaseModel):
    user_id: str
    resource_id: str
    permission: str

class PermissionUpdate(BaseModel):
    permission: str

# Create router - 10 lines instead of 200+!
router = create_crud_router(
    table_name="user_permissions",
    primary_key=["user_id", "resource_id"],  # Composite key
    client_dependency=get_clickhouse_client,
    create_model=PermissionCreate,
    update_model=PermissionUpdate,
    filterable_fields=["user_id", "resource_id"],
)

# âœ… Full CRUD API in 10 lines!
# GET    /user-permissions/{user_id}/{resource_id}
# POST   /user-permissions/
# PUT    /user-permissions/{user_id}/{resource_id}
# DELETE /user-permissions/{user_id}/{resource_id}
```

---

## Verification Checklist

After migration, verify:

- [ ] All existing endpoints respond correctly
- [ ] Request validation works (try invalid data)
- [ ] 404 errors for missing records
- [ ] Pagination works (limit, offset parameters)
- [ ] Filtering works (if enabled)
- [ ] Version history works (if enabled)
- [ ] Custom validators execute (if configured)
- [ ] Reload callback executes (for config)
- [ ] Logs show proper messages

---

## Rollback Plan

If you encounter issues, you can easily rollback:

```bash
# Restore old handler
mv config_handler_OLD.py config_handler.py

# Restart service
systemctl restart engine-service
```

The old handlers are fully functional and backward compatible.

---

## Common Issues

### Issue: "Module 'config_core' has no attribute 'create_crud_router'"

**Solution**: FastAPI not installed. Install optional dependencies:
```bash
pip install config-core[api]
```

### Issue: "ConfigStore is not defined"

**Solution**: Make sure your service's config module has initialized ConfigStore:
```python
# engine/config.py
from configflow import ConfigStore

config_store = ConfigStore(
    initial_config=initial_config,
    clickhouse_params=clickhouse_params,
    config_name="engine_config",
)
```

### Issue: Custom endpoint logic missing

**Solution**: The factory handles standard CRUD. For custom logic, add endpoints to the router after creation:
```python
router = create_crud_router(...)

# Add custom endpoint
@router.post("/custom-action")
async def custom_action():
    ...
```

---

## Need Help?

- Check [README.md](README.md) for full API documentation
- See [CHANGELOG.md](CHANGELOG.md) for version history
- Look at example handlers in `engine_analytic_ai/engine/handlers/*_NEW.py`

---

## Summary

**Time to migrate one handler**: 15-30 minutes
**Code reduction**: 80-90%
**Risk**: Low (can easily rollback)
**Benefit**: Massive reduction in maintenance burden, consistent APIs

Start with one table, verify it works, then migrate others!
