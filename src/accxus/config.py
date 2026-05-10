from __future__ import annotations

import logging
from pathlib import Path

from rigi import config_dir, data_dir

from accxus.types.core import AppConfig

log = logging.getLogger(__name__)

APP_NAME = "accxus"

CONFIG_DIR: Path = config_dir(APP_NAME)
DATA_DIR: Path = data_dir(APP_NAME)
SESSIONS_DIR: Path = DATA_DIR / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

_cfg_file: Path = CONFIG_DIR / "config.json"


def load_config() -> AppConfig:
    if _cfg_file.exists():
        try:
            return AppConfig.model_validate_json(_cfg_file.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"[config] parse error ({e}), using defaults")
    cfg = AppConfig()
    save_config(cfg)
    return cfg


def save_config(cfg: AppConfig) -> None:
    _cfg_file.write_text(cfg.model_dump_json(indent=2), encoding="utf-8")


config: AppConfig = load_config()

TG_API_ID: int = config.tg_api_id
TG_API_HASH: str = config.tg_api_hash
