"""
Config-Specific API Factory for ConfigStore

This module provides FastAPI router factory specifically for configuration management
using ConfigStore backend. Provides version management, section-based updates,
and reload capabilities.

Usage:
    from config_core import ConfigStore
    from config_core.config_api import create_config_router
    
    store = ConfigStore(
        initial_config={...},
        clickhouse_params={...},
        config_name="engine_config"
    )
    
    router = create_config_router(
        config_store=store,
        config_model=RootConfig,  # Optional Pydantic model for validation
        reload_callback=reload_settings  # Optional callback after config changes
    )
    
    app.include_router(router, prefix="/config")
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Dict, List, Optional, Type

try:
    from fastapi import APIRouter, Depends, HTTPException, Body
    from fastapi.concurrency import run_in_threadpool
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = None
    Depends = None
    HTTPException = None
    Body = None
    BaseModel = None

logger = logging.getLogger(__name__)


# â”€â”€â”€ Response Models â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

if FASTAPI_AVAILABLE:
    class ConfigVersionInfo(BaseModel):
        """Config version information"""
        config_name: str
        environment: str
        version: int
        updated_at: Optional[str] = None

    class ConfigVersionsResponse(BaseModel):
        """List of config versions"""
        status: str = "success"
        total_versions: int
        versions: List[ConfigVersionInfo]

    class ConfigVersionDetailResponse(BaseModel):
        """Detailed config version"""
        status: str = "success"
        version: int
        updated_at: Optional[str] = None
        config: Dict[str, Any]

    class ConfigReloadResponse(BaseModel):
        """Config reload response"""
        status: str = "success"
        message: str
        config: Optional[Dict[str, Any]] = None


# â”€â”€â”€ Config Router Factory â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def create_config_router(
    config_store,  # ConfigStore instance
    config_model: Optional[Type[BaseModel]] = None,
    reload_callback: Optional[Callable] = None,
    auth_dependency: Optional[Callable] = None,
    router_prefix: str = "/config",
    router_tags: Optional[List[str]] = None,
    enable_section_endpoints: bool = True,
    enable_version_endpoints: bool = True,
    enable_database_endpoints: bool = True,
) -> APIRouter:
    """
    Create a config management router for ConfigStore.
    
    Args:
        config_store: ConfigStore instance (initialized with config_name)
        config_model: Optional Pydantic model for config validation
        reload_callback: Optional function to call after config updates
        auth_dependency: Optional FastAPI dependency for authentication
        router_prefix: URL prefix (default: "/config")
        router_tags: OpenAPI tags (default: ["config"])
        enable_section_endpoints: Enable section-specific CRUD (default: True)
        enable_version_endpoints: Enable version management endpoints (default: True)
        enable_database_endpoints: Enable database introspection endpoints (default: True)
    
    Returns:
        FastAPI APIRouter with config management endpoints
        
    Raises:
        RuntimeError: If FastAPI is not installed
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError(
            "FastAPI is required for config API. Install with: pip install configflow[api]"
        )
    
    from .backend import ConfigStore
    
    if not isinstance(config_store, ConfigStore):
        raise TypeError("config_store must be an instance of ConfigStore")
    
    # Default values
    router_tags = router_tags or ["config"]
    
    # Create router
    router = APIRouter(prefix=router_prefix, tags=router_tags)
    
    # Apply auth dependency to all routes if provided
    dependencies = [Depends(auth_dependency)] if auth_dependency else []
    
    # Get config_name from store
    config_name = config_store._config_name
    environment = config_store._environment
    
    # Helper to execute config operations in thread pool
    async def _run_in_thread(func, *args, **kwargs):
        """Run ConfigStore operation in thread pool"""
        return await run_in_threadpool(func, *args, **kwargs)
    
    # â”€â”€â”€ GET Full Config â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    
    @router.get("/", dependencies=dependencies)
    async def get_full_config():
        """
        Read the entire configuration.
        Returns the current active config from ConfigStore.
        """
        try:
            config = await _run_in_thread(config_store.get_config, refresh=False)
            
            if config_model:
                return config_model(**config)
            return config
            
        except Exception as e:
            logger.error(f"Error reading config: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to read config: {str(e)}"
            )
    
    # â”€â”€â”€ PUT Full Config (Replace) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    
    @router.put("/", dependencies=dependencies)
    async def replace_config(new_config: Dict[str, Any] = Body(...)):
        """
        Replace the entire configuration.
        Creates a new version in the database.
        """
        try:
            # Validate with model if provided
            if config_model:
                validated = config_model(**new_config)
                new_config = validated.dict() if hasattr(validated, 'dict') else validated.model_dump()
            
            # Update config (creates new version)
            await _run_in_thread(config_store.update_config, new_config)
            
            # Get updated config
            updated = await _run_in_thread(config_store.get_config, refresh=True)
            
            # Call reload callback if provided
            if reload_callback:
                try:
                    if asyncio.iscoroutinefunction(reload_callback):
                        await reload_callback()
                    else:
                        await _run_in_thread(reload_callback)
                except Exception as e:
                    logger.warning(f"Reload callback failed: {e}")
            
            logger.info(f"Replaced full config for {config_name}")
            
            if config_model:
                return config_model(**updated)
            return updated
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error replacing config: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to replace config: {str(e)}"
            )
    
    # â”€â”€â”€ PATCH Config (Merge) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    
    @router.patch("/", dependencies=dependencies)
    async def update_config(patch: Dict[str, Any] = Body(...)):
        """
        Merge provided keys into the configuration.
        Creates a new version in the database.
        
        Example: {"logging": {"level": "DEBUG"}, "debug": true}
        """
        try:
            # Patch config (deep merge)
            updated = await _run_in_thread(config_store.patch_config, patch)
            
            # Call reload callback if provided
            if reload_callback:
                try:
                    if asyncio.iscoroutinefunction(reload_callback):
                        await reload_callback()
                    else:
                        await _run_in_thread(reload_callback)
                except Exception as e:
                    logger.warning(f"Reload callback failed: {e}")
            
            logger.info(f"Patched config for {config_name}")
            
            if config_model:
                return config_model(**updated)
            return updated
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error patching config: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to patch config: {str(e)}"
            )
    
    # â”€â”€â”€ POST Reload Config â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    
    @router.post("/reload", response_model=ConfigReloadResponse, dependencies=dependencies)
    async def reload_config():
        """
        Reload configuration from database.
        Clears cache and fetches the latest version.
        """
        try:
            # Refresh config from database
            config = await _run_in_thread(config_store.get_config, refresh=True)
            
            # Call reload callback if provided
            if reload_callback:
                try:
                    if asyncio.iscoroutinefunction(reload_callback):
                        await reload_callback()
                    else:
                        await _run_in_thread(reload_callback)
                    logger.info("Reload callback executed successfully")
                except Exception as e:
                    logger.warning(f"Reload callback failed: {e}")
            
            logger.info(f"Reloaded config for {config_name}")
            
            return ConfigReloadResponse(
                status="success",
                message=f"Configuration reloaded for {config_name}",
                config=config
            )
            
        except Exception as e:
            logger.error(f"Error reloading config: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to reload config: {str(e)}"
            )
    
    # â”€â”€â”€ Section Endpoints â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    
    if enable_section_endpoints:
        
        @router.get("/{section}", dependencies=dependencies)
        async def get_section(section: str):
            """
            Read a specific section of the config.
            Example: /config/clickhouse
            """
            try:
                config = await _run_in_thread(config_store.get_config, refresh=False)
                
                if section not in config:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Section '{section}' not found in config"
                    )
                
                return config[section]
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error reading section '{section}': {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to read section: {str(e)}"
                )
        
        @router.put("/{section}", dependencies=dependencies)
        async def replace_section(section: str, section_config: Dict[str, Any] = Body(...)):
            """
            Replace a specific section of the config.
            Example: PUT /config/clickhouse with {"host": "localhost", ...}
            """
            try:
                # Update section
                patch = {section: section_config}
                updated = await _run_in_thread(config_store.patch_config, patch)
                
                # Call reload callback
                if reload_callback:
                    try:
                        if asyncio.iscoroutinefunction(reload_callback):
                            await reload_callback()
                        else:
                            await _run_in_thread(reload_callback)
                    except Exception as e:
                        logger.warning(f"Reload callback failed: {e}")
                
                logger.info(f"Replaced section '{section}' in {config_name}")
                
                if config_model:
                    return config_model(**updated)
                return updated
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error replacing section '{section}': {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to replace section: {str(e)}"
                )
        
        @router.delete("/{section}", dependencies=dependencies)
        async def delete_section(section: str):
            """
            Delete a specific section from the config.
            Not recommended for required sections!
            """
            try:
                config = await _run_in_thread(config_store.get_config, refresh=False)
                
                if section not in config:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Section '{section}' not found in config"
                    )
                
                # Remove section
                config.pop(section)
                await _run_in_thread(config_store.update_config, config)
                
                # Get updated config
                updated = await _run_in_thread(config_store.get_config, refresh=True)
                
                # Call reload callback
                if reload_callback:
                    try:
                        if asyncio.iscoroutinefunction(reload_callback):
                            await reload_callback()
                        else:
                            await _run_in_thread(reload_callback)
                    except Exception as e:
                        logger.warning(f"Reload callback failed: {e}")
                
                logger.info(f"Deleted section '{section}' from {config_name}")
                
                if config_model:
                    return config_model(**updated)
                return updated
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error deleting section '{section}': {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to delete section: {str(e)}"
                )
    
    # â”€â”€â”€ Version Management Endpoints â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    
    if enable_version_endpoints:
        
        @router.get("/versions", response_model=ConfigVersionsResponse, dependencies=dependencies)
        async def get_config_versions():
            """
            Fetch all config versions from database.
            Shows version history with timestamps.
            """
            try:
                client = config_store._client
                
                rows = await _run_in_thread(
                    client.execute,
                    """
                    SELECT config_name, environment, version, updated_at
                    FROM configs
                    WHERE config_name = %(name)s AND environment = %(env)s
                    ORDER BY version DESC
                    """,
                    {"name": config_name, "env": environment}
                )
                
                versions = [
                    ConfigVersionInfo(
                        config_name=row[0],
                        environment=row[1],
                        version=row[2],
                        updated_at=row[3].isoformat() if row[3] else None
                    )
                    for row in rows
                ]
                
                return ConfigVersionsResponse(
                    status="success",
                    total_versions=len(versions),
                    versions=versions
                )
                
            except Exception as e:
                logger.error(f"Error fetching versions: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to fetch versions: {str(e)}"
                )
        
        @router.get("/versions/{version}", response_model=ConfigVersionDetailResponse, dependencies=dependencies)
        async def get_config_by_version(version: int):
            """
            Fetch a specific config version from database.
            Does NOT apply it - just shows what that version contains.
            """
            try:
                client = config_store._client
                
                rows = await _run_in_thread(
                    client.execute,
                    """
                    SELECT payload, updated_at
                    FROM configs
                    WHERE config_name = %(name)s AND environment = %(env)s AND version = %(version)s
                    """,
                    {"name": config_name, "env": environment, "version": version}
                )
                
                if not rows:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Version {version} not found for {config_name}"
                    )
                
                payload = json.loads(rows[0][0])
                updated_at = rows[0][1]
                
                return ConfigVersionDetailResponse(
                    status="success",
                    version=version,
                    updated_at=updated_at.isoformat() if updated_at else None,
                    config=payload
                )
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error fetching version {version}: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to fetch version: {str(e)}"
                )
        
        @router.put("/versions/{version}", dependencies=dependencies)
        async def update_config_version(version: int, payload: Dict[str, Any] = Body(...)):
            """
            Update a specific version in-place (advanced operation).
            Modifies the version in the database without creating a new version.
            """
            try:
                await _run_in_thread(config_store.update_config_version, version, payload)
                
                logger.info(f"Updated version {version} of {config_name}")
                
                return {"status": "success", "message": f"Version {version} updated"}
                
            except Exception as e:
                logger.error(f"Error updating version {version}: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to update version: {str(e)}"
                )
        
        @router.patch("/versions/{version}", dependencies=dependencies)
        async def patch_config_version(version: int, patch: Dict[str, Any] = Body(...)):
            """
            Patch a specific version in-place (advanced operation).
            Merges changes into the version in the database.
            """
            try:
                await _run_in_thread(config_store.patch_config_version, version, patch)
                
                logger.info(f"Patched version {version} of {config_name}")
                
                return {"status": "success", "message": f"Version {version} patched"}
                
            except Exception as e:
                logger.error(f"Error patching version {version}: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to patch version: {str(e)}"
                )
    
    # â”€â”€â”€ Database Introspection Endpoints â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    
    if enable_database_endpoints:
        
        @router.get("/database/current", dependencies=dependencies)
        async def get_current_database_config():
            """
            Fetch the current config directly from database (latest version).
            This is what will be loaded on next server restart/reload.
            """
            try:
                client = config_store._client
                
                rows = await _run_in_thread(
                    client.execute,
                    """
                    SELECT version, payload, updated_at
                    FROM configs
                    WHERE config_name = %(name)s AND environment = %(env)s
                    ORDER BY version DESC
                    LIMIT 1
                    """,
                    {"name": config_name, "env": environment}
                )
                
                if not rows:
                    return {
                        "status": "not_found",
                        "message": f"No config found in database for {config_name}"
                    }
                
                version = rows[0][0]
                payload = json.loads(rows[0][1])
                updated_at = rows[0][2]
                
                return {
                    "status": "success",
                    "version": version,
                    "updated_at": updated_at.isoformat() if updated_at else None,
                    "config": payload,
                    "note": "This config will be loaded on next restart/reload"
                }
                
            except Exception as e:
                logger.error(f"Error fetching database config: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to fetch database config: {str(e)}"
                )
    
    return router


# Import asyncio for async callback support
try:
    import asyncio
except ImportError:
    asyncio = None
