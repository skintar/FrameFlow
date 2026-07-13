from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

import settings as app_settings
from config import (
    BUDGET_NO_AUDIO,
    DEFAULT_DURATION,
    DEFAULT_MODEL,
    DEFAULT_SIZE,
    MAX_CHARACTER_REFERENCES,
    MAX_PROJECT_CHARACTERS,
    STATIC_DIR,
    STYLE_PRESETS,
)
from pipeline import GenerationPipeline, ProjectStore, load_api_key
from pricing import (
    estimate_clip_cost,
    fetch_video_models,
    get_model,
    min_clip_cost,
    models_for_ui,
    pick_duration,
    pick_size,
    price_per_second,
    snap_duration,
)
from providers.registry import get_provider, provider_optional

app = FastAPI(title="FrameFlow", description="Локальная студия цепочной генерации видео", version="1.0.0")
pipeline = GenerationPipeline()
store = ProjectStore()

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/media", StaticFiles(directory=str(store.root)), name="media")


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/api/health")
async def health() -> dict[str, Any]:
    active = app_settings.get_active_provider_id()
    client_ok = False
    model_count = 0
    provider = provider_optional(active)
    if provider:
        client_ok = provider.check_key()
    try:
        model_count = len(await fetch_video_models(active))
    except Exception:
        pass
    preset = next((p for p in app_settings.PROVIDER_CATALOG if p["id"] == active), {})
    return {
        "studio": "ok",
        "product": "FrameFlow",
        "version": "1.0.0",
        "active_provider": active,
        "provider_name": preset.get("name", active),
        "api_key_set": bool(load_api_key(active)),
        "provider_ok": client_ok,
        "model_count": model_count,
        "budget_mode": BUDGET_NO_AUDIO,
        "max_project_characters": MAX_PROJECT_CHARACTERS,
        "max_api_references": MAX_CHARACTER_REFERENCES,
        "styles": {k: v["label"] for k, v in STYLE_PRESETS.items()},
    }


@app.get("/api/settings")
async def get_settings() -> dict[str, Any]:
    return app_settings.settings_for_ui()


@app.post("/api/settings")
async def save_settings(body: dict[str, Any]) -> dict[str, Any]:
    try:
        return app_settings.apply_settings(body)
    except Exception as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/providers")
async def providers_list() -> dict[str, Any]:
    return {"providers": app_settings.PROVIDER_CATALOG, "settings": app_settings.settings_for_ui()}


@app.get("/api/models")
async def list_models(refresh: bool = False, provider: str | None = None) -> dict[str, Any]:
    pid = provider or app_settings.get_active_provider_id()
    try:
        models = await fetch_video_models(pid, force=refresh)
        return {"models": models_for_ui(models), "count": len(models), "provider": pid}
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"Не удалось загрузить модели: {exc}")


@app.get("/api/projects/list")
async def list_projects() -> dict[str, Any]:
    return {"projects": store.list_projects()}


