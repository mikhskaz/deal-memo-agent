"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # API keys
    ANTHROPIC_API_KEY: str = ""
    TAVILY_API_KEY: str = ""

    # Model config
    EXTRACTION_MODEL: str = "claude-sonnet-4-5"
    DRAFTING_MODEL: str = "claude-sonnet-4-5"
    MAX_TOKENS_EXTRACTION: int = 4096
    MAX_TOKENS_DRAFT: int = 8192

    # Pipeline config
    CHUNK_SIZE_TOKENS: int = 6000
    CHUNK_OVERLAP_TOKENS: int = 500
    MAX_SEARCH_QUERIES: int = 6
    MAX_SEARCH_RESULTS_PER_QUERY: int = 3

    # App
    PORT: int = 8000
    CORS_ORIGINS: str = "http://localhost:3000"
    LOG_LEVEL: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
