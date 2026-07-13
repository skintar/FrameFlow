from __future__ import annotations

from pathlib import Path

from PIL import Image

# Лимит ByteDance / Seedance для референс-изображений
MIN_ASPECT = 0.40
MAX_ASPECT = 2.50


def _pick_grid(count: int) -> tuple[int, int]:
    """Подбирает сетку cols×rows: все фото помещаются, aspect ratio в допустимых пределах."""
    best: tuple[tuple[int, float], int, int] | None = None
    for cols in range(1, count + 2):
        rows = (count + cols - 1) // cols
        aspect = cols / rows
        if aspect < MIN_ASPECT or aspect > MAX_ASPECT:
            continue
        waste = cols * rows - count
        score = (waste, abs(aspect - 1.0))
        if best is None or score < best[0]:
            best = (score, cols, rows)
    if best:
        return best[1], best[2]
    # запасной вариант — квадратная сетка
    side = max(2, int(count**0.5 + 0.999))
    return side, (count + side - 1) // side


def _fit_cell(path: Path, cell_size: int) -> Image.Image:
    im = Image.open(path).convert("RGB")
    im.thumbnail((cell_size, cell_size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (cell_size, cell_size), (28, 28, 36))
    canvas.paste(im, ((cell_size - im.width) // 2, (cell_size - im.height) // 2))
    return canvas


def build_character_collage(paths: list[Path], output: Path, cell_size: int = 480) -> Path:
    """Склеивает фото персонажей в коллаж с допустимым aspect ratio для API."""
    existing = [p for p in paths if p.exists()]
    if not existing:
        raise ValueError("Нет изображений для коллажа")

    output.parent.mkdir(parents=True, exist_ok=True)

    if len(existing) == 1:
        Image.open(existing[0]).convert("RGB").save(output, "JPEG", quality=92)
        return output

    cells = [_fit_cell(p, cell_size) for p in existing]
    cols, rows = _pick_grid(len(cells))
    collage = Image.new("RGB", (cell_size * cols, cell_size * rows), (28, 28, 36))
    for idx, cell in enumerate(cells):
        collage.paste(cell, ((idx % cols) * cell_size, (idx // cols) * cell_size))
    collage.save(output, "JPEG", quality=92)
    return output
