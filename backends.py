"""
Storage Backend Adapters

Provides adapters for different storage backends (ClickHouse, DuckDB, etc.)
to work with the generic CRUD API.

This enables the same CRUD API to work with multiple storage backends
using the Strategy/Adapter pattern.
"""

from typing import Any, Dict, List, Protocol, runtime_checkable
import logging

logger = logging.getLogger(__name__)


@runtime_checkable
class StorageBackend(Protocol):
    """
    Protocol/Interface for storage backends.
    
    Any backend that implements these methods can be used with
    create_crud_router() to provide a REST API.
    
    This enables:
    - ClickHouse backend for persistent storage
    - DuckDB backend for cached/in-memory data
    - MongoDB backend for document storage (future)
    - Any other backend that implements this interface
    """
    
    def query(self, table: str, filters: Dict[str, Any], limit: int, offset: int) -> List[Dict]:
        """
        Query data from backend with filters.
        
        Args:
            table: Table name
            filters: Dict of column_name -> value for filtering
            limit: Maximum number of rows to return
            offset: Number of rows to skip
            
        Returns:
            List of dicts (rows)
        """
        ...
    
    def create(self, table: str, data: Dict[str, Any]) -> Dict:
        """
        Create new record in backend.
        
        Args:
            table: Table name
            data: Dict of column_name -> value
            
        Returns:
            Created record dict
        """
        ...
    
    def update(self, table: str, id_value: Any, data: Dict[str, Any]) -> Dict:
        """
        Update existing record in backend.
        
        Args:
            table: Table name
            id_value: Primary key value
            data: Dict of column_name -> value to update
            
        Returns:
            Updated record dict
        """
        ...
    
    def delete(self, table: str, id_value: Any) -> bool:
        """
        Delete record from backend.
        
        Args:
            table: Table name
            id_value: Primary key value
            
        Returns:
            True if successful
        """
        ...
    
    def get_by_id(self, table: str, id_value: Any) -> Dict:
        """
        Get single record by ID.
        
        Args:
            table: Table name
            id_value: Primary key value
            
        Returns:
            Record dict
            
        Raises:
            ValueError: If record not found
        """
        ...
    
    def get_info(self, table: str) -> Dict:
        """
        Get table metadata (row count, columns, etc.).
        
        Args:
            table: Table name
            
        Returns:
            Dict with metadata
        """
        ...


class ClickHouseBackend:
    """
    ClickHouse storage backend adapter.
    
    Uses clickhouse_core.ClickHouseClient for low-level operations.
    Implements the StorageBackend protocol to work with generic CRUD API.
    
    Example:
        from clickhouse_core import ClickHouseClient
        from configflow import ClickHouseBackend, create_crud_router
        
        client = ClickHouseClient(config)
        backend = ClickHouseBackend(client, primary_key="widget_id")
        router = create_crud_router("widget_query", backend)
    """
    
    def __init__(self, client, primary_key: str = "id"):
        """
        Args:
            client: clickhouse_core.ClickHouseClient instance
            primary_key: Name of primary key column
        """
        self.client = client
        self.primary_key = primary_key
    
    def query(self, table: str, filters: Dict[str, Any], limit: int, offset: int) -> List[Dict]:
        """Query ClickHouse table with SQL WHERE."""
        where_clauses = []
        params = {}
        
        for i, (key, value) in enumerate(filters.items()):
            param_name = f"p{i}"
            where_clauses.append(f"{key} = %({param_name})s")
            params[param_name] = value
        
        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        
        sql = f"""
            SELECT * FROM {table}
            {where_sql}
            ORDER BY {self.primary_key}
            LIMIT {limit} OFFSET {offset}
        """
        
        rows = self.client.execute(sql, params)
        
        # Get column names
        desc_rows = self.client.execute(f"DESCRIBE TABLE {table}")
        columns = [row[0] for row in desc_rows]
        
        return [dict(zip(columns, row)) for row in rows]
    
    def create(self, table: str, data: Dict[str, Any]) -> Dict:
        """Insert new record into ClickHouse."""
        columns = list(data.keys())
        values_placeholder = ", ".join([f"%({col})s" for col in columns])
        
        sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({values_placeholder})"
        self.client.execute(sql, data)
        
        return data
    
    def update(self, table: str, id_value: Any, data: Dict[str, Any]) -> Dict:
        """
        Update record in ClickHouse using ALTER TABLE UPDATE.
        
        Note: ClickHouse updates are eventually consistent and may take time to apply.
        For ReplacingMergeTree, consider inserting a new version instead.
        """
        set_clauses = [f"{key} = %({key})s" for key in data.keys()]
        params = {**data, "id_val": id_value}
        
        sql = f"""
            ALTER TABLE {table}
            UPDATE {', '.join(set_clauses)}
            WHERE {self.primary_key} = %(id_val)s
        """
        
        self.client.execute(sql, params)
        return {**data, self.primary_key: id_value}
    
    def delete(self, table: str, id_value: Any) -> bool:
        """
        Delete record from ClickHouse using ALTER TABLE DELETE.
        
        Note: ClickHouse deletes are eventually consistent and may take time to apply.
        """
        sql = f"ALTER TABLE {table} DELETE WHERE {self.primary_key} = %(id_val)s"
        self.client.execute(sql, {"id_val": id_value})
        return True
    
    def get_by_id(self, table: str, id_value: Any) -> Dict:
        """Get single record by ID."""
        results = self.query(table, {self.primary_key: id_value}, limit=1, offset=0)
        if not results:
            raise ValueError(f"Record with {self.primary_key}={id_value} not found")
        return results[0]
    
    def get_info(self, table: str) -> Dict:
        """Get ClickHouse table metadata."""
        # Get row count
        count_result = self.client.execute(f"SELECT count() FROM {table}")
        row_count = count_result[0][0] if count_result else 0
        
        # Get schema
        desc_rows = self.client.execute(f"DESCRIBE TABLE {table}")
        columns = [row[0] for row in desc_rows]
        column_types = {row[0]: row[1] for row in desc_rows}
        
        # Get engine info
        try:
            engine_query = f"""
                SELECT engine, engine_full
                FROM system.tables
                WHERE name = '{table}'
                LIMIT 1
            """
            engine_result = self.client.execute(engine_query)
            engine = engine_result[0][0] if engine_result else "Unknown"
            engine_full = engine_result[0][1] if engine_result else "Unknown"
        except:
            engine = "Unknown"
            engine_full = "Unknown"
        
        return {
            "table_name": table,
            "row_count": row_count,
            "columns": columns,
            "column_types": column_types,
            "engine": engine,
            "engine_full": engine_full,
            "backend": "clickhouse",
            "primary_key": self.primary_key,
        }


