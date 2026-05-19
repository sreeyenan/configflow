from __future__ import annotations

import os
from typing import Any, Dict


def resolve_env_vars(value: Any) -> Any:
    """
    Recursively resolve environment variables in config values.
    Supports ${VAR} and ${VAR:default} syntax.
    """
    if isinstance(value, str):
        if value.startswith("${") and value.endswith("}"):
            expr = value[2:-1]
            if ":" in expr:
                env_var, default = expr.split(":", 1)
            else:
                env_var, default = expr, None
            resolved = os.getenv(env_var, default)
            return resolved if resolved is not None else value
        return value
    if isinstance(value, dict):
        return {k: resolve_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_env_vars(item) for item in value]
    return value
