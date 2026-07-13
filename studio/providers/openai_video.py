from __future__ import annotations

import base64
import mimetypes
import time
from pathlib import Path
from typing import Any, Callable

import httpx

from providers.base import VideoProvider, VideoProviderError


def image_to_data_url(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    mime = mime or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


class OpenAIVideoProvider(VideoProvider):
    """OpenAI-совместимый Video API: POST /videos, GET /videos/{id}."""

    def __init__(
        self,
        *,
        provider_id: str,
        name: str,
        description: str,
        api_key: str,
        base_url: str,
        models_url: str | None = None,
    ) -> None:
        self.id = provider_id
        self.name = name
        self.description = description
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.models_url = (models_url or f"{self.base_url}/models").rstrip("/")
        self._models_cache: dict[str, Any] | None = None
        self._models_fetched_at = 0.0
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def check_key(self) -> bool:
        if not self.api_key:
            return False
        try:
            with httpx.Client(timeout=12.0) as client:
                r = client.get(f"{self.base_url}/models", headers=self.headers)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def fetch_models(self, *, force: bool = False) -> dict[str, Any]:
        now = time.time()
        if not force and self._models_cache and now - self._models_fetched_at < 300:
            return self._models_cache
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(self.models_url, headers=self.headers)
            r.raise_for_status()
            data = r.json()
        if isinstance(data, dict) and "data" in data:
            models = {m["id"]: m for m in data["data"] if isinstance(m, dict) and "id" in m}
        elif isinstance(data, dict):
            models = data
        else:
            models = {}
        self._models_cache = models
        self._models_fetched_at = now
        return models

    def create_video(
        self,
        *,
        model: str,
        prompt: str,
        duration: int,
        size: str,
        first_frame: Path | None = None,
        reference_images: list[Path] | None = None,
        generate_audio: bool | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "duration": duration,
            "size": size,
        }
        if generate_audio is not None:
            body["generate_audio"] = generate_audio

        if first_frame and first_frame.exists():
            body["frame_images"] = [
                {
                    "type": "image_url",
                    "image_url": {"url": image_to_data_url(first_frame)},
                    "frame_type": "first_frame",
                }
            ]
        elif reference_images:
            body["input_references"] = [
                {
                    "type": "image_url",
                    "image_url": {"url": image_to_data_url(path)},
                }
                for path in reference_images[:2]
                if path.exists()
            ]

        with httpx.Client(timeout=120.0) as client:
            r = client.post(f"{self.base_url}/videos", headers=self.headers, json=body)
        if r.status_code not in (200, 202):
            raise VideoProviderError(r.text or f"HTTP {r.status_code}")
        return r.json()

    def get_video(self, job_id: str) -> dict[str, Any]:
        with httpx.Client(timeout=60.0) as client:
            r = client.get(f"{self.base_url}/videos/{job_id}", headers=self.headers)
        r.raise_for_status()
        return r.json()

    def wait_for_video(
        self,
        job_id: str,
        *,
        timeout_sec: int = 1800,
        poll_sec: float = 15.0,
        on_tick: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            status = self.get_video(job_id)
            if on_tick:
                on_tick(status)
            state = status.get("status")
            if state == "completed":
                return status
            if state == "failed":
                err = status.get("error")
                if isinstance(err, dict):
                    err = err.get("message") or str(err)
                raise VideoProviderError(err or "Генерация не удалась")
            time.sleep(poll_sec)
        raise VideoProviderError(f"Таймаут ожидания задачи {job_id}")

    def download_video(self, job_id: str, dest: Path, status: dict[str, Any] | None = None) -> Path:
        status = status or self.get_video(job_id)
        urls = status.get("unsigned_urls") or []
        url = urls[0] if urls else f"{self.base_url}/videos/{job_id}/content?index=0"
        dest.parent.mkdir(parents=True, exist_ok=True)
        with httpx.Client(timeout=300.0, follow_redirects=True) as client:
            r = client.get(url, headers=self.headers)
        r.raise_for_status()
        dest.write_bytes(r.content)
        return dest
