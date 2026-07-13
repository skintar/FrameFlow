from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable


class VideoProviderError(RuntimeError):
    pass


class VideoProvider(ABC):
    id: str
    name: str
    description: str

    @abstractmethod
    def check_key(self) -> bool: ...

    @abstractmethod
    async def fetch_models(self, *, force: bool = False) -> dict[str, Any]: ...

    @abstractmethod
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
    ) -> dict[str, Any]: ...

    @abstractmethod
    def get_video(self, job_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def wait_for_video(
        self,
        job_id: str,
        *,
        timeout_sec: int = 1800,
        poll_sec: float = 15.0,
        on_tick: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def download_video(self, job_id: str, dest: Path, status: dict[str, Any] | None = None) -> Path: ...
