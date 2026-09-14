"""Runtime settings, read once from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE lines from a .env file into the environment without overriding it.

    Looks in the current directory, then the repo root. No dependency; quotes are stripped.
    The file is git-ignored and is how the API key reaches local runs. Never log its contents.
    """
    candidates = [path] if path else [Path(".env"), Path(__file__).resolve().parents[3] / ".env"]
    for candidate in candidates:
        if candidate and candidate.is_file():
            for line in candidate.read_text("utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("'\""))
            return


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    model: str
    dry_run: bool
    fixture: Path | None

    # Sector benchmark subtracted from every realized move (see CLAUDE.md, confidence score).
    benchmark_ticker: str = "XLE"
    # Moves smaller than this, in percent, resolve as "flat" and count as a miss.
    flat_threshold_pct: float = 0.5
    # Predictions resting only on Tier 3 sources are capped at this confidence.
    tier3_confidence_cap: float = 0.6
    # Minimum resolved predictions per (category, horizon) before a bucket counts as calibrated.
    min_resolved_for_calibration: int = 50
    # Hard ceiling on events sent to the LLM per run: three runs a day, so 24 events/day.
    # Measured 2026-09-14: about USD 0.055 per event on the Batch API, so roughly USD 1.30/day
    # and USD 40/month at this cap. Raise only with the owner's sign-off.
    max_events_per_run: int = 8

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv()
        fixture = os.getenv("FIBR0_FIXTURE")
        return cls(
            database_url=os.getenv("DATABASE_URL"),
            model=os.getenv("FIBR0_MODEL", "claude-opus-5"),
            dry_run=_bool(os.getenv("FIBR0_DRY_RUN")),
            fixture=Path(fixture) if fixture else None,
        )

    def require_database(self) -> str:
        if not self.database_url:
            raise SystemExit(
                "DATABASE_URL is not set. Copy .env.example to .env or set the secret."
            )
        return self.database_url
