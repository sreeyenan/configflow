"""
Example: Using ConfigStore with DuckDB backend

This example demonstrates how to use configflow with DuckDB as the storage backend
instead of ClickHouse. DuckDB is ideal for:
- Local development and testing
- Single-instance services
- Embedded applications
- When you don't need shared state across multiple pods

DuckDB provides the same API as ClickHouse but with a simpler setup.
"""

from configflow import ConfigStore
import json

def main():
    # Example 1: In-memory DuckDB (no persistence)
    print("=" * 60)
    print("Example 1: In-memory DuckDB")
    print("=" * 60)
    
    store_memory = ConfigStore(
        initial_config={
            "app_name": "my_service",
            "version": "1.0.0",
            "debug": True,
            "threshold": 0.85,
            "features": {
                "feature_a": True,
                "feature_b": False,
            }
        },
        duckdb_params={"database": ":memory:"},
        backend="duckdb",
        config_name="app_config",
        environment="development",
    )
    
    # Get config
    config = store_memory.get_config()
    print(f"Initial config: {json.dumps(config, indent=2)}")
    
    # Update a single value
    print("\nPatching config (threshold: 0.95)...")
    store_memory.patch_config({"threshold": 0.95})
    
    updated_config = store_memory.get_config()
    print(f"Updated threshold: {updated_config['threshold']}")
    
    # Update nested value
    print("\nPatching nested config (feature_a: False)...")
    store_memory.patch_config({"features": {"feature_a": False}})
    
    config = store_memory.get_config()
    print(f"Updated feature_a: {config['features']['feature_a']}")
    
    # Example 2: File-based DuckDB (persistent)
    print("\n" + "=" * 60)
    print("Example 2: File-based DuckDB (persistent)")
    print("=" * 60)
    
    store_file = ConfigStore(
        initial_config={
            "database": {
                "host": "${DB_HOST:localhost}",
                "port": "${DB_PORT:5432}",
            },
            "cache_ttl": 300,
        },
        duckdb_params={"database": "example_config.duckdb"},
        backend="duckdb",
        config_name="db_config",
        environment="production",
    )
    
    config = store_file.get_config()
    print(f"Config from file: {json.dumps(config, indent=2)}")
    print(f"\n✅ Config saved to: example_config.duckdb")
    
    # Example 3: Using environment variable to set backend
    print("\n" + "=" * 60)
    print("Example 3: Using DEFAULT_BACKEND environment variable")
    print("=" * 60)
    
    import os
    os.environ["DEFAULT_BACKEND"] = "duckdb"
    os.environ["DUCKDB_DATABASE"] = ":memory:"
    
    store_env = ConfigStore(
        initial_config={"message": "Hello from DuckDB via env vars!"},
        config_name="env_config",
    )
    
    config = store_env.get_config()
    print(f"Config: {json.dumps(config, indent=2)}")
    
    # Example 4: CRUD operations
    print("\n" + "=" * 60)
    print("Example 4: Full CRUD operations")
    print("=" * 60)
    
    store_crud = ConfigStore(
        initial_config={"counter": 0, "items": []},
        duckdb_params={"database": ":memory:"},
        backend="duckdb",
        config_name="crud_config",
    )
    
    # Read
    print("Read:", store_crud.get_config())
    
    # Update (partial)
    store_crud.patch_config({"counter": 1})
    print("After patch:", store_crud.get_config())
    
    # Update (full replace)
    store_crud.update_config({"counter": 5, "items": ["a", "b", "c"]})
    print("After update:", store_crud.get_config())
    
    # Refresh from DB
    fresh = store_crud.get_config(refresh=True)
    print("After refresh:", fresh)
    
    print("\n" + "=" * 60)
    print("✅ All examples completed successfully!")
    print("=" * 60)

if __name__ == "__main__":
    main()
