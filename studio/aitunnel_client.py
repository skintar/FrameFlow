"""Обратная совместимость — используйте providers.registry."""
from __future__ import annotations

from providers.base import VideoProviderError as AITunnelError
from providers.openai_video import OpenAIVideoProvider, image_to_data_url
from providers.registry import get_provider

AITunnelClient = OpenAIVideoProvider

__all__ = ["AITunnelClient", "AITunnelError", "image_to_data_url", "get_provider"]