async def compute_calc(
    *,
    model: str = DEFAULT_MODEL,
    size: str = DEFAULT_SIZE,
    clip_count: int = 5,
    clip_seconds: float = DEFAULT_DURATION,
    target_total_seconds: float | None = None,
    drive: str = "clip",
    provider: str | None = None,
) -> dict[str, Any]:
    pid = provider or app_settings.get_active_provider_id()
    models = await fetch_video_models(pid)
    model_info = get_model(models, model)
    clip_count = max(1, min(clip_count, 200))

    if drive == "total" and target_total_seconds and target_total_seconds > 0:
        clip_seconds = round(target_total_seconds / clip_count, 2)
    else:
        clip_seconds = float(clip_seconds)

    duration = snap_duration(model_info, clip_seconds)
    size = pick_size(model_info, size)
    with_audio = not BUDGET_NO_AUDIO

    per_clip = estimate_clip_cost(model_info, size=size, duration=duration, with_audio=with_audio)
    min_one = min_clip_cost(model_info, with_audio=with_audio)
    pps = price_per_second(model_info, size, with_audio)
    total = round(per_clip * clip_count, 2)

    mins = int((clip_count * duration) // 60)
    secs = int((clip_count * duration) % 60)
    ui_model = next((m for m in models_for_ui(models) if m["id"] == model), None)

    return {
        "model": model,
        "size": size,
        "clip_count": clip_count,
        "clip_seconds": float(duration),
        "requested_clip_seconds": clip_seconds,
        "effective_clip_seconds": float(duration),
        "total_seconds": round(clip_count * duration, 2),
        "total_label": f"{mins} мин {secs} сек" if mins else f"{secs} сек",
        "cost_per_clip_rub": per_clip,
        "price_per_second_rub": round(pps, 2),
        "min_cost_per_clip_rub": min_one["min_cost_rub"],
        "total_cost_rub": total,
        "supports_chain": bool(model_info.get("supported_frame_images")),
        "min_duration": ui_model["min_duration"] if ui_model else duration,
        "max_duration": ui_model["max_duration"] if ui_model else duration,
        "budget_mode": BUDGET_NO_AUDIO,
        "provider": pid,
        "warning": None if ui_model and ui_model["supports_chain"] else (
            "Модель без цепочки кадров — каждый клип генерируется отдельно."
        ),
    }


@app.get("/api/calc")
async def calc_endpoint(
    model: str = DEFAULT_MODEL,
    size: str = DEFAULT_SIZE,
    clip_count: int = 5,
    clip_seconds: float = DEFAULT_DURATION,
    target_total_seconds: float | None = None,
    drive: str = "clip",
    provider: str | None = None,
) -> dict[str, Any]:
    try:
        return await compute_calc(
            model=model,
            size=size,
            clip_count=clip_count,
            clip_seconds=clip_seconds,
            target_total_seconds=target_total_seconds,
            drive=drive,
            provider=provider,
        )
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/projects")
async def create_project(
    title: str = Form("Новый проект"),
    style: str = Form("cinematic"),
    model: str = Form(DEFAULT_MODEL),
    size: str = Form(DEFAULT_SIZE),
    clip_count: int = Form(5),
    clip_seconds: float = Form(DEFAULT_DURATION),
    target_total_seconds: float = Form(0),
    provider: str = Form(""),
) -> dict[str, Any]:
    if style not in STYLE_PRESETS:
        raise HTTPException(400, "Неизвестный стиль")
    pid = provider.strip() or app_settings.get_active_provider_id()
    try:
        calc_data = await compute_calc(
            model=model,
            size=size,
            clip_count=clip_count,
            clip_seconds=clip_seconds,
            target_total_seconds=target_total_seconds or None,
            provider=pid,
        )
    except KeyError:
        raise HTTPException(400, f"Неизвестная модель: {model}")
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))
    spec = pipeline.create_project(
        title=title,
        style=style,
        model=calc_data["model"],
        size=calc_data["size"],
        clip_count=calc_data["clip_count"],
        clip_seconds=calc_data["clip_seconds"],
        target_total_seconds=calc_data["total_seconds"],
        provider=pid,
    )
    return {"project": spec.to_dict(), "calc": calc_data}


@app.get("/api/projects/{project_id}")
async def get_project(project_id: str) -> dict[str, Any]:
    try:
        spec = store.load_spec(project_id)
    except FileNotFoundError:
        raise HTTPException(404, "Проект не найден")
    calc_data = await compute_calc(
        model=spec.model,
        size=spec.size,
        clip_count=spec.clip_count,
        clip_seconds=spec.clip_seconds,
        target_total_seconds=spec.target_total_seconds,
        provider=spec.provider,
    )
    return {"project": spec.to_dict(), "calc": calc_data}


