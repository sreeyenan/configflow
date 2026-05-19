"""
Generic CRUD API Factory for Storage Backends

This module provides reusable FastAPI router factories for common CRUD operations
on any storage backend (ClickHouse, DuckDB, etc.). Supports:
- List with filtering and pagination
- Get by ID/primary key
- Create new records
- Update existing records
- Delete records
- Backend-agnostic through adapter pattern

Usage:
    from config_core import create_crud_router, ClickHouseBackend
    from clickhouse_core import ClickHouseClient
    
    client = ClickHouseClient(config)
    backend = ClickHouseBackend(client, primary_key="widget_id")
    
    router = create_crud_router(
        table_name="widget_query",
        backend=backend,
        response_model=WidgetQueryResponse,
        create_model=WidgetQueryCreate,
        update_model=WidgetQueryUpdate
    )
    
    app.include_router(router, prefix="/widget-query")
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Type, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from .backends import StorageBackend

try:
    from fastapi import APIRouter, Depends, HTTPException, Query, Body
    from fastapi.concurrency import run_in_threadpool
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = None
    Depends = None
    HTTPException = None
    Query = None
    Body = None
    BaseModel = None

logger = logging.getLogger(__name__)


# â”€â”€â”€ Generic Response Models â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

if FASTAPI_AVAILABLE:
    class GenericListResponse(BaseModel):
        """Generic paginated list response"""
        total: int
        items: List[Dict[str, Any]]
        limit: int
        offset: int

    class GenericMessageResponse(BaseModel):
        """Generic success/error message response"""
        message: str
        status: str = "success"
        details: Optional[Dict[str, Any]] = None


# â”€â”€â”€ CRUD Router Factory â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def create_crud_router(
    table_name: str,
    backend: "StorageBackend",
    primary_key: Optional[str] = None,
    response_model: Optional[Type[BaseModel]] = None,
    create_model: Optional[Type[BaseModel]] = None,
    update_model: Optional[Type[BaseModel]] = None,
    list_model: Optional[Type[BaseModel]] = None,
    router_prefix: Optional[str] = None,
    router_tags: Optional[List[str]] = None,
    order_by: Optional[str] = None,
    filterable_fields: Optional[List[str]] = None,
    enable_history: bool = False,
    timestamp_field: str = "created_at",
    async_mode: bool = True,
    custom_validators: Optional[Dict[str, Callable]] = None,
) -> APIRouter:
    """
    Create a generic CRUD router for any storage backend (ClickHouse, DuckDB, etc.).
    
    This function creates a FastAPI router with standard CRUD endpoints that work
    with ANY storage backend implementing the StorageBackend protocol.
    
    Args:
        table_name: Name of the table in the backend
        backend: StorageBackend instance (ClickHouseBackend, DuckDbBackend, etc.)
        primary_key: Primary key field name (optional, inferred from backend if not provided)
        response_model: Pydantic model for responses (optional)
        create_model: Pydantic model for create requests (optional)
        update_model: Pydantic model for update requests (optional)
        list_model: Pydantic model for list responses (optional, defaults to GenericListResponse)
        router_prefix: URL prefix for router (defaults to f"/{table_name}")
        router_tags: Tags for OpenAPI docs (defaults to [table_name])
        order_by: Default ORDER BY clause (backend-specific)
        filterable_fields: Fields that can be filtered in list endpoint
        enable_history: Enable version history endpoint (backend-dependent)
        timestamp_field: Field name for timestamps (default: "created_at")
        async_mode: Use async/await for operations (default: True)
        custom_validators: Dict of field_name -> validator_function
    
    Returns:
        FastAPI APIRouter with CRUD endpoints
        
    Raises:
        RuntimeError: If FastAPI is not installed
        
    Example:
        from config_core import create_crud_router, ClickHouseBackend
        from clickhouse_core import ClickHouseClient
        
        client = ClickHouseClient(config)
        backend = ClickHouseBackend(client, primary_key="widget_id")
        router = create_crud_router("widget_query", backend)
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError(
            "FastAPI is required for CRUD API. Install with: pip install configflow[api]"
        )
    
    # Get primary key from backend if not provided
    if primary_key is None:
        primary_key = getattr(backend, 'primary_key', 'id')
    
    # Default values
    router_prefix = router_prefix or f"/{table_name.replace('_', '-')}"
    router_tags = router_tags or [table_name]
    filterable_fields = filterable_fields or []
    custom_validators = custom_validators or {}
    
    # Create router
    router = APIRouter(prefix=router_prefix, tags=router_tags)
    
    # Determine primary key fields (support composite keys)
    pk_fields = [primary_key] if isinstance(primary_key, str) else list(primary_key)
    
    # Client dependency - returns the backend's client
    def client_dependency():
        """Return the backend client for dependency injection"""
        return backend.client if hasattr(backend, 'client') else backend
    
    # Helper function to execute queries via backend
    async def _execute_query(client, query: str, params: dict):
        """Execute a query using the backend"""
        if async_mode:
            return await run_in_threadpool(backend.execute, query, params)
        else:
            return backend.execute(query, params)
    
    # Helper function to validate primary key values
    def _validate_pk_values(pk_values: dict):
        """Validate that all primary key fields are provided"""
        for field in pk_fields:
            if field not in pk_values or pk_values[field] is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing primary key field: {field}"
                )
    
    # Helper function to build WHERE clause from filters
    def _build_where_clause(filters: dict) -> tuple:
        """Build WHERE clause from filter parameters"""
        conditions = []
        params = {}
        for field, value in filters.items():
            if value is not None and field in filterable_fields:
                conditions.append(f"{field} = %({field})s")
                params[field] = value
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        return where_clause, params
    
    # Helper function to call backend methods
    async def _call_backend(method, *args, **kwargs):
        """Call backend method in async or sync mode"""
        if async_mode:
            return await run_in_threadpool(method, *args, **kwargs)
        else:
            return method(*args, **kwargs)
    
    # â”€â”€â”€ CREATE Endpoint â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    
    if create_model:
        @router.post("/", response_model=response_model or Dict)
        async def create_record(
            request: create_model,
            client = Depends(client_dependency)
        ):
            """Create a new record"""
            try:
                data = request.dict() if hasattr(request, 'dict') else request.model_dump()
                
                # Apply custom validators
                for field, validator in custom_validators.items():
                    if field in data:
                        data[field] = validator(data[field])
                
                # Check if record already exists
                pk_where = " AND ".join([f"{field} = %({field})s" for field in pk_fields])
                pk_params = {field: data[field] for field in pk_fields}
                
                existing = await _execute_query(
                    client,
                    f"SELECT {', '.join(pk_fields)} FROM {table_name} WHERE {pk_where} LIMIT 1",
                    pk_params
                )
                
                if existing:
                    pk_values = ", ".join([f"{field}='{data[field]}'" for field in pk_fields])
                    raise HTTPException(
                        status_code=409,
                        detail=f"Record with {pk_values} already exists. Use PUT to update."
                    )
                
                # Add timestamp if field exists and not provided
                if timestamp_field and timestamp_field not in data:
                    data[timestamp_field] = datetime.utcnow()
                
                # Build INSERT query
                fields = list(data.keys())
                values_placeholder = ", ".join([f"%({field})s" for field in fields])
                
                await _execute_query(
                    client,
                    f"INSERT INTO {table_name} ({', '.join(fields)}) VALUES ({values_placeholder})",
                    data
                )
                
                logger.info(f"Created record in {table_name}: {pk_params}")
                
                # Return created record
                if response_model:
                    return response_model(**data)
                return data
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error creating record in {table_name}: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to create record: {str(e)}"
                )
    
    # â”€â”€â”€ READ (List) Endpoint â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    
    @router.get("/", response_model=list_model or GenericListResponse)
    async def list_records(
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        client = Depends(client_dependency),
        **filters
    ):
        """List records with optional filtering and pagination"""
        try:
            # Build WHERE clause from query params
            where_clause, where_params = _build_where_clause(filters)
            
            # Get total count
            count_query = f"SELECT count() FROM {table_name} {where_clause}"
            total_result = await _execute_query(client, count_query, where_params)
            total = total_result[0][0] if total_result else 0
            
            # Get data
            order_clause = f"ORDER BY {order_by}" if order_by else ""
            data_query = f"""
                SELECT * FROM {table_name}
                {where_clause}
                {order_clause}
                LIMIT %(limit)s OFFSET %(offset)s
            """
            where_params.update({'limit': limit, 'offset': offset})
            
            rows = await _execute_query(client, data_query, where_params)
            
            # Convert to dict
            items = []
            if rows:
                # Get column names from first row if available
                if hasattr(rows, 'keys'):
                    items = [dict(row) for row in rows]
                else:
                    # Fallback: query for column names
                    desc_query = f"DESCRIBE TABLE {table_name}"
                    desc_rows = await _execute_query(client, desc_query, {})
                    columns = [row[0] for row in desc_rows]
                    items = [dict(zip(columns, row)) for row in rows]
            
            if list_model and list_model != GenericListResponse:
                return list_model(total=total, items=items, limit=limit, offset=offset)
            
            return GenericListResponse(total=total, items=items, limit=limit, offset=offset)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error listing records from {table_name}: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to list records: {str(e)}"
            )
    
    # â”€â”€â”€ READ (Get by ID) Endpoint â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    
    # Build path parameters for primary key(s)
    pk_path = "/".join([f"{{{field}}}" for field in pk_fields])
    
    @router.get(f"/{pk_path}", response_model=response_model or Dict)
    async def get_record(
        client = Depends(client_dependency),
        **pk_values
    ):
        """Get a record by primary key"""
        try:
            _validate_pk_values(pk_values)
            
            # Build WHERE clause for primary key
            where_conditions = [f"{field} = %({field})s" for field in pk_fields]
            where_clause = " AND ".join(where_conditions)
            
            order_clause = f"ORDER BY {order_by}" if order_by else ""
            
            query = f"""
                SELECT * FROM {table_name}
                WHERE {where_clause}
                {order_clause}
                LIMIT 1
            """
            
            rows = await _execute_query(client, query, pk_values)
            
            if not rows:
                pk_str = ", ".join([f"{k}={v}" for k, v in pk_values.items()])
                raise HTTPException(
                    status_code=404,
                    detail=f"Record with {pk_str} not found in {table_name}"
                )
            
            # Convert to dict
            row = rows[0]
            if hasattr(row, 'keys'):
                data = dict(row)
            else:
                # Get column names
                desc_query = f"DESCRIBE TABLE {table_name}"
                desc_rows = await _execute_query(client, desc_query, {})
                columns = [r[0] for r in desc_rows]
                data = dict(zip(columns, row))
            
            if response_model:
                return response_model(**data)
            return data
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting record from {table_name}: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get record: {str(e)}"
            )
    
    # â”€â”€â”€ UPDATE Endpoint â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    
    if update_model:
        @router.put(f"/{pk_path}", response_model=response_model or Dict)
        async def update_record(
            request: update_model,
            client = Depends(client_dependency),
            **pk_values
        ):
            """Update an existing record"""
            try:
                _validate_pk_values(pk_values)
                
                # Check if record exists
                where_conditions = [f"{field} = %({field})s" for field in pk_fields]
                where_clause = " AND ".join(where_conditions)
                
                existing = await _execute_query(
                    client,
                    f"SELECT * FROM {table_name} WHERE {where_clause} LIMIT 1",
                    pk_values
                )
                
                if not existing:
                    pk_str = ", ".join([f"{k}={v}" for k, v in pk_values.items()])
                    raise HTTPException(
                        status_code=404,
                        detail=f"Record with {pk_str} not found in {table_name}"
                    )
                
                # Get update data (exclude None values)
                data = request.dict(exclude_none=True) if hasattr(request, 'dict') else request.model_dump(exclude_none=True)
                
                # Apply custom validators
                for field, validator in custom_validators.items():
                    if field in data:
                        data[field] = validator(data[field])
                
                # Remove primary key fields from update data
                for field in pk_fields:
                    data.pop(field, None)
                
                if not data:
                    raise HTTPException(
                        status_code=400,
                        detail="No fields to update"
                    )
                
                # Build UPDATE query (ClickHouse ALTER TABLE UPDATE)
                set_clauses = [f"{field} = %({field})s" for field in data.keys()]
                update_params = {**data, **pk_values}
                
                await _execute_query(
                    client,
                    f"""
                    ALTER TABLE {table_name}
                    UPDATE {', '.join(set_clauses)}
                    WHERE {where_clause}
                    """,
                    update_params
                )
                
                logger.info(f"Updated record in {table_name}: {pk_values}")
                
                # Fetch and return updated record
                updated_rows = await _execute_query(
                    client,
                    f"SELECT * FROM {table_name} WHERE {where_clause} LIMIT 1",
                    pk_values
                )
                
                if updated_rows:
                    row = updated_rows[0]
                    if hasattr(row, 'keys'):
                        result = dict(row)
                    else:
                        desc_query = f"DESCRIBE TABLE {table_name}"
                        desc_rows = await _execute_query(client, desc_query, {})
                        columns = [r[0] for r in desc_rows]
                        result = dict(zip(columns, row))
                    
                    if response_model:
                        return response_model(**result)
                    return result
                
                return {"message": "Updated successfully"}
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error updating record in {table_name}: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to update record: {str(e)}"
                )
    
    # â”€â”€â”€ DELETE Endpoint â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    
    @router.delete(f"/{pk_path}", response_model=GenericMessageResponse)
    async def delete_record(
        client = Depends(client_dependency),
        **pk_values
    ):
        """Delete a record by primary key"""
        try:
            _validate_pk_values(pk_values)
            
            # Check if record exists
            where_conditions = [f"{field} = %({field})s" for field in pk_fields]
            where_clause = " AND ".join(where_conditions)
            
            existing = await _execute_query(
                client,
                f"SELECT {', '.join(pk_fields)} FROM {table_name} WHERE {where_clause} LIMIT 1",
                pk_values
            )
            
            if not existing:
                pk_str = ", ".join([f"{k}={v}" for k, v in pk_values.items()])
                raise HTTPException(
                    status_code=404,
                    detail=f"Record with {pk_str} not found in {table_name}"
                )
            
            # Delete using ALTER TABLE (ClickHouse way)
            # Note: Build WHERE clause with literal values for ALTER TABLE DELETE
            where_literals = " AND ".join([
                f"{field} = '{pk_values[field]}'" if isinstance(pk_values[field], str)
                else f"{field} = {pk_values[field]}"
                for field in pk_fields
            ])
            
            await _execute_query(
                client,
                f"ALTER TABLE {table_name} DELETE WHERE {where_literals}",
                {}
            )
            
            logger.info(f"Deleted record from {table_name}: {pk_values}")
            
            return GenericMessageResponse(
                message=f"Record deleted successfully from {table_name}",
                status="success",
                details=pk_values
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting record from {table_name}: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete record: {str(e)}"
            )
    
    # â”€â”€â”€ HISTORY Endpoint (Optional) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    
    if enable_history:
        @router.get(f"/{pk_path}/history", response_model=list_model or GenericListResponse)
        async def get_record_history(
            client = Depends(client_dependency),
            **pk_values
        ):
            """Get all historical versions of a record"""
            try:
                _validate_pk_values(pk_values)
                
                # Build WHERE clause for primary key
                where_conditions = [f"{field} = %({field})s" for field in pk_fields]
                where_clause = " AND ".join(where_conditions)
                
                order_clause = f"ORDER BY {timestamp_field} DESC" if timestamp_field else ""
                
                query = f"""
                    SELECT * FROM {table_name}
                    WHERE {where_clause}
                    {order_clause}
                """
                
                rows = await _execute_query(client, query, pk_values)
                
                if not rows:
                    pk_str = ", ".join([f"{k}={v}" for k, v in pk_values.items()])
                    raise HTTPException(
                        status_code=404,
                        detail=f"No history found for {pk_str} in {table_name}"
                    )
                
                # Convert to list of dicts
                items = []
                if hasattr(rows[0], 'keys'):
                    items = [dict(row) for row in rows]
                else:
                    desc_query = f"DESCRIBE TABLE {table_name}"
                    desc_rows = await _execute_query(client, desc_query, {})
                    columns = [r[0] for r in desc_rows]
                    items = [dict(zip(columns, row)) for row in rows]
                
                if list_model and list_model != GenericListResponse:
                    return list_model(total=len(items), items=items, limit=len(items), offset=0)
                
                return GenericListResponse(total=len(items), items=items, limit=len(items), offset=0)
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error getting history from {table_name}: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to get record history: {str(e)}"
                )
    
    return router
