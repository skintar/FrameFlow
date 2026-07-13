from __future__ import annotations

from typing import Any

import settings as app_settings
from providers.base import VideoProvider
from providers.openai_video import OpenAIVideoProvider


def list_providers() -> list[dict[str, Any]]:
    return app_settings.settings_for_ui()["providers"]


def get_provider(provider_id: str | None = None) -> VideoProvider:
    pid = provider_id or app_settings.get_active_provider_id()
    api_key = app_settings.get_api_key(pid)
    if not api_key:
        preset = next((p for p in app_settings.PROVIDER_CATALOG if p["id"] == pid), app_settings.PROVIDER_CATALOG[0])
        raise RuntimeError(f"Нет API-ключа ({preset['api_key_env']}). Откройте Настройки в FrameFlow.")

    base_url, models_url = app_settings.get_provider_urls(pid)
    preset = next((p for p in app_settings.PROVIDER_CATALOG if p["id"] == pid), app_settings.PROVIDER_CATALOG[0])
    return OpenAIVideoProvider(
        provider_id=pid,
        name=preset["name"],
        description=preset["description"],
        api_key=api_key,
        base_url=base_url,
        models_url=models_url or None,
    )


def provider_optional(provider_id: str | None = None) -> VideoProvider | None:
    try:
        return get_provider(provider_id)
    except RuntimeError:
        return None
