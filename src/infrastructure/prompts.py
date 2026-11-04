"""Loads LLM prompts from assets/prompts/<name>.md so wording can change without touching code."""
from functools import lru_cache

from src import config

PROMPTS_DIR = config.ROOT / "assets" / "prompts"


@lru_cache
def load_prompt(name: str) -> str:
    """Raw text of a prompt file (cached)."""
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


def render_prompt(name: str, **values) -> str:
    """Prompt with `{key}` placeholders replaced. Only the keys given are touched, so JSON braces stay as written."""
    text = load_prompt(name)
    for key, value in values.items():
        text = text.replace("{" + key + "}", str(value))
    return text
