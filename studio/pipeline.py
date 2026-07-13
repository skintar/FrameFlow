from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from providers.base import VideoProviderError
from providers.registry import get_provider
import settings as app_settings
from collage import build_character_collage
from config import BUDGET_NO_AUDIO, DEFAULT_DURATION, DEFAULT_MODEL, DEFAULT_SIZE, MAX_CHARACTER_REFERENCES, MAX_PROJECT_CHARACTERS, PROJECTS_DIR, STYLE_PRESETS
from pricing import fetch_video_models, get_model, pick_duration, pick_size

EXTRACT_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "extract_last_frame.py"
CONCAT_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "concat_clips.py"
PYTHON = os.environ.get("PYTHON", str(Path(__file__).resolve().parents[1] / "venv" / "Scripts" / "python.exe"))


def load_api_key(provider_id: str | None = None) -> str | None:
    return app_settings.get_api_key(provider_id)


@dataclass
class ClipSpec:
    index: int
    prompt: str = ""
    reference_paths: list[str] = field(default_factory=list)


@dataclass
class ProjectSpec:
    project_id: str
    title: str
    style: str
    model: str
    size: str
    clip_count: int
    clip_seconds: float
    target_total_seconds: float
    provider: str = "aitunnel"
    global_characters: list[str] = field(default_factory=list)
    clips: list[ClipSpec] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "title": self.title,
            "style": self.style,
            "model": self.model,
            "size": self.size,
            "clip_count": self.clip_count,
            "clip_seconds": self.clip_seconds,
            "target_total_seconds": self.target_total_seconds,
            "provider": self.provider,
            "global_characters": self.global_characters,
            "clips": [
                {"index": c.index, "prompt": c.prompt, "reference_paths": c.reference_paths}
                for c in self.clips
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectSpec:
        clips = [
            ClipSpec(
                index=c["index"],
                prompt=c.get("prompt", ""),
                reference_paths=c.get("reference_paths", []),
            )
            for c in data.get("clips", [])
        ]
        return cls(
            project_id=data["project_id"],
            title=data.get("title", "Untitled"),
            style=data.get("style", "anime"),
            model=data.get("model", DEFAULT_MODEL),
            size=data.get("size", DEFAULT_SIZE),
            clip_count=data["clip_count"],
            clip_seconds=data["clip_seconds"],
            target_total_seconds=data.get("target_total_seconds", 0),
            provider=data.get("provider", app_settings.get_active_provider_id()),
            global_characters=data.get("global_characters", []),
            clips=clips,
        )


@dataclass
class ClipStatus:
    index: int
    state: str = "pending"
    message: str = ""
    video_path: str | None = None
    chain_frame_path: str | None = None
    cost_rub: float | None = None
    remote_job_id: str | None = None


@dataclass
class JobState:
    job_id: str
    project_id: str
    status: str = "queued"
    current_clip: int = 0
    clips: list[ClipStatus] = field(default_factory=list)
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    total_cost_rub: float = 0.0
    final_video_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "project_id": self.project_id,
            "status": self.status,
            "current_clip": self.current_clip,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_cost_rub": round(self.total_cost_rub, 2),
            "final_video_path": self.final_video_path,
            "clips": [
                {
                    "index": c.index,
                    "state": c.state,
                    "message": c.message,
                    "video_path": c.video_path,
                    "chain_frame_path": c.chain_frame_path,
                    "cost_rub": c.cost_rub,
                }
                for c in self.clips
            ],
        }


