from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "BidExpert API"
    app_env: str = "dev"
    database_url: str = "sqlite+pysqlite:///./bidexpert.db"
    min_matrix_coverage: float = 0.9

    model_config = SettingsConfigDict(env_prefix="BIDEXPERT_", extra="ignore")


settings = Settings()
