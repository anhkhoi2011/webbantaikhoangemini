"""Merge server credentials from an ignored local file or environment variables."""
import json
import os
from pathlib import Path


def with_runtime_secrets(filename, config, base_dir):
    section = {"payment_config.json": "payment", "telegram_config.json": "telegram", "telegram_buyer": "telegramBuyer"}.get(Path(filename).name)
    if not section or not isinstance(config, dict):
        return config
    result = dict(config)
    try:
        private = json.loads((Path(base_dir) / "runtime_secrets.json").read_text(encoding="utf-8-sig"))
        result.update({k: v for k, v in private.get(section, {}).items() if v})
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    if section == "payment":
        access = os.environ.get("APIPAY_ACCESS_KEY")
        if access:
            result.update(accessKey=access, apiKey=access)
        secret = os.environ.get("APIPAY_SECRET_KEY")
        if secret:
            result["secretKey"] = secret
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if token:
        result["botToken" if section == "telegram" else "telegramBotToken"] = token
    return result


def separate_runtime_secrets(filename, config, base_dir):
    fields = {
        "payment_config.json": ("payment", ("apiKey", "accessKey", "secretKey", "telegramBotToken")),
        "telegram_config.json": ("telegram", ("botToken",)),
    }.get(Path(filename).name)
    if not fields or not isinstance(config, dict):
        return config
    section, names = fields
    private_path = Path(base_dir) / "runtime_secrets.json"
    incoming = {key: config[key] for key in names if config.get(key)}
    if incoming:
        try:
            private = json.loads(private_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            private = {}
        private.setdefault(section, {}).update(incoming)
        temporary = private_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(private, indent=2) + "\n", encoding="utf-8")
        temporary.replace(private_path)
    return {key: ("" if key in names else value) for key, value in config.items()}
