"""AI-powered post generation service (stub).

When wired to a real AI provider, this service will generate social media
captions, hashtag suggestions, and platform-specific variants from a prompt.

For now, it is a no-op placeholder so the API layer can import and call it
without the caller needing to know whether AI is configured.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AiGeneratedPost:
    """Output of the AI post generation service."""

    caption: str = ""
    hashtags: list[str] = field(default_factory=list)
    platform_variants: dict[str, str] = field(default_factory=dict)
    suggested_media_queries: list[str] = field(default_factory=list)


def generate_post(prompt: str, platforms: list[str] | None = None) -> AiGeneratedPost:
    """Generate a social media post from a text prompt (stub).

    Args:
        prompt: The user's content prompt / brief.
        platforms: Optional list of platform keys (e.g. ``["twitter", "linkedin"]``).

    Returns:
        An ``AiGeneratedPost`` with placeholder content.
    """
    return AiGeneratedPost(
        caption=f"[AI stub] {prompt}",
        hashtags=["#brightbean", "#socialmedia"],
        platform_variants={p: f"[{p}] {prompt}" for p in (platforms or [])},
        suggested_media_queries=["nature landscape", "team collaboration"],
    )
