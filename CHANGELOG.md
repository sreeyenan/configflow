# Changelog

## 0.2.0 (2026-05-16)

### ðŸš€ Major New Features

#### Generic CRUD API Factory (`crud_api.py`)
- **NEW**: `create_crud_router()` - Generic FastAPI router factory for any ClickHouse table
- Supports full CRUD operations (Create, Read, Update, Delete)
- Built-in pagination and filtering
- Version history support for versioned tables
- Composite primary key support
- Custom validators and field-level validations
- Async execution in thread pool
- Comprehensive error handling

**Use Case**: Eliminate 80-90% of boilerplate CRUD code by using a factory function instead of writing custom endpoints for each table.

**Example**: Replace 400+ lines of custom widget_query handler with 50 lines using the factory.

#### Config Management API (`config_api.py`)
- **NEW**: `create_config_router()` - FastAPI router factory specifically for ConfigStore
- Full CRUD on configurations with validation
- Section-based updates (e.g., update only `clickhouse` section)
- Version management (list, get, update, patch specific versions)
- Database introspection endpoints
- Reload callback support (e.g., recreate connection pools after config change)
- Authentication dependency support

**Use Case**: Consistent config management API across all microservices (engine, ETL, NLQ, gateway).

**Example**: Replace 150+ lines of custom config handler with 20 lines using the factory.

#### ClickHouse Table Creation Helpers
- **NEW**: `create_table_initializer()` - Generate CREATE TABLE SQL with full MergeTree support
  - All MergeTree engine variants (ReplacingMergeTree, SummingMergeTree, AggregatingMergeTree, etc.)
  - Partitioning (`PARTITION BY`)
  - Primary keys and ORDER BY
  - TTL policies for automatic data retention
  - Table settings (index_granularity, etc.)
  - Proper ClickHouse syntax
  
- **NEW**: `create_materialized_view_sql()` - Generate MATERIALIZED VIEW SQL
  - Target table syntax
  - Inline engine syntax
  - POPULATE option for backfilling
  - Real-time aggregations
  
**Use Case**: Properly configure ClickHouse tables with MergeTree engines, partitioning, TTL, and materialized views. No more manual SQL writing!

**Example**: See `widget_query_COMPLETE_EXAMPLE.py` for a full implementation with ReplacingMergeTree, SummingMergeTree, materialized views, and audit trails.

### ðŸ“¦ Optional Dependencies

Added optional dependency group for FastAPI support:
```bash
pip install configflow[api]  # FastAPI + Pydantic
pip install configflow[all]  # Everything (API + Cython)
```

Core library remains lightweight - FastAPI is only required if you use the API modules.

### ðŸ”§ API Exports

Updated `__init__.py` to export new APIs (with graceful fallback if FastAPI not installed):
- `create_crud_router` - Generic table CRUD factory
- `create_config_router` - Config management factory
- `create_table_initializer` - ClickHouse table creation helper
- `create_materialized_view_sql` - Materialized view helper

### ðŸ“ Documentation

- Updated **configflow_USER_MANUAL.md** with comprehensive ClickHouse concepts:
  - All MergeTree engine types and when to use them
  - Partitioning strategies (by month, day, custom)
  - TTL policies for data retention
  - Materialized views for real-time aggregations
  - Complete working examples
  
- Added **CLICKHOUSE_SUPPORT.md** - Dedicated guide for ClickHouse features

- Added **widget_query_COMPLETE_EXAMPLE.py** - Full working example showing:
  - ReplacingMergeTree for deduplication
  - SummingMergeTree for aggregation
  - Materialized views for real-time stats
  - Audit trail with TTL
  - CRUD APIs for all tables
  
- Updated README with comprehensive API usage examples

- Added **MIGRATION_GUIDE.md** - Step-by-step migration from custom handlers

### â™»ï¸ Code Reusability

Services can now:
1. **Eliminate code duplication**: Same CRUD pattern for all tables
2. **Consistent APIs**: All services expose standardized endpoints
3. **Rapid development**: Add new table CRUD in minutes, not hours
4. **Proper ClickHouse usage**: MergeTree engines, partitioning, TTL, materialized views
5. **Dual-mode architecture**: Works for both microservices (HTTP) and library mode (direct imports)

### ðŸ—„ï¸ ClickHouse Best Practices

The new helpers enforce ClickHouse best practices:
- âœ… Proper engine selection (ReplacingMergeTree for updates, SummingMergeTree for aggregations)
- âœ… Partitioning for query performance
- âœ… TTL for automatic data cleanup
- âœ… Materialized views for real-time dashboards
- âœ… Low cardinality types for memory optimization
- âœ… Enum types for type safety

### ðŸ”„ Version Bump

- Updated version from `0.1.1` â†’ `0.2.0`
- Updated pyproject.toml with new dependencies and keywords

### ðŸ› Breaking Changes

None - all existing APIs remain unchanged. New features are additive and optional.

---

## 0.1.1
- ConfigStore backend improvements
- Version management for configs

## 0.1.0
- Initial configflow with JSON loading and env placeholder resolution.
