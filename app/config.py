"""Application settings and RAN diagnostic policy.

Threshold ownership is explicit on purpose: 3GPP defines how network
measurements are produced and reported (TS 32.425 for E-UTRAN, TS 28.552 for
5G, TS 36.214 for physical-layer measurements). It does not dictate pass/fail
limits. Those are operator or vendor policy, so they live here as configurable
values with documented defaults instead of being hardcoded in the rules.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ENGINE_VERSION = "0.2.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    name: str = "hacom-ai-telco-engine"
    version: str = ENGINE_VERSION
    environment: str = "local"
    log_level: str = "INFO"
    cors_origins: list[str] = ["*"]


class Thresholds(BaseSettings):
    """Operator-tunable RAN policy used by the deterministic rule engine."""

    model_config = SettingsConfigDict(
        env_prefix="RAN_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    congestion_prb_pct: float = 80.0
    severe_congestion_prb_pct: float = 90.0
    congestion_efficiency_pct: float = 60.0
    severe_congestion_efficiency_pct: float = 40.0
    capacity_watch_prb_pct: float = 70.0

    weak_rsrp_dbm: float = -110.0
    good_rsrp_dbm: float = -100.0
    interference_sinr_db: float = 5.0
    coverage_sinr_db: float = 0.0

    min_spectral_efficiency_bps_hz: float = 1.0

    max_drop_call_rate_pct: float = 1.0
    critical_drop_call_rate_pct: float = 2.0


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_thresholds() -> Thresholds:
    return Thresholds()


class LlmSettings(BaseSettings):
    """Agent provider configuration.

    Defaults to the deterministic mock so the service runs with no credentials.
    Set ``LLM_PROVIDER=openai`` and ``LLM_API_KEY`` to use a real model; the base
    URL means any OpenAI-compatible endpoint works, including a local runtime.
    """

    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    provider: Literal["mock", "openai"] = "mock"
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    temperature: float = 0.2
    max_steps: int = 4


@lru_cache
def get_llm_settings() -> LlmSettings:
    return LlmSettings()
