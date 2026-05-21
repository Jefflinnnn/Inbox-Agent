from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # Microsoft Graph
    ms_tenant_id: str
    ms_client_id: str
    ms_client_secret: str

    # Notion
    notion_api_key: str
    notion_kanban_db_id: str
    notion_meetings_db_id: str

    # Claude
    anthropic_api_key: str

    # App config
    log_level: str = "INFO"
    max_emails_per_run: int = 50
    days_back_meetings: int = 7

    # Paths
    project_dir: Path = Path(__file__).resolve().parent.parent.parent
    db_path: Path = Path(__file__).resolve().parent.parent.parent / "state.db"
    token_path: Path = Path(__file__).resolve().parent.parent.parent / ".tokens.json"


def load_settings() -> Settings:
    return Settings()
