from __future__ import annotations

from pathlib import Path


def test_ci_workflow_includes_required_quality_gates() -> None:
    workflow = Path('.github/workflows/ci.yml')
    assert workflow.exists(), 'expected GitHub Actions workflow at .github/workflows/ci.yml'

    text = workflow.read_text(encoding='utf-8')
    assert 'pull_request' in text
    assert 'ruff check app tests' in text
    assert 'pytest --cov=app' in text
    assert '--cov-fail-under=60' in text
    assert 'alembic upgrade head' in text
    assert 'alembic downgrade -1' in text
    assert 'docker compose config --quiet' in text
    assert 'pip-audit' in text
    assert 'docker build' in text