@app.post("/api/projects/{project_id}/clips")
async def save_clips(project_id: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        spec = pipeline.update_clips(project_id, body.get("clips", []))
    except FileNotFoundError:
        raise HTTPException(404, "Проект не найден")
    return {"project": spec.to_dict()}


@app.post("/api/projects/{project_id}/clips/{clip_index}/refs")
async def upload_ref(project_id: str, clip_index: int, file: UploadFile = File(...)) -> dict[str, Any]:
    refs_dir = store.refs_dir(project_id, clip_index)
    dest = refs_dir / (file.filename or "ref.png")
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    rel = store.rel_path(project_id, dest)
    spec = store.load_spec(project_id)
    for clip in spec.clips:
        if clip.index == clip_index:
            if len(clip.reference_paths) >= MAX_PROJECT_CHARACTERS:
                raise HTTPException(400, f"Максимум {MAX_PROJECT_CHARACTERS} фото на клип")
            if rel not in clip.reference_paths:
                clip.reference_paths.append(rel)
    store.save_spec(spec)
    return {"path": rel, "filename": dest.name, "url": f"/media/{project_id}/{rel}"}


@app.delete("/api/projects/{project_id}/clips/{clip_index}/refs/{filename}")
async def delete_clip_ref(project_id: str, clip_index: int, filename: str) -> dict[str, Any]:
    spec = store.load_spec(project_id)
    for clip in spec.clips:
        if clip.index == clip_index:
            clip.reference_paths = [p for p in clip.reference_paths if not p.endswith(filename)]
    store.save_spec(spec)
    path = store.refs_dir(project_id, clip_index) / filename
    if path.exists():
        path.unlink()
    return {"project": spec.to_dict()}


@app.post("/api/projects/{project_id}/characters")
async def upload_character(project_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
    chars_dir = store.characters_dir(project_id)
    dest = chars_dir / (file.filename or "character.png")
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    rel = store.rel_path(project_id, dest)
    spec = store.load_spec(project_id)
    if len(spec.global_characters) >= MAX_PROJECT_CHARACTERS:
        raise HTTPException(400, f"Максимум {MAX_PROJECT_CHARACTERS} персонажей в проекте")
    if rel not in spec.global_characters:
        spec.global_characters.append(rel)
    store.save_spec(spec)
    return {"path": rel, "filename": dest.name, "url": f"/media/{project_id}/{rel}", "project": spec.to_dict()}


@app.delete("/api/projects/{project_id}/characters/{filename}")
async def delete_character(project_id: str, filename: str) -> dict[str, Any]:
    spec = store.load_spec(project_id)
    spec.global_characters = [p for p in spec.global_characters if not p.endswith(filename)]
    for clip in spec.clips:
        clip.reference_paths = [p for p in clip.reference_paths if not p.endswith(filename)]
    store.save_spec(spec)
    path = store.characters_dir(project_id) / filename
    if path.exists():
        path.unlink()
    return {"project": spec.to_dict()}


@app.post("/api/projects/{project_id}/characters/apply-all")
async def apply_characters_all(project_id: str) -> dict[str, Any]:
    try:
        spec = store.apply_global_to_all_clips(project_id)
    except FileNotFoundError:
        raise HTTPException(404, "Проект не найден")
    return {"project": spec.to_dict()}


@app.post("/api/projects/{project_id}/generate")
async def generate(project_id: str) -> dict[str, Any]:
    try:
        spec = store.load_spec(project_id)
    except FileNotFoundError:
        raise HTTPException(404, "Проект не найден")
    if not load_api_key(spec.provider):
        raise HTTPException(400, "Укажите API-ключ в Настройках FrameFlow")
    return {
        "job_id": pipeline.start_job(project_id),
        "clips_done": pipeline.clips_already_done(project_id),
    }


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str) -> dict[str, Any]:
    job = pipeline.get_job(job_id)
    if not job:
        raise HTTPException(404, "Задача не найдена")
    data = job.to_dict()
    for clip in data["clips"]:
        if clip.get("video_path"):
            rel = Path(clip["video_path"]).relative_to(store.root)
            clip["video_url"] = f"/media/{rel.as_posix()}"
    if data.get("final_video_path"):
        rel = Path(data["final_video_path"]).relative_to(store.root)
        data["final_video_url"] = f"/media/{rel.as_posix()}"
    return data


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> dict[str, str]:
    pipeline.cancel_job(job_id)
    return {"status": "cancelling"}


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    icon = STATIC_DIR / "favicon.svg"
    if icon.exists():
        return FileResponse(icon, media_type="image/svg+xml")
    raise HTTPException(404)
