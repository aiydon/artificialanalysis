from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict

BASE_URL = "https://artificialanalysis.ai"

# The changelog shows several evaluation batches per day; two hours keeps the
# dashboard fresh without re-downloading ~25 MB of pages more often than useful.
DEFAULT_INTERVAL = 2 * 60 * 60.0


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    data_dir: Path = Path("data")
    proxy: str | None = None
    timeout: float = 60.0
    retries: int = 3
    interval: float = DEFAULT_INTERVAL
    jitter: float = 0.1

    @property
    def db_path(self) -> Path:
        return self.data_dir / "aa.db"

    @property
    def export_dir(self) -> Path:
        return self.data_dir / "export"


def settings_from_env() -> Settings:
    """Defaults come from AA_* environment variables; CLI flags override them."""
    return Settings(
        data_dir=Path(os.getenv("AA_DATA_DIR", "data")),
        proxy=os.getenv("AA_PROXY") or None,
        timeout=float(os.getenv("AA_TIMEOUT", "60")),
        retries=int(os.getenv("AA_RETRIES", "3")),
        interval=float(os.getenv("AA_INTERVAL", str(DEFAULT_INTERVAL))),
        jitter=float(os.getenv("AA_JITTER", "0.1")),
    )
