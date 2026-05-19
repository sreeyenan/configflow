from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from .resolver import resolve_env_vars

logger = logging.getLogger(__name__)


@dataclass
class BackendSettings:
    backend: str = "clickhouse"
    config_name: str = "engine_config"
    environment: str = "default"


class ConfigStore:
    def __init__(
        self,
        initial_config: Dict[str, Any],
        clickhouse_params: Optional[Dict[str, Any]] = None,
        backend: Optional[str] = None,
        config_name: str = "engine_config",
        environment: Optional[str] = None,
        *,
        seed_db: bool = True,
        resolve_on_read: bool = True,
    ) -> None:
        # keep the raw initial config as provided (do not resolve before storing)
        self._initial_config_raw = initial_config or {}
        self._clickhouse_params = clickhouse_params or {}
        self._backend = (backend or os.getenv("DEFAULT_BACKEND", "clickhouse")).lower()
        self._config_name = config_name
        self._environment = environment or os.getenv("ENVIRONMENT", "default")
        self._seed_db = bool(seed_db)
        self._resolve_on_read = bool(resolve_on_read)
        self._cache: Optional[Dict[str, Any]] = None
        self._client = None

        if self._backend != "clickhouse":
            raise RuntimeError(
                f"Unsupported backend '{self._backend}'. Only clickhouse is supported right now."
            )

        self._connect_clickhouse()
        self._ensure_configs_table()
        self._load_or_seed_config()

    def _connect_clickhouse(self) -> None:
        try:
            from clickhouse_core import ClickHouseConfig, ClickHouseClient
        except ImportError as exc:
            raise RuntimeError("clickhouse-core is required for configflow clickhouse backend") from exc

        env_params = {
            "host": os.getenv("CLICKHOUSE_HOST"),
            "port": os.getenv("CLICKHOUSE_PORT"),
            "database": os.getenv("CLICKHOUSE_DATABASE"),
            "username": os.getenv("CLICKHOUSE_USERNAME"),
            "password": os.getenv("CLICKHOUSE_PASSWORD"),
        }

        base = {
            "host": env_params["host"] or self._clickhouse_params.get("host"),
            "port": env_params["port"] or self._clickhouse_params.get("port"),
            "database": env_params["database"] or self._clickhouse_params.get("database"),
            "username": env_params["username"] or self._clickhouse_params.get("username"),
            "password": env_params["password"] or self._clickhouse_params.get("password"),
        }

        if not all(base.values()):
            missing = [key for key, value in base.items() if not value]
            raise RuntimeError(f"Missing ClickHouse connection params: {missing}")

        cfg = ClickHouseConfig(
            host=str(base["host"]),
            port=int(base["port"]),
            database=str(base["database"]),
            username=str(base["username"]),
            password=str(base["password"]),
        )

        self._client = ClickHouseClient(cfg)
        logger.info("configflow connected to ClickHouse (%s:%s/%s)", cfg.host, cfg.port, cfg.database)

    def _ensure_configs_table(self) -> None:
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS configs (
            config_name String,
            environment String DEFAULT 'default',
            version UInt64,
            payload String,
            created_at DateTime DEFAULT now(),
            updated_at DateTime DEFAULT now()
        )
        ENGINE = MergeTree
        ORDER BY (config_name, environment, version)
        """
        self._client.execute(create_table_sql)

    def _load_or_seed_config(self) -> None:
        row = self._client.fetch_one(
            """
            SELECT version, payload
            FROM configs
            WHERE config_name = %(name)s AND environment = %(env)s
            ORDER BY version DESC
            LIMIT 1
            """,
            {"name": self._config_name, "env": self._environment},
        )

        if row:
            payload = json.loads(row["payload"])  # stored form (may contain placeholders)
            if self._resolve_on_read:
                payload = resolve_env_vars(payload)
            self._cache = payload
            logger.info("Loaded config '%s' from ClickHouse", self._config_name)
            return

        # No DB row found: seed from the raw initial config provided by caller
        payload_raw = self._initial_config_raw
        if not payload_raw:
            raise RuntimeError("Initial config is empty and no config found in database")

        if self._seed_db:
            # store the raw JSON as-is (placeholders preserved)
            self._client.execute(
                """
                INSERT INTO configs (config_name, environment, version, payload, updated_at)
                VALUES
                """,
                [(
                    self._config_name,
                    self._environment,
                    1,
                    json.dumps(payload_raw),
                    datetime.now(),
                )],
            )
            logger.info("Seeded config '%s' in ClickHouse (raw JSON stored)", self._config_name)
        else:
            logger.info("Seed disabled: using initial config in-memory without seeding DB")

        # cache resolved view for runtime (resolve placeholders now so callers get resolved values)
        cached = resolve_env_vars(payload_raw) if self._resolve_on_read else payload_raw
        self._cache = cached

    def get_config(self, refresh: bool = False) -> Dict[str, Any]:
        if self._cache is not None and not refresh:
            return self._cache
        self._load_or_seed_config()
        return self._cache or {}

    def create_config(self, payload: Dict[str, Any]) -> None:
        if not payload:
            raise RuntimeError("Config payload is empty")
        self._client.execute(
            """
            INSERT INTO configs (config_name, environment, version, payload, updated_at)
            VALUES
            """,
            [(
                self._config_name,
                self._environment,
                1,
                json.dumps(payload),
                datetime.now(),
            )],
        )
        self._cache = payload

    def update_config(self, payload: Dict[str, Any]) -> None:
        if not payload:
            raise RuntimeError("Config payload is empty")
        version = self._get_latest_version()
        self._mutate_payload(version, payload)
        self._cache = payload

    def update_config_version(self, version: int, payload: Dict[str, Any]) -> None:
        if not payload:
            raise RuntimeError("Config payload is empty")
        if version <= 0:
            raise RuntimeError("Version must be a positive integer")
        self._mutate_payload(version, payload)
        # do not update cache unless it is the latest version
        if version == self._get_latest_version():
            self._cache = payload

    def patch_config(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        current = self.get_config(refresh=True)
        merged = _deep_merge(current, patch)
        version = self._get_latest_version()
        self._mutate_payload(version, merged)
        self._cache = merged
        return merged

    def patch_config_version(self, version: int, patch: Dict[str, Any]) -> Dict[str, Any]:
        if version <= 0:
            raise RuntimeError("Version must be a positive integer")
        if not patch:
            raise RuntimeError("Patch payload is empty")

        row = self._client.fetch_one(
            """
            SELECT payload
            FROM configs
            WHERE config_name = %(name)s AND environment = %(env)s AND version = %(version)s
            LIMIT 1
            """,
            {"name": self._config_name, "env": self._environment, "version": version},
        )

        if not row:
            raise RuntimeError(f"Config version {version} not found")

        current = json.loads(row["payload"])
        merged = _deep_merge(current, patch)
        self._mutate_payload(version, merged)

        if version == self._get_latest_version():
            self._cache = merged
        return merged

    def delete_config(self) -> None:
        self._client.execute(
            """
            ALTER TABLE configs
            DELETE WHERE config_name = %(name)s AND environment = %(env)s
            """,
            {"name": self._config_name, "env": self._environment},
        )
        self._cache = None

    def _get_latest_version(self) -> int:
        row = self._client.fetch_one(
            """
            SELECT max(version) AS version
            FROM configs
            WHERE config_name = %(name)s AND environment = %(env)s
            """,
            {"name": self._config_name, "env": self._environment},
        )
        return int(row["version"] or 1)

    def _mutate_payload(self, version: int, payload: Dict[str, Any]) -> None:
        self._client.execute(
            """
            ALTER TABLE configs
            UPDATE payload = %(payload)s, updated_at = now()
            WHERE config_name = %(name)s AND environment = %(env)s AND version = %(version)s
            """,
            {
                "payload": json.dumps(payload),
                "name": self._config_name,
                "env": self._environment,
                "version": version,
            },
        )


def _deep_merge(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
