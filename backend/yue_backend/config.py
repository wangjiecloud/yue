from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="YUE_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Field(default=PROJECT_ROOT / "data")

    deepseek_base_url: str = ""
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-v4.1-flash"
    deepseek_workspace: str = ""
    deepseek_timeout_s: float = 120.0

    cosyvoice_model_dir: Path | None = None
    cosyvoice_code_dir: Path | None = None
    cosyvoice_python: Path | None = None
    cosyvoice_reference_audio: Path | None = None
    cosyvoice_reference_text: str = ""
    cosyvoice_device: str = "auto"
    cosyvoice_timeout_s: float = 600.0

    allow_placeholder_tts: bool = False

    def ensure_dirs(self) -> None:
        for name in ("uploads", "jobs", "courses", "media", "reports", "tmp", "assets"):
            (self.data_dir / name).mkdir(parents=True, exist_ok=True)

    @property
    def deepseek_configured(self) -> bool:
        return bool(self.deepseek_base_url and self.deepseek_api_key)

    @property
    def cosyvoice_configured(self) -> bool:
        return bool(
            self.cosyvoice_model_dir
            and Path(self.cosyvoice_model_dir).is_dir()
            and self.cosyvoice_reference_audio
            and Path(self.cosyvoice_reference_audio).is_file()
            and self.cosyvoice_reference_text
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
