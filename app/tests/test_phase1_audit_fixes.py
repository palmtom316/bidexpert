from __future__ import annotations

from types import SimpleNamespace

from app.extract import tender_parser as parser
from app.services.byok import profiles
from app.worker import tasks


def test_tender_parser_uses_llm_candidate_chain_before_regex(monkeypatch) -> None:
    calls: list[str] = []

    def fake_chain(*, project_id, task_type):  # noqa: ANN001
        assert project_id is None
        assert task_type == "EXTRACT"
        return [
            SimpleNamespace(model="gemini-3-pro"),
            SimpleNamespace(model="gpt-5"),
        ]

    def fake_run_langextract(*, text: str, model_id: str):
        calls.append(model_id)
        assert "格式" not in text
        if model_id == "gemini-3-pro":
            raise RuntimeError("provider timeout")
        return [
            {
                "extraction_text": "投标人须具备特级资质。",
                "attributes": {
                    "page_no": 2,
                    "section_anchor": "第二章 资格条件",
                    "is_must": True,
                },
            }
        ]

    monkeypatch.setattr(parser, "resolve_profile_chain_for_task", fake_chain, raising=False)
    monkeypatch.setattr(parser, "_run_langextract", fake_run_langextract, raising=False)

    result = parser.parse_tender_requirements("这段文本依赖LLM抽取，不依赖正则关键词")

    assert calls == ["gemini-3-pro", "gpt-5"]
    assert result.status == "OK"
    assert len(result.requirements) == 1
    assert result.requirements[0].original_text == "投标人须具备特级资质。"
    assert result.requirements[0].page_no == 2
    assert result.requirements[0].section_anchor == "第二章 资格条件"


def test_section_render_stage_generates_docx_artifact(monkeypatch) -> None:
    called: dict[str, object] = {}

    def fake_render_word_structured(*, output_path, content, placeholders, template_path, style_config, export_pdf):
        called["output_path"] = output_path
        called["content"] = content
        called["placeholders"] = placeholders
        called["template_path"] = template_path
        called["style_config"] = style_config
        called["export_pdf"] = export_pdf
        return ("/tmp/generated/section-S-001.docx", None)

    monkeypatch.setattr(tasks, "render_word_structured", fake_render_word_structured, raising=False)
    monkeypatch.setattr(tasks.section_render_stage_task, "update_state", lambda *args, **kwargs: None)

    context = {
        "project_id": "p-001",
        "section_key": "S-001",
        "stages": {
            "generate": {
                "status": "SUPPORTED",
                "generated_text": "这是基于证据的章节内容。",
            }
        },
    }

    result = tasks.section_render_stage_task.run(context)

    assert called["export_pdf"] is False
    assert str(called["output_path"]).endswith(".docx")
    assert result["status"] == "SUPPORTED"
    assert result["stages"]["render"]["status"] == "SUCCEEDED"
    assert result["stages"]["render"]["render_ready"] is True
    assert result["stages"]["render"]["output_path"] == "/tmp/generated/section-S-001.docx"


def test_default_embed_profile_reads_global_openai_credentials(monkeypatch) -> None:
    monkeypatch.setenv("BIDEXPERT_OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BIDEXPERT_OPENAI_BASE_URL", "https://api.openai.com/v1")

    from app.core.config import Settings

    monkeypatch.setattr(profiles, "settings", Settings())

    chain = profiles.resolve_profile_chain_for_task(project_id=None, task_type="EMBED")

    assert chain
    assert chain[0].provider == "openai"
    assert chain[0].model == "text-embedding-3-large"
    assert chain[0].api_key == "sk-test"
    assert chain[0].base_url == "https://api.openai.com/v1"
