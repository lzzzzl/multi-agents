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
    # mock | openai | deepseek | ...  (mock 用于无 key 时本地兜底)
    LLM_PROVIDER: str = "mock"
    # 兼容 key,兼容 base_url 指向任意 OpenAI 兼容网关(DeepSeek / 通义 / Ollama 等)
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.deepseek.com"
    LLM_MODEL: str = "deepseek-chat"

    # 兼容旧配置项:OPENAI_API_KEY / DEFAULT_MODEL 作为缺省来源
    OPENAI_API_KEY: str = ""
    DEFAULT_MODEL: str = "gpt-5"

    @property
    def effective_llm_api_key(self) -> str:
        return self.LLM_API_KEY or self.OPENAI_API_KEY

    @property
    def effective_llm_model(self) -> str:
        return self.LLM_MODEL or self.DEFAULT_MODEL

    # 运行限制
    WORKER_CONCURRENCY: int = 2
    RUN_MAX_STEPS: int = 30
    RUN_MAX_COST_USD: float = 2.00
    # Writer 出稿后 Reviewer 不通过时最大重写轮次(不含首次出稿)
    WORKFLOW_MAX_REWRITES: int = 3

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.BACKEND_CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
