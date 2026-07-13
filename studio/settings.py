from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from config import ENV_FILE

PROVIDER_CATALOG: list[dict[str, Any]] = [
    {
        "id": "aitunnel",
        "name": "AITunnel",
        "description": "Облачная генерация видео, оплата в рублях. Рекомендуется для старта.",
        "base_url": "https://api.aitunnel.ru/v1",
        "models_url": "https://api.aitunnel.ru/public/aitunnel/models/videos",
        "api_key_env": "AITUNNEL_API_KEY",
        "docs_url": "https://docs.aitunnel.ru",
    },
    {
        "id": "custom",
        "name": "Свой API",
        "description": "Любой OpenAI-совместимый Video API: свой URL и ключ.",
        "base_url_env": "CUSTOM_BASE_URL",
        "models_url_env": "CUSTOM_MODELS_URL",
        "api_key_env": "CUSTOM_API_KEY",
        "default_base_url": "https://api.openai.com/v1",
        "default_models_url": "",
    },
]

_ENV_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def read_env_file() -> dict[str, str]:
    data: dict[str, str] = {}
    if not ENV_FILE.exists():
        return data
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _ENV_KEY.match(line)
        if m:
            key, val = m.group(1), m.group(2).strip().strip('"').strip("'")
            data[key] = val
    return data


def write_env_file(updates: dict[str, str]) -> None:
    current = read_env_file()
    current.update({k: v for k, v in updates.items() if v is not None})
    lines: list[str] = []
    if ENV_FILE.exists():
        for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                lines.append(raw)
                continue
            m = _ENV_KEY.match(stripped)
            if m and m.group(1) in updates:
                continue
            lines.append(raw)
    else:
        lines = [
            "# FrameFlow — настройки API",
            "# Документация: https://github.com/skintar/FrameFlow",
            "",
        ]
    for key, val in updates.items():
        if val is None:
            continue
        lines.append(f"{key}={val}")
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for key, val in updates.items():
        if val:
            os.environ[key] = val


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "••••••••"
    return f"{value[:4]}••••{value[-4:]}"


def get_active_provider_id() -> str:
    env = read_env_file()
    return env.get("FRAMEFLOW_PROVIDER", os.environ.get("FRAMEFLOW_PROVIDER", "aitunnel"))


def get_api_key(provider_id: str | None = None) -> str | None:
    pid = provider_id or get_active_provider_id()
    preset = next((p for p in PROVIDER_CATALOG if p["id"] == pid), PROVIDER_CATALOG[0])
    env_name = preset["api_key_env"]
    key = os.environ.get(env_name, "").strip()
    if key:
        return key
    env = read_env_file()
    return env.get(env_name, "").strip() or None


def get_provider_urls(provider_id: str | None = None) -> tuple[str, str]:
    pid = provider_id or get_active_provider_id()
    preset = next((p for p in PROVIDER_CATALOG if p["id"] == pid), PROVIDER_CATALOG[0])
    env = read_env_file()

    if pid == "custom":
        base = env.get("CUSTOM_BASE_URL") or preset.get("default_base_url", "")
        models = env.get("CUSTOM_MODELS_URL") or f"{base.rstrip('/')}/models"
        return base.rstrip("/"), models.rstrip("/")

    return preset["base_url"].rstrip("/"), preset["models_url"].rstrip("/")


def settings_for_ui() -> dict[str, Any]:
    env = read_env_file()
    active = get_active_provider_id()
    providers = []
    for p in PROVIDER_CATALOG:
        key_env = p["api_key_env"]
        key = env.get(key_env, "")
        item = {
            "id": p["id"],
            "name": p["name"],
            "description": p["description"],
            "has_key": bool(key),
            "api_key_masked": mask_secret(key),
            "docs_url": p.get("docs_url"),
        }
        if p["id"] == "custom":
            item["base_url"] = env.get("CUSTOM_BASE_URL", p.get("default_base_url", ""))
            item["models_url"] = env.get("CUSTOM_MODELS_URL", "")
        providers.append(item)
    return {
        "active_provider": active,
        "providers": providers,
        "env_path": str(ENV_FILE),
    }


def apply_settings(body: dict[str, Any]) -> dict[str, Any]:
    updates: dict[str, str] = {}
    provider = body.get("active_provider")
    if provider in {p["id"] for p in PROVIDER_CATALOG}:
        updates["FRAMEFLOW_PROVIDER"] = provider

    api_key = (body.get("api_key") or "").strip()
    if api_key and not api_key.startswith("••"):
        preset = next((p for p in PROVIDER_CATALOG if p["id"] == (provider or get_active_provider_id())), None)
        if preset:
            updates[preset["api_key_env"]] = api_key

    if provider == "custom" or get_active_provider_id() == "custom":
        if body.get("base_url"):
            updates["CUSTOM_BASE_URL"] = body["base_url"].strip().rstrip("/")
        if body.get("models_url") is not None:
            updates["CUSTOM_MODELS_URL"] = body["models_url"].strip().rstrip("/")

    if updates:
        write_env_file(updates)
    return settings_for_ui()
