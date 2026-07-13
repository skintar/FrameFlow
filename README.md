# FrameFlow

**FrameFlow** — локальная студия для создания длинных видео из цепочки AI-клипов.  
Склейка кадров, персонажи, автосохранение промптов.

![FrameFlow](https://img.shields.io/badge/version-1.0-blue) ![Python](https://img.shields.io/badge/python-3.10+-green)

## Запуск за 1 клик (Windows)

1. Скачайте или клонируйте репозиторий
2. **Дважды кликните `FrameFlow.bat`**
3. Откроется браузер → **⚙ Настройки** → вставьте API-ключ
4. Создайте проект → напишите промпты → **Начать генерацию**

> Нужны: **Python 3.10+** и **ffmpeg** в PATH ([скачать ffmpeg](https://ffmpeg.org/download.html))

## Поддерживаемые API

| Провайдер | Описание |
|-----------|----------|
| **AITunnel** | Рекомендуется. Оплата в рублях, много моделей. [aitunnel.ru](https://aitunnel.ru) |
| **Свой API** | Любой OpenAI-совместимый Video API (`POST /videos`, `GET /videos/{id}`) |

Настройка через интерфейс (**Настройки**) или файл `.env`:

```env
FRAMEFLOW_PROVIDER=aitunnel
AITUNNEL_API_KEY=sk-...

# Свой API:
# FRAMEFLOW_PROVIDER=custom
# CUSTOM_API_KEY=sk-...
# CUSTOM_BASE_URL=https://api.example.com/v1
# CUSTOM_MODELS_URL=https://api.example.com/v1/models
```

## Как это работает

```
Клип #1  →  видео  →  последний кадр  →  Клип #2  →  ...  →  episode_full.mp4
   ↑                        ↓
 персонажи              цепочка кадров
 (референсы)
```

- **Цепочка кадров** — каждый следующий клип продолжает предыдущий
- **Персонажи** — фото героев на клипе #1 (3+ фото склеиваются в коллаж)
- **Автосохранение** — промпты пишутся на диск при вводе
- **Продолжение** — при сбое генерация стартует с последнего готового клипа

## Ручной запуск

```bash
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
cd studio
python -m uvicorn app:app --host 127.0.0.1 --port 8765
```

Откройте http://127.0.0.1:8765

## Структура проекта

```
FrameFlow/
├── FrameFlow.bat          ← запуск одним кликом
├── .env.example
├── requirements.txt
├── scripts/               ← ffmpeg-утилиты
└── studio/
    ├── app.py             ← API сервер
    ├── pipeline.py        ← генерация и проекты
    ├── providers/         ← AITunnel + свой API
    └── static/            ← интерфейс
```

Проекты сохраняются в `studio/projects/` (не коммитятся в git).

## Советы

- Для длинных роликов используйте модели с **цепочкой кадров** (Seedance, Wan)
- Указывайте в промпте клипа #1, кто где на коллаже персонажей
- При 88 клипах — не закрывайте `FrameFlow.bat`; при сбое просто нажмите «Начать генерацию» снова

## Лицензия

MIT