class DuckDbBackend:
    """
    DuckDB cache storage backend adapter.
    
    Uses cached_duckdb.DuckDbCacheManager for low-level operations.
    Implements the StorageBackend protocol to work with generic CRUD API.
    
    Note: DuckDB cache is typically read-only. Write operations (create/update/delete)
    will raise NotImplementedError. Use cache.store() to populate data instead.
    
    Example:
        from cached_duckdb import DuckDbCacheManager
        from configflow import DuckDbBackend, create_crud_router
        
        cache = DuckDbCacheManager()
        cache.store(database="client_abc", table="sales", df=df)
        
        backend = DuckDbBackend(cache, database="client_abc")
        router = create_crud_router("sales", backend, read_only=True)
    """
    
    def __init__(self, cache_manager, database: str, primary_key: str = "id"):
        """
        Args:
            cache_manager: cached_duckdb.DuckDbCacheManager instance
            database: Database name in cache (e.g., "client_abc")
            primary_key: Name of primary key column
        """
        self.cache = cache_manager
        self.database = database
        self.primary_key = primary_key
    
    def query(self, table: str, filters: Dict[str, Any], limit: int, offset: int) -> List[Dict]:
        """Query DuckDB cache with SQL WHERE."""
        where_clauses = []
        for k, v in filters.items():
            if isinstance(v, str):
                where_clauses.append(f"{k} = '{v}'")
            elif isinstance(v, (int, float)):
                where_clauses.append(f"{k} = {v}")
            elif v is None:
                where_clauses.append(f"{k} IS NULL")
            else:
                # For other types, try string representation
                where_clauses.append(f"{k} = '{v}'")
        
        sql_where = " AND ".join(where_clauses) if where_clauses else None
        
        # Query from cache
        df = self.cache.query(
            database=self.database,
            table=table,
            sql_where=sql_where,
            limit=limit + offset  # Get extra rows for offset
        )
        
        # Apply offset in pandas
        if offset > 0:
            df = df.iloc[offset:]
        
        # Limit again after offset
        if limit > 0:
            df = df.head(limit)
        
        return df.to_dict('records')
    
    def create(self, table: str, data: Dict[str, Any]) -> Dict:
        """
        Create is not supported for DuckDB cache (read-only).
        Cache is populated via cache.store() with full DataFrame.
        """
        raise NotImplementedError(
            "DuckDB cache is typically read-only. Use cache.store() to populate data."
        )
    
    def update(self, table: str, id_value: Any, data: Dict[str, Any]) -> Dict:
        """Update not supported for DuckDB cache (read-only)."""
        raise NotImplementedError(
            "DuckDB cache is typically read-only. Use cache.store() to refresh data."
        )
    
    def delete(self, table: str, id_value: Any) -> bool:
        """Delete not supported for DuckDB cache (read-only)."""
        raise NotImplementedError(
            "DuckDB cache is typically read-only. Use cache.invalidate() to remove data."
        )
    
    def get_by_id(self, table: str, id_value: Any) -> Dict:
        """Get single record by ID."""
        results = self.query(table, {self.primary_key: id_value}, limit=1, offset=0)
        if not results:
            raise ValueError(f"Record with {self.primary_key}={id_value} not found in cache")
        return results[0]
    
    def get_info(self, table: str) -> Dict:
        """Get DuckDB cache table metadata."""
        # Get table info from cache manager
        info = self.cache.get_table_info(database=self.database, table=table)
        last_updated = self.cache.get_last_updated(database=self.database, table=table)
        
        # Add backend-specific info
        return {
            **info,
            "database": self.database,
            "last_updated": last_updated.isoformat() if last_updated else None,
            "exists": self.cache.exists(database=self.database, table=table),
            "backend": "duckdb",
            "primary_key": self.primary_key,
            "read_only": True,
        }