class ProjectStore:
    def __init__(self, root: Path = PROJECTS_DIR) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def project_dir(self, project_id: str) -> Path:
        return self.root / project_id

    def rel_path(self, project_id: str, path: Path) -> str:
        try:
            return path.relative_to(self.project_dir(project_id)).as_posix()
        except ValueError:
            return str(path)

    def resolve_path(self, project_id: str, ref: str) -> Path:
        p = Path(ref)
        if p.is_absolute():
            return p
        return self.project_dir(project_id) / ref

    def characters_dir(self, project_id: str) -> Path:
        d = self.project_dir(project_id) / "characters"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save_spec(self, spec: ProjectSpec) -> None:
        pdir = self.project_dir(spec.project_id)
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "project.json").write_text(
            json.dumps(spec.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_spec(self, project_id: str) -> ProjectSpec:
        path = self.project_dir(project_id) / "project.json"
        if not path.exists():
            raise FileNotFoundError(project_id)
        return ProjectSpec.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list_projects(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for path in sorted(self.root.glob("*/project.json"), reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                pid = data["project_id"]
                videos = list((self.root / pid / "videos").glob("video_*.mp4"))
                items.append(
                    {
                        "project_id": pid,
                        "title": data.get("title", pid),
                        "model": data.get("model"),
                        "clip_count": data.get("clip_count", 0),
                        "clips_done": len(videos),
                        "updated_at": path.stat().st_mtime,
                    }
                )
            except Exception:
                continue
        return items[:20]

    def refs_dir(self, project_id: str, clip_index: int) -> Path:
        d = self.project_dir(project_id) / "refs" / f"clip_{clip_index:03d}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def videos_dir(self, project_id: str) -> Path:
        d = self.project_dir(project_id) / "videos"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def existing_clip_videos(self, project_id: str, clip_count: int) -> dict[int, Path]:
        videos_dir = self.videos_dir(project_id)
        found: dict[int, Path] = {}
        for i in range(1, clip_count + 1):
            path = videos_dir / f"video_{i:03d}.mp4"
            if path.exists() and path.stat().st_size > 1024:
                found[i] = path
        return found

    def chains_dir(self, project_id: str) -> Path:
        d = self.project_dir(project_id) / "chains"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def apply_global_to_all_clips(self, project_id: str) -> ProjectSpec:
        spec = self.load_spec(project_id)
        for clip in spec.clips:
            for ref in spec.global_characters:
                if ref not in clip.reference_paths:
                    clip.reference_paths.append(ref)
        self.save_spec(spec)
        return spec


class GenerationPipeline:
    def __init__(self) -> None:
        self.store = ProjectStore()
        self.jobs: dict[str, JobState] = {}
        self._lock = threading.Lock()
        self._cancel_flags: set[str] = set()

    def create_project(self, **kwargs: Any) -> ProjectSpec:
        project_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        clip_count = kwargs["clip_count"]
        clips = [ClipSpec(index=i + 1) for i in range(clip_count)]
        spec = ProjectSpec(project_id=project_id, clips=clips, **kwargs)
        self.store.save_spec(spec)
        return spec

    def update_clips(self, project_id: str, clips: list[dict[str, Any]]) -> ProjectSpec:
        spec = self.store.load_spec(project_id)
        by_index = {c["index"]: c for c in clips}
        for clip in spec.clips:
            if clip.index in by_index:
                data = by_index[clip.index]
                clip.prompt = data.get("prompt", clip.prompt)
                clip.reference_paths = data.get("reference_paths", clip.reference_paths)
        self.store.save_spec(spec)
        return spec

    def active_job_for_project(self, project_id: str) -> JobState | None:
        for job in self.jobs.values():
            if job.project_id == project_id and job.status in {"queued", "running"}:
                return job
        return None

    def start_job(self, project_id: str) -> str:
        existing = self.active_job_for_project(project_id)
        if existing:
            return existing.job_id
        spec = self.store.load_spec(project_id)
        job_id = uuid.uuid4().hex
        job = JobState(
            job_id=job_id,
            project_id=project_id,
            clips=[ClipStatus(index=c.index) for c in spec.clips],
        )
        with self._lock:
            self.jobs[job_id] = job
        threading.Thread(target=self._run_job, args=(job_id,), daemon=True).start()
        return job_id

    def cancel_job(self, job_id: str) -> None:
        self._cancel_flags.add(job_id)

    def get_job(self, job_id: str) -> JobState | None:
        return self.jobs.get(job_id)

    def clips_already_done(self, project_id: str) -> int:
        spec = self.store.load_spec(project_id)
        return len(self.store.existing_clip_videos(project_id, spec.clip_count))

    def _prepare_chain_frame(
        self,
        project_id: str,
        last_index: int,
        videos_dir: Path,
        chains_dir: Path,
    ) -> Path:
        chain_path = chains_dir / f"clip_{last_index:03d}_last.png"
        if chain_path.exists() and chain_path.stat().st_size > 100:
            return chain_path
        last_video = videos_dir / f"video_{last_index:03d}.mp4"
        self._extract_last_frame(last_video, chain_path)
        return chain_path

    def _compose_prompt(self, spec: ProjectSpec, clip: ClipSpec) -> str:
        preset = STYLE_PRESETS.get(spec.style, STYLE_PRESETS["anime"])
        return f"{clip.prompt.strip()}, {preset['positive']}"

    def _collect_references(
        self,
        spec: ProjectSpec,
        clip_spec: ClipSpec,
        model_info: dict[str, Any],
    ) -> list[Path] | None:
        if not model_info.get("supports_reference_images"):
            return None
        ordered: list[Path] = []
        seen: set[str] = set()
        # Сначала фото клипа, потом общие (без дублей)
        for ref in list(clip_spec.reference_paths) + list(spec.global_characters):
            path = self.store.resolve_path(spec.project_id, ref)
            key = str(path.resolve()) if path.exists() else ref
            if key in seen or not path.exists():
                continue
            seen.add(key)
            ordered.append(path)
        if not ordered:
            return None
        if len(ordered) <= MAX_CHARACTER_REFERENCES:
            return ordered
        collage_path = self.store.characters_dir(spec.project_id) / "_collage_for_api.jpg"
        build_character_collage(ordered, collage_path)
        return [collage_path]

    def _extract_last_frame(self, video_path: Path, output_path: Path) -> None:
        subprocess.run(
            [PYTHON, str(EXTRACT_SCRIPT), str(video_path), "-o", str(output_path)],
            check=True,
            capture_output=True,
        )

    def _concat_videos(self, video_paths: list[Path], output: Path) -> None:
        if len(video_paths) < 2:
            if video_paths:
                shutil.copy2(video_paths[0], output)
            return
        subprocess.run(
            [PYTHON, str(CONCAT_SCRIPT), *[str(p) for p in video_paths], "-o", str(output)],
            check=True,
            capture_output=True,
        )

    def _run_job(self, job_id: str) -> None:
        job = self.jobs[job_id]
        spec = self.store.load_spec(job.project_id)
        provider_id = spec.provider or app_settings.get_active_provider_id()
        try:
            client = get_provider(provider_id)
        except RuntimeError as exc:
            job.status = "error"
            job.error = str(exc)
            job.finished_at = datetime.now(timezone.utc).isoformat()
            return

        job.status = "running"
        job.started_at = datetime.now(timezone.utc).isoformat()

        import asyncio

        models = asyncio.run(fetch_video_models(provider_id))
        model_info = get_model(models, spec.model)
        duration = pick_duration(model_info, spec.clip_seconds)
        size = pick_size(model_info, spec.size)
        can_chain = bool(model_info.get("supported_frame_images"))

        chain_frame: Path | None = None
        videos_dir = self.store.videos_dir(spec.project_id)
        chains_dir = self.store.chains_dir(spec.project_id)
        existing = self.store.existing_clip_videos(spec.project_id, spec.clip_count)
        rendered: list[Path] = []

        for i, clip_spec in enumerate(spec.clips):
            if clip_spec.index in existing:
                path = existing[clip_spec.index]
                job.clips[i].state = "done"
                job.clips[i].message = "Уже готово (продолжение)"
                job.clips[i].video_path = str(path)
                rendered.append(path)

        if can_chain and existing:
            last_index = max(existing)
            try:
                chain_frame = self._prepare_chain_frame(
                    spec.project_id, last_index, videos_dir, chains_dir
                )
            except Exception:
                chain_frame = None

        for i, clip_spec in enumerate(spec.clips):
            if clip_spec.index in existing:
                continue

            if job_id in self._cancel_flags:
                job.status = "cancelled"
                job.finished_at = datetime.now(timezone.utc).isoformat()
                return

            clip_status = job.clips[i]
            job.current_clip = clip_spec.index
            clip_status.state = "generating"
            clip_status.message = "Отправка в AITunnel..."

            if not clip_spec.prompt.strip():
                clip_status.state = "error"
                job.status = "error"
                job.error = f"Клип #{clip_spec.index}: нет промпта"
                job.finished_at = datetime.now(timezone.utc).isoformat()
                return

            prompt = self._compose_prompt(spec, clip_spec)
            first_frame = chain_frame if (chain_frame and can_chain) else None
            if clip_spec.index > 1 and not can_chain:
                clip_status.message = "Модель без цепочки — каждый клип с нуля"

            refs_for_api = self._collect_references(spec, clip_spec, model_info)
            if first_frame:
                # Цепочка кадров и референсы персонажей — взаимоисключающие
                refs_for_api = None

            try:
                submitted = client.create_video(
                    model=spec.model,
                    prompt=prompt,
                    duration=duration,
                    size=size,
                    first_frame=first_frame,
                    reference_images=refs_for_api,
                    generate_audio=False if BUDGET_NO_AUDIO else None,
                )
                remote_id = submitted["id"]
                clip_status.remote_job_id = remote_id
                started = time.time()

                def on_tick(status: dict[str, Any], cs=clip_status, st=started) -> None:
                    elapsed = int(time.time() - st)
                    m, s = divmod(elapsed, 60)
                    state = status.get("status", "...")
                    cs.message = f"{state} — {m}:{s:02d}"

                result = client.wait_for_video(remote_id, on_tick=on_tick)
                dest_video = videos_dir / f"video_{clip_spec.index:03d}.mp4"
                client.download_video(remote_id, dest_video, status=result)
                clip_status.video_path = str(dest_video)
                rendered.append(dest_video)

                cost = float((result.get("usage") or {}).get("cost_rub") or 0)
                clip_status.cost_rub = cost
                job.total_cost_rub += cost

                if can_chain:
                    chain_path = chains_dir / f"clip_{clip_spec.index:03d}_last.png"
                    self._extract_last_frame(dest_video, chain_path)
                    clip_status.chain_frame_path = str(chain_path)
                    chain_frame = chain_path

                clip_status.state = "done"
                clip_status.message = f"Готово — {cost:.2f} ₽"
            except Exception as exc:
                clip_status.state = "error"
                clip_status.message = str(exc)
                job.status = "error"
                job.error = f"Клип #{clip_spec.index}: {exc}"
                job.finished_at = datetime.now(timezone.utc).isoformat()
                return

        all_videos = [
            videos_dir / f"video_{c.index:03d}.mp4"
            for c in spec.clips
            if (videos_dir / f"video_{c.index:03d}.mp4").exists()
        ]
        if len(all_videos) >= 1:
            final = videos_dir / "episode_full.mp4"
            try:
                self._concat_videos(all_videos, final)
                job.final_video_path = str(final)
            except Exception:
                job.final_video_path = str(all_videos[0])

        job.status = "done"
        job.finished_at = datetime.now(timezone.utc).isoformat()
