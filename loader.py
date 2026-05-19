from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .resolver import resolve_env_vars


def load_config_from_path(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    return resolve_env_vars(json.loads(path.read_text(encoding="utf-8")))


def load_json_config(config_path: Optional[str] = None, cwd: Optional[Path] = None) -> Dict[str, Any]:
    cwd = cwd or Path.cwd()

    if config_path:
        override = Path(config_path)
        config = load_config_from_path(override)
        if config:
            return config

    cwd_cfg = cwd / "config.json"
    config = load_config_from_path(cwd_cfg)
    if config:
        return config

    return {}


class ConfigLoader:
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path

    def load(self) -> Dict[str, Any]:
        return load_json_config(self.config_path)
