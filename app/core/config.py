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
    qdrant_vector_size: int = 3072
    qdrant_hybrid_candidate_limit: int = 128
    qdrant_rrf_k: int = 60
    qdrant_enable_rerank: bool = True
    qdrant_rerank_candidate_limit: int = 24
    qdrant_hybrid_topk_min: int = 50
    qdrant_hybrid_topk_max: int = 100
    qdrant_prompt_topn_min: int = 10
    qdrant_prompt_topn_max: int = 20
    qdrant_cross_encoder_enabled: bool = False
    qdrant_cross_encoder_model: str = "BAAI/bge-reranker-base"

    llm_http_timeout_seconds: int = 120
    log_level: str = "INFO"
    log_format: str = "json"
    metrics_enabled: bool = True
    auth_mode: str = "api_key"
    jwt_secret: str | None = None
    jwt_public_key_pem: str | None = None
    jwt_allowed_algorithms: str = "RS256,ES256"
    jwt_issuer: str | None = None
    jwt_audience: str | None = None
    max_upload_bytes: int = 50 * 1024 * 1024
    api_rate_limit_enabled: bool = True
    api_rate_limit_requests: int = 300
    api_rate_limit_window_seconds: int = 60

    upload_dir: str = "data/uploads"
    serve_ui_static: bool = True
    expert_library_root: str = "data/tender-expert-lib"
    render_output_dir: str = "data/exports"
    render_template_dir: str = "templates"
    workflow_artifact_dir: str = "data/workflow-runs"
    enable_ocr_fallback: bool = True
    ocr_provider: str = "tesseract"
    pdf_ocr_textlen_threshold: int = 200
    pdf_ocr_min_non_whitespace_ratio: float = 0.01
    pdf_render_dpi: int = 260
    hunyuan_ocr_api_key: str | None = None
    hunyuan_ocr_base_url: str | None = None
    docai_ocr_api_key: str | None = None
    docai_ocr_base_url: str | None = None
    schema_version: str = "v1.0"
    top_k_default: int = 6
    evidence_expiry_warning_days: int = 30
    project_token_budget_default: int = 500000
    section_max_input_tokens: int = 16000
    section_max_output_tokens: int = 4000
    task_max_retries: int = 2
    task_max_fallbacks: int = 1
    max_parallel_sections: int = 4
    task_status_stream_timeout_seconds: int = 300
    semantic_cache_cleanup_interval_seconds: int = 300
    semantic_cache_max_local_entries: int = 4096
    evidence_fuzzy_partial_ratio_threshold: int = 88
    pricing_file: str | None = None
    master_key_b64: str | None = None
    vault_addr: str | None = None
    vault_token: str | None = None
    vault_mount: str = "secret"
    vault_namespace: str | None = None
    vault_redis_fallback_enabled: bool = True
    api_key: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str | None = "https://api.openai.com/v1"
    gemini_api_key: str | None = None
    gemini_base_url: str | None = None
    qwen_api_key: str | None = None
    qwen_base_url: str | None = None
    deepseek_api_key: str | None = None
    deepseek_base_url: str | None = "https://api.deepseek.com/v1"
    voyage_api_key: str | None = None
    voyage_base_url: str | None = "https://api.voyageai.com/v1"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    review_fallback_provider: str | None = None
    review_fallback_model: str | None = None
    review_fallback_base_url: str | None = None
    review_fallback_api_key: str | None = None
    review_ensemble_enabled: bool = False
    review_ensemble_size: int = 3
    rl_routing_enabled: bool = False
    rl_routing_exploration_rate: float = 0.1
    langextract_default_model: str = "gemini-3-pro"
    context_compression_use_llm: bool = True
    context_compression_max_items: int = 6
    context_compression_max_chars: int = 4000
    context_compression_snippet_chars: int = 800
    expert_chunk_min_tokens: int = 800
    expert_chunk_max_tokens: int = 1200
    expert_chunk_overlap_tokens: int = 120

    model_config = SettingsConfigDict(env_prefix="BIDEXPERT_", extra="ignore")


settings = Settings()
