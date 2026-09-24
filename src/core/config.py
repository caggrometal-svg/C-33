from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    app_name: str
    environment: str
    host: str
    port: int
    agent_max_steps: int
    web_timeout_seconds: float
    memory_file: str


def load_settings() -> Settings:
    return Settings(
        app_name=os.getenv("APP_NAME", "C-33"),
        environment=os.getenv("APP_ENV", "development"),
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        agent_max_steps=int(os.getenv("AGENT_MAX_STEPS", "8")),
        web_timeout_seconds=float(os.getenv("WEB_TIMEOUT_SECONDS", "15")),
        memory_file=os.getenv("MEMORY_FILE", "data/memory.json"),
    )
