from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    davinci_mode: Literal["replay", "live"] = "replay"
    davinci_data_dir: Path = Path("runtime")
    mongodb_uri: str = ""
    mongodb_database: str = "da_vinci"
    openai_api_key: str = ""
    openai_model: str = "gpt-6-astra"
    davinci_sandbox_image: str = "da-vinci-cad:local"
    davinci_run_budget_usd: float = 10
    davinci_daily_budget_usd: float = 50
    davinci_api_token: str = ""
    davinci_web_url: str = "http://127.0.0.1:3000"
    davinci_use_atlas_triggers: bool = False

    @property
    def root(self) -> Path:
        self.davinci_data_dir.mkdir(parents=True, exist_ok=True)
        return self.davinci_data_dir.resolve()
