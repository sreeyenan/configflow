# config_core Environment Variables

`config_core` resolves values from environment variables using the syntax:

```
${VAR}
${VAR:default}
```

Example in JSON:

```json
{
  "service": {
    "host": "${SERVICE_HOST:0.0.0.0}",
    "port": "${SERVICE_PORT:8030}",
    "debug": "${DEBUG:false}"
  }
}
```

If `SERVICE_HOST` is set, it will be used. If not, the default `0.0.0.0` is used.

## Backend selection

- `DEFAULT_BACKEND` (default: `clickhouse`)

## ClickHouse connection

The ClickHouse backend uses env vars first; if missing, it falls back to
the `clickhouse_params` passed into `ConfigStore`.

- `CLICKHOUSE_HOST`
- `CLICKHOUSE_PORT`
- `CLICKHOUSE_DATABASE`
- `CLICKHOUSE_USERNAME`
- `CLICKHOUSE_PASSWORD`

Per-DB overrides (if you choose to extend later):

- `<DBNAME>_USERNAME`
- `<DBNAME>_PASSWORD`
