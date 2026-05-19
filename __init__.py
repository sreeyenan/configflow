try:
    from importlib.metadata import version
    __version__ = version("configflow")
except Exception:
    __version__ = "0.0.0"  # Fallback for development

from .resolver import resolve_env_vars
from .loader import load_json_config, load_config_from_path, ConfigLoader
from .backend import ConfigStore

__all__ = [
    "resolve_env_vars",
    "load_json_config",
    "load_config_from_path",
    "ConfigLoader",
    "ConfigStore",
]

# Optional FastAPI API modules (only available if fastapi is installed)
try:
    # Import table utilities from clickhouse_core (low-level SQL generation)
    from clickhouse_core import (
        create_table_initializer,
        create_materialized_view_sql,
    )
    
    from .crud_api import create_crud_router
    from .config_api import create_config_router
    from .backends import (
        StorageBackend,
        ClickHouseBackend,
        DuckDbBackend,
    )
    
    __all__.extend([
        "create_crud_router",
        "create_config_router",
        "create_table_initializer",  # Re-exported from clickhouse_core
        "create_materialized_view_sql",  # Re-exported from clickhouse_core
        "StorageBackend",
        "ClickHouseBackend",
        "DuckDbBackend",
    ])
except ImportError:
    # FastAPI not installed - API modules not available
    # Install with: pip install configflow[api]
    pass
