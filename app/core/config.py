import base64
import binascii

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.llm.model_registry import get_fallback_chain, list_registry_entries
from app.llm.roles import ModelRole


class Settings(BaseSettings):
    app_name: str = "BidExpert API"
    app_env: str = "dev"
    database_url: str = "sqlite+pysqlite:///./bidexpert.db"
    min_matrix_coverage: float = 0.95

    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_pre_ping: bool = True
    db_pool_recycle: int = 1800

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
    qdrant_sparse_bm25_k1: float = 1.2
    qdrant_sparse_bm25_b: float = 0.75
    qdrant_synonyms_enabled: bool = True
    qdrant_synonym_expand_limit: int = 8
    qdrant_rerank_ab_variant: str = "A"
    qdrant_rerank_weight_profiles: dict[str, dict[str, float]] = {
        "A": {"base": 0.55, "lexical": 0.40, "quality": 0.05},
        "B": {"base": 0.45, "lexical": 0.45, "quality": 0.10},
    }
    qdrant_cross_encoder_enabled: bool = False
    qdrant_cross_encoder_model: str = "BAAI/bge-reranker-base"
    qdrant_llm_rerank_enabled: bool = False
    qdrant_llm_rerank_candidate_limit: int = 30
    qdrant_llm_rerank_top_k: int = 12

    llm_http_timeout_seconds: int = 120
    log_level: str = "INFO"
    log_format: str = "json"
    metrics_enabled: bool = True
    metrics_public_enabled: bool = False
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
    ocr_provider: str = "glm-ocr"
    pdf_ocr_textlen_threshold: int = 200
    pdf_ocr_min_non_whitespace_ratio: float = 0.01
    pdf_ocr_confidence_threshold: float = 0.75
    pdf_render_dpi: int = 260
    glm_ocr_api_key: str | None = None
    glm_ocr_base_url: str | None = None
    glm_ocr_model: str = "glm-ocr"
    textin_ocr_api_key: str | None = None
    textin_ocr_base_url: str = "https://api.textin.com/ai/service/v2/recognize/document"
    textin_ocr_model: str | None = None
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
    section_output_tokens_map: dict[str, int] = {
        "default": 4000,
        "施工方案": 12000,
        "施工组织设计": 12000,
        "技术方案": 10000,
        "商务响应": 6000,
        "资审文件": 5000,
        "评标响应": 7000,
    }
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
    secret_temp_key_ttl_seconds: int = 3600
    api_key: str | None = None
    api_key_secondary: str | None = None
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
    langextract_default_model: str = "qwen3.5"
    context_compression_use_llm: bool = True
    context_compression_max_items: int = 6
    context_compression_max_chars: int = 4000
    context_compression_snippet_chars: int = 800
    expert_chunk_min_tokens: int = 800
    expert_chunk_max_tokens: int = 1200
    expert_chunk_overlap_tokens: int = 120
    expert_chunk_min_chars: int = 80
    knowledge_quality_low_score_threshold: float = 70.0
    knowledge_sampling_ratio: float = 0.1
    knowledge_sampling_accuracy_threshold: float = 0.85

    model_config = SettingsConfigDict(
        env_prefix="BIDEXPERT_", 
        extra="ignore",
        env_file=".env"
    )


settings = Settings()


def normalized_app_env() -> str:
    return (settings.app_env or "").strip().lower()


def _validate_model_registry_defaults() -> None:
    entries = list_registry_entries()
    if not entries:
        raise RuntimeError("Model registry must contain at least one model entry")

    registered_keys = {(entry.provider, entry.model_name) for entry in entries}
    registered_model_names = {entry.model_name for entry in entries}

    default_extract_model = (settings.langextract_default_model or "").strip()
    if not default_extract_model:
        raise RuntimeError("BIDEXPERT_LANGEXTRACT_DEFAULT_MODEL must not be empty")
    if default_extract_model not in registered_model_names:
        raise RuntimeError(
            f"BIDEXPERT_LANGEXTRACT_DEFAULT_MODEL={default_extract_model!r} is not registered"
        )

    for role in ModelRole:
        for provider, model in get_fallback_chain(role):
            if (provider, model) not in registered_keys:
                raise RuntimeError(
                    f"Model registry default chain for {role.value} contains unregistered model {provider}:{model}"
                )


def validate_runtime_baseline() -> None:
    normalized = normalized_app_env()
    if normalized in {"production", "prd"}:
        raise RuntimeError("Production baseline requires BIDEXPERT_APP_ENV=prod")
    if normalized not in {"dev", "test", "prod"}:
        raise RuntimeError(
            f"Unsupported BIDEXPERT_APP_ENV={settings.app_env!r}; allowed values: dev, test, prod"
        )
    _validate_model_registry_defaults()
    if normalized == "prod":
        raw_master_key = (settings.master_key_b64 or "").strip()
        if not raw_master_key:
            raise RuntimeError("BIDEXPERT_MASTER_KEY_B64 is required when BIDEXPERT_APP_ENV=prod")
        try:
            decoded = base64.b64decode(raw_master_key, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise RuntimeError("BIDEXPERT_MASTER_KEY_B64 must be valid base64") from exc
        if len(decoded) != 32:
            raise RuntimeError("BIDEXPERT_MASTER_KEY_B64 must decode to 32 bytes")
    if normalized == "prod" and settings.vault_redis_fallback_enabled:
        raise RuntimeError(
            "BIDEXPERT_VAULT_REDIS_FALLBACK_ENABLED must be false when BIDEXPERT_APP_ENV=prod"
        )
    if normalized == "prod" and "localhost" in settings.cors_origins:
        raise RuntimeError("CORS_ORIGINS must not contain localhost in prod")
    if normalized == "prod" and "bidexpert:bidexpert@" in settings.database_url:
        raise RuntimeError("Default database password must not be used in prod")
    if normalized == "prod" and "://:@" not in settings.redis_url and "@" not in settings.redis_url:
        raise RuntimeError("REDIS_URL must include a password in prod")
    if int(settings.secret_temp_key_ttl_seconds) <= 0:
        raise RuntimeError("BIDEXPERT_SECRET_TEMP_KEY_TTL_SECONDS must be greater than 0")
