"""
Workforce OS — Configuration
Centralized settings from environment variables.
"""

import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Supabase
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_service_role_key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    supabase_anon_key: str = os.getenv("SUPABASE_ANON_KEY", "")
    
    # LLM
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    voyage_api_key: str = os.getenv("VOYAGE_API_KEY", "")
    
    # Models
    primary_model: str = "deepseek-v4-pro"
    secondary_model: str = "claude-sonnet-4-6"
    embedding_model: str = "voyage-3"
    
    # App
    environment: str = os.getenv("ENVIRONMENT", "development")
    debug: bool = os.getenv("DEBUG", "true").lower() == "true"
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    
    # Cache
    redis_url: str = os.getenv("REDIS_URL", "")
    
    # Limits
    max_agents_per_council: int = 5
    max_rounds_group: int = 5
    request_timeout_seconds: int = 60
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
