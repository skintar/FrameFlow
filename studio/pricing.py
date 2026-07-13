from __future__ import annotations

import time
from typing import Any

from config import BUDGET_NO_AUDIO, DEFAULT_SIZE, MAX_CHARACTER_REFERENCES, MAX_PROJECT_CHARACTERS, MODEL_LABELS

_cache: dict[str, dict[str, Any]] = {}
_CACHE_TTL = 300

PROVIDER_LABELS = {
    "bytedance": "ByteDance",
    "alibaba": "Alibaba / Wan",
    "kwaivgi": "Kling",
    "google": "Google Veo",
    "openai": "OpenAI Sora",
    "x-ai": "xAI Grok",
    "minimax": "MiniMax",
}


def _price_table(model: dict[str, Any], with_audio: bool = True) -> dict[str, float]:
    key = "size_prices" if with_audio else "size_prices_no_audio"
    table = model.get(key) or model.get("size_prices") or {}
    return {k: float(v) for k, v in table.items()}


def price_per_second(model: dict[str, Any], size: str, with_audio: bool = True) -> float:
    prices = _price_table(model, with_audio)
    if size in prices:
        return prices[size]
    return float(model.get("max_price_per_second", 0))


def estimate_clip_cost(
    model: dict[str, Any],
    *,
    size: str,
    duration: int,
    with_audio: bool = True,
) -> float:
    return round(price_per_second(model, size, with_audio) * duration, 2)


def min_duration(model: dict[str, Any]) -> int:
    durations = [int(d) for d in (model.get("supported_durations") or [4])]
    return min(durations)


def max_duration(model: dict[str, Any]) -> int:
    durations = [int(d) for d in (model.get("supported_durations") or [5])]
    return max(durations)


def cheapest_size(model: dict[str, Any], with_audio: bool | None = None) -> str:
    if with_audio is None:
        with_audio = not BUDGET_NO_AUDIO
    prices = _price_table(model, with_audio)
    sizes = model.get("supported_sizes") or [DEFAULT_SIZE]
    if not prices:
        return sizes[0]
    affordable = {s: prices[s] for s in sizes if s in prices}
    if not affordable:
        return sizes[0]
    return min(affordable, key=affordable.get)


def min_clip_cost(model: dict[str, Any], *, with_audio: bool | None = None) -> dict[str, Any]:
    if with_audio is None:
        with_audio = not BUDGET_NO_AUDIO
    duration = min_duration(model)
    size = cheapest_size(model, with_audio)
    pps = price_per_second(model, size, with_audio)
    return {
        "duration_sec": duration,
        "size": size,
        "price_per_second": pps,
        "min_cost_rub": estimate_clip_cost(model, size=size, duration=duration, with_audio=with_audio),
    }


def model_label(model_id: str) -> str:
    if model_id in MODEL_LABELS:
        return MODEL_LABELS[model_id]
    return model_id.replace("-", " ").replace("_", " ").title()


async def fetch_video_models(provider_id: str | None = None, force: bool = False) -> dict[str, Any]:
    import settings as app_settings
    from providers.registry import get_provider

    pid = provider_id or app_settings.get_active_provider_id()
    now = time.time()
    bucket = _cache.setdefault(pid, {"models": {}, "fetched_at": 0.0})
    if not force and bucket["models"] and now - bucket["fetched_at"] < _CACHE_TTL:
        return bucket["models"]

    provider = get_provider(pid)
    models = await provider.fetch_models(force=force)
    bucket["models"] = models
    bucket["fetched_at"] = now
    return models


def get_model(models: dict[str, Any], model_id: str) -> dict[str, Any]:
    if model_id not in models:
        raise KeyError(f"Unknown model: {model_id}")
    return models[model_id]


def models_for_ui(models: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for model_id, m in models.items():
        with_audio = not BUDGET_NO_AUDIO
        min_info = min_clip_cost(m, with_audio=with_audio)
        chain = bool(m.get("supported_frame_images"))
        durations = sorted(int(d) for d in (m.get("supported_durations") or [4]))
        sizes = list(m.get("supported_sizes") or [])
        items.append(
            {
                "id": model_id,
                "label": model_label(model_id),
                "provider": PROVIDER_LABELS.get(m.get("provider", ""), m.get("provider", "")),
                "supports_chain": chain,
                "supports_refs": bool(m.get("supports_reference_images")),
                "max_refs": MAX_CHARACTER_REFERENCES if m.get("supports_reference_images") else 0,
                "max_project_characters": MAX_PROJECT_CHARACTERS if m.get("supports_reference_images") else 0,
                "supports_audio": bool(m.get("generate_audio")),
                "min_duration": durations[0] if durations else 4,
                "max_duration": durations[-1] if durations else 10,
                "durations": durations,
                "min_cost_rub": min_info["min_cost_rub"],
                "cheapest_size": min_info["size"],
                "price_per_second": min_info["price_per_second"],
                "sizes": sizes,
                "tier": "budget" if min_info["min_cost_rub"] < 20 else "standard" if min_info["min_cost_rub"] < 80 else "premium",
            }
        )
    items.sort(key=lambda x: (not x["supports_chain"], x["min_cost_rub"]))
    return items


def snap_duration(model: dict[str, Any], seconds: float) -> int:
    """Ближайшая допустимая длительность из supported_durations модели."""
    durations = sorted(int(d) for d in (model.get("supported_durations") or [4]))
    target = int(round(seconds))
    if target in durations:
        return target
    return min(durations, key=lambda d: abs(d - target))


def pick_duration(model: dict[str, Any], seconds: float) -> int:
    return snap_duration(model, seconds)


def pick_size(model: dict[str, Any], preferred: str = DEFAULT_SIZE) -> str:
    sizes = model.get("supported_sizes") or [DEFAULT_SIZE]
    if preferred in sizes:
        return preferred
    return cheapest_size(model)


def clamp_clip_seconds(model: dict[str, Any], seconds: float) -> float:
    durations = sorted(int(d) for d in (model.get("supported_durations") or [4]))
    lo, hi = durations[0], durations[-1]
    return float(max(lo, min(hi, round(seconds))))
