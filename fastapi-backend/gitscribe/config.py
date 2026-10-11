"""Environment-driven configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# One .env at the repo root, shared with the frontend.
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def _bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    llm_base_url: str
    llm_model_fast: str
    llm_model_strong: str
    llm_think_strong: bool
    num_ctx: int
    max_diff_chars: int
    max_concurrency: int
    db_path: str
    cors_origins: tuple[str, ...]
    repos_dir: str
    github_token: str | None

    @property
    def max_prompt_chars(self) -> int:
        """Rough character budget for a prompt, leaving room for the response.

        Assumes ~3 chars/token (conservative for code) and reserves a quarter
        of the context window for output.
        """
        return int(self.num_ctx * 3 * 0.75)


@lru_cache
def get_settings() -> Settings:
    load_dotenv(ENV_FILE)
    env = os.environ.get
    return Settings(
        llm_provider=env("LLM_PROVIDER", "ollama"),
        llm_base_url=env("LLM_BASE_URL", "http://localhost:11434"),
        llm_model_fast=env("LLM_MODEL_FAST", "qwen3.5:9b"),
        llm_model_strong=env("LLM_MODEL_STRONG", "qwen3.5:9b"),
        llm_think_strong=_bool(env("LLM_THINK_STRONG", "false")),
        num_ctx=int(env("NUM_CTX", "16384")),
        max_diff_chars=int(env("MAX_DIFF_CHARS", "20000")),
        max_concurrency=int(env("MAX_CONCURRENCY", "2")),
        db_path=env("DB_PATH", "gitscribe.db"),
        cors_origins=tuple(
            o.strip() for o in env("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()
        ),
        repos_dir=env("REPOS_DIR", "repos"),
        github_token=env("GITHUB_TOKEN") or None,
    )
