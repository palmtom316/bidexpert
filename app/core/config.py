from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "BidExpert API"
    app_env: str = "dev"
    database_url: str = "sqlite+pysqlite:///./bidexpert.db"
    min_matrix_coverage: float = 0.95

    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "expert_chunks_v1"
    qdrant_vector_size: int = 256

    upload_dir: str = "data/uploads"
    enable_ocr_fallback: bool = True
    schema_version: str = "v3.2"
    top_k_default: int = 6
    evidence_expiry_warning_days: int = 30
    project_token_budget_default: int = 500000
    section_max_input_tokens: int = 16000
    section_max_output_tokens: int = 4000
    task_max_retries: int = 2
    task_max_fallbacks: int = 1
    max_parallel_sections: int = 4
    master_key_b64: str | None = None
    review_fallback_provider: str | None = None
    review_fallback_model: str | None = None
    review_fallback_base_url: str | None = None
    review_fallback_api_key: str | None = None
    langextract_default_model: str = "gemini-2.5-flash"

    model_config = SettingsConfigDict(env_prefix="BIDEXPERT_", extra="ignore")


settings = Settings()
