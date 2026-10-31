import json
import os
import sys
from pathlib import Path

APP_NAME = "BytegoImageMaster"
APP_TITLE = "Bytego中转站GPT-Image/Grok Image Master"
VERSION = "1.1.0"
# HTTP 头只能用 ASCII，所以单独给一个英文 UA
USER_AGENT = "BytegoImageMaster/1.1"

# 开发者信息（界面与关于页都会展示）
DEVELOPER = "NL-1234"
DEVELOPER_QQ = "2265242381"

# 固定的两个中转端点：国际站 / 国内直连
ENDPOINTS = {
    "global": {
        "label": "国际站",
        "url": "https://bytego.team/v1",
        "hint": "默认线路，海外网络直连",
    },
    "cn": {
        "label": "国内直连",
        "url": "https://bytego.xyz/v1",
        "hint": "国内网络更稳，延迟更低",
    },
}
DEFAULT_ENDPOINT = "global"


def endpoint_url(key: str) -> str:
    item = ENDPOINTS.get(key) or ENDPOINTS[DEFAULT_ENDPOINT]
    return item["url"]


def endpoint_label(key: str) -> str:
    item = ENDPOINTS.get(key) or ENDPOINTS[DEFAULT_ENDPOINT]
    return item["label"]


def data_dir() -> Path:
    override = os.environ.get("BYTEGO_HOME") or os.environ.get("HILIAND_HOME")
    if override:
        d = Path(override)
        d.mkdir(parents=True, exist_ok=True)
        return d
    if sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return data_dir() / "config.json"


def history_path() -> Path:
    return data_dir() / "history.json"


def default_output_dir() -> str:
    pics = Path.home() / "Pictures"
    root = pics if pics.exists() else Path.home()
    return str(root / APP_NAME)


DEFAULT_CONFIG = {
    "endpoint": DEFAULT_ENDPOINT,
    "base_url": endpoint_url(DEFAULT_ENDPOINT),
    "api_key": "",
    "image_model": "gpt-image-2",
    "chat_model": "gpt-4o",
    "size": "4096x4096",
    "quality": "auto",
    "count": 1,
    "output_format": "png",
    "transparent": False,
    "max_retries": 5,
    "timeout": 1000,
    "auto_approve": False,
    "output_dir": "",
    "allow_command": True,
    "allow_write": True,
    "allow_open": True,
    "allow_generate": True,
}


def _read_json(path: Path, fallback):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return fallback


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(_read_json(config_path(), {}) or {})
    if not cfg.get("output_dir"):
        cfg["output_dir"] = default_output_dir()
    # 端点是固定的：base_url 永远跟着 endpoint 走
    key = cfg.get("endpoint") if cfg.get("endpoint") in ENDPOINTS else DEFAULT_ENDPOINT
    cfg["endpoint"] = key
    # 仅供自动化测试用的后门：设置 BYTEGO_BASE_URL 可把请求指向本地 mock 服务，
    # 正常使用时不存在这个环境变量，地址恒为所选中转站。
    override = (os.environ.get("BYTEGO_BASE_URL") or "").strip()
    cfg["base_url"] = override or endpoint_url(key)
    return cfg


def save_config(cfg: dict) -> None:
    _write_json(config_path(), cfg)


def load_history() -> list:
    data = _read_json(history_path(), [])
    return data if isinstance(data, list) else []


def save_history(items: list) -> None:
    _write_json(history_path(), items[:500])
