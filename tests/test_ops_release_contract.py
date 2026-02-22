from __future__ import annotations

from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_compose_includes_data_backup_service_for_ops_profile() -> None:
    compose = _read("docker-compose.yml")
    assert "data-backup:" in compose
    assert 'profiles: ["ops"]' in compose
    assert "/scripts/data_backup.sh" in compose


def test_backup_readme_covers_data_backup_and_monthly_template() -> None:
    readme = _read("deploy/backup/README.md")
    assert "data-backup" in readme
    assert "monthly-restore-drill-template.md" in readme


def test_alert_rules_cover_429_5xx_and_task_failure_rate() -> None:
    rules = _read("deploy/monitoring/prometheus-alerts.yml")
    assert "bidexpert_http_rate_limit_total" in rules
    assert "bidexpert_http_server_errors_total" in rules
    assert "bidexpert_celery_task_events_total" in rules


def test_release_preflight_script_blocks_runtime_artifacts() -> None:
    script = _read("scripts/release/preflight_runtime_artifacts.sh")
    assert "data/workflow-runs" in script
    assert "backups/" in script
    assert ".db" in script


def test_readme_uses_correct_celery_module_and_mentions_preflight() -> None:
    readme = _read("docs/README.md")
    assert "celery -A app.worker.celery_app.celery_app worker" in readme
    assert "preflight_runtime_artifacts.sh" in readme


def test_compose_api_healthcheck_uses_api_key_header() -> None:
    compose = _read("docker-compose.yml")
    assert "X-API-Key" in compose
    assert "BIDEXPERT_API_KEY" in compose


def test_compose_nginx_supports_non_prod_tls_fallback() -> None:
    compose = _read("docker-compose.yml")
    assert "BIDEXPERT_APP_ENV" in compose
    assert "openssl req -x509" in compose
    assert "Provide deploy/nginx/certs/tls.crt and tls.key in prod" in compose


def test_compose_redis_requires_password() -> None:
    compose = _read("docker-compose.yml")
    assert "requirepass" in compose
    assert "REDIS_PASSWORD" in compose


def test_compose_worker_uses_celery_inspect_healthcheck() -> None:
    compose = _read("docker-compose.yml")
    assert "celery -A app.worker.celery_app.celery_app inspect ping" in compose


def test_compose_services_have_graceful_shutdown() -> None:
    compose = _read("docker-compose.yml")
    assert "stop_grace_period:" in compose


def test_base_migration_supports_bootstrapped_schema_guard() -> None:
    migration = _read("migrations/versions/47ace6ac701b_add_reviewreport_and_scoringreport.py")
    assert "_is_bootstrapped_schema" in migration
    assert "legacy schema already bootstrapped" in migration
