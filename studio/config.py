from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parent
PROJECTS_DIR = STUDIO_ROOT / "projects"
STATIC_DIR = STUDIO_ROOT / "static"
ENV_FILE = STUDIO_ROOT.parent / ".env"

AITUNNEL_BASE_URL = "https://api.aitunnel.ru/v1"
AITUNNEL_MODELS_URL = "https://api.aitunnel.ru/public/aitunnel/models/videos"

# Бюджетные значения по умолчанию (минимальная цена)
DEFAULT_MODEL = "seedance-1-5-pro"
DEFAULT_SIZE = "480x480"
DEFAULT_DURATION = 4
BUDGET_NO_AUDIO = True
MAX_CHARACTER_REFERENCES = 2  # слотов в одном запросе AITunnel
MAX_PROJECT_CHARACTERS = 8  # сколько фото можно хранить в проекте

MODEL_LABELS = {
    "seedance-1-5-pro": "Seedance 1.5 Pro — самый дешёвый",
    "grok-imagine-video": "Grok Imagine — бюджетный",
    "seedance-2.0-fast": "Seedance 2.0 Fast — быстрее",
    "wan-2.7": "Wan 2.7 — аниме",
    "kling-v3.0-std": "Kling 3.0 Std",
    "wan-2.6": "Wan 2.6",
}

STYLE_PRESETS = {
    "anime": {
        "label": "Аниме",
        "positive": "anime style, cel shading, clean line art, vibrant colors, smooth animation",
        "negative": "photorealistic, 3d render, blurry, low quality, bad anatomy",
    },
    "cinematic": {
        "label": "Кинематограф",
        "positive": "cinematic lighting, film grain, dramatic composition, high production value",
        "negative": "cartoon, anime, low quality, blurry, amateur",
    },
    "watercolor": {
        "label": "Акварель",
        "positive": "watercolor painting style, soft edges, artistic brush strokes, dreamy atmosphere",
        "negative": "photorealistic, sharp digital, low quality, noisy",
    },
    "comic": {
        "label": "Комикс",
        "positive": "comic book style, bold outlines, halftone dots, dynamic poses",
        "negative": "photorealistic, blurry, low quality, muddy colors",
    },
    "pixel": {
        "label": "Пиксель-арт",
        "positive": "pixel art style, retro game aesthetic, crisp pixels, limited palette",
        "negative": "photorealistic, blurry, smooth gradients, anti-aliased",
    },
    "3d": {
        "label": "3D-рендер",
        "positive": "3d render, stylized 3d, smooth shading, octane render quality",
        "negative": "2d, flat, low poly artifacts, blurry",
    },
    "realistic": {
        "label": "Реализм",
        "positive": "photorealistic, natural lighting, detailed textures, high fidelity",
        "negative": "cartoon, anime, painting, low quality, blurry",
    },
}

PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
