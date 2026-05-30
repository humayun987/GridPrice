from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    APP_ENV: str = "production"
    SECRET_KEY: str = "gridprice-super-secret-key-change-in-prod"
    APP_PORT: int = 8000

    # Database
    DATABASE_URL: str = ""

    # Redis
    REDIS_URL: str = ""

    # ML Service
    ML_SERVICE_URL: str = "mock"

    model_config = {
        "env_file": ".env",
        "extra": "ignore"
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()
