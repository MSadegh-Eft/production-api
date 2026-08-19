"""
Centralized Configuration
Uses pydantic-settings for validated environment variables.
"""

from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from functools import lru_cache

# Load .env into os.environ so LangChain/LangSmith SDK can read tracing config
load_dotenv()

class Settings(BaseSettings):
    
    # LLM Configuration
    openai_api_key: str
    google_api_key: str
    primary_model: str = "gemini-3.5-flash"
    fallback_model: str = "gpt-4o-mini"
    
    # LangSmith
    langchain_tracing_v2: bool = True
    langchain_api_key: str = ""
    langchain_project: str = "production-api"
    
    
    # Application
    app_env: str = "development"
    log_level: str = "INFO"
    rate_limit: str = "20/minute"
    cache_ttl_seconds: int = 300
    max_retries: int = 3

    # Conversation memory
    # Ceiling on how many tokens of chat history get sent to the LLM per
    # request, kept safely under gpt-4o-mini's 128K context window since
    # the fallback model may end up serving the same trimmed history.
    max_context_tokens: int = 100_000
    # Leave blank to keep memory in-process only (wiped whenever the
    # server restarts, e.g. Render free-tier spin-down). Set to a Postgres
    # connection string (e.g. from Neon) to persist it across restarts.
    database_url: str = ""
    
    
    model_config = {"env_file": ".env", "extra": "ignore"}
    
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"
    
@lru_cache
def get_settings() -> Settings:
    """Cached settings instance - loaded once, reused everywhere."""
    return Settings()