from __future__ import annotations

from app.extract import tender_parser



def test_regex_parser_covers_disqualify_phrase_matrix() -> None:
    phrases = [
        "废标",
        "作废标处理",
        "无效标",
        "无效投标",
        "不予通过资格审查",
        "资格审查不通过",
        "资格否决",
        "取消投标资格",
        "否决投标",
        "不予受理",
    ]
    text = "。".join(f"投标文件出现情形时{phrase}" for phrase in phrases)

    requirements = tender_parser._parse_with_regex(text)  # noqa: SLF001

    detected = {
        phrase
        for phrase in phrases
        if any(
            phrase in item.original_text and bool(item.format_constraints.get("disqualify_rule"))
            for item in requirements
        )
    }

    assert detected == set(phrases)
