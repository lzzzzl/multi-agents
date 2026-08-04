"""应用配置。从环境变量读取,默认值见 .env.example。"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_ENV: str = "local"

    # 数据库与缓存
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/multi_agents"
    REDIS_URL: str = "redis://localhost:6379/0"

    # 跨域
    BACKEND_CORS_ORIGINS: str = "http://localhost:3000"

    # 模型供应商
    LLM_PROVIDER: str = "openai"
    OPENAI_API_KEY: str = ""
    DEFAULT_MODEL: str = "gpt-5"

    # 运行限制
    WORKER_CONCURRENCY: int = 2
    RUN_MAX_STEPS: int = 30
    RUN_MAX_COST_USD: float = 2.00

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.BACKEND_CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
