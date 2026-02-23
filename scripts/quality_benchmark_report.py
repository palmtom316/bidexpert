from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from app.extract.tender_parser import _parse_with_regex
from app.services.global_facts import detect_global_fact_conflicts, extract_global_facts_from_text


def load_cases(fixture_dir: Path) -> list[dict]:
    cases: list[dict] = []
    for path in sorted(fixture_dir.glob("case_*.json")):
        cases.append(json.loads(path.read_text(encoding="utf-8")))
    return cases


def evaluate_case(case: dict) -> dict:
    requirements = _parse_with_regex(case["tender_text"])

    disqual_expected = list(case.get("expected_disqualify_phrases", []))
    disqual_hit = [
        phrase
        for phrase in disqual_expected
        if any(
            phrase in item.original_text and bool(item.format_constraints.get("disqualify_rule"))
            for item in requirements
        )
    ]

    scoring_expected = list(case.get("expected_scoring_phrases", []))
    scoring_hit = [
        phrase
        for phrase in scoring_expected
        if any(
            phrase in item.original_text
            and (
                item.score_weight is not None
                or str(item.format_constraints.get("scoring_rule_type") or "").strip() in {"bonus", "penalty"}
            )
            for item in requirements
        )
    ]

    base_facts = extract_global_facts_from_text(case["base_facts_text"])
    candidate_facts = extract_global_facts_from_text(case["candidate_facts_text"])
    conflicts = detect_global_fact_conflicts(base_facts, candidate_facts)

    return {
        "case_id": case.get("case_id", "unknown"),
        "disqualify_expected": len(disqual_expected),
        "disqualify_hit": len(disqual_hit),
        "scoring_expected": len(scoring_expected),
        "scoring_hit": len(scoring_hit),
        "key_param_conflicts": conflicts,
        "disqualify_coverage": len(disqual_hit) / max(len(disqual_expected), 1),
        "scoring_response": len(scoring_hit) / max(len(scoring_expected), 1),
        "key_param_consistency": 1.0 if not conflicts else 0.0,
    }


def summarize(results: list[dict]) -> dict:
    total = len(results)
    if total == 0:
        return {
            "total_cases": 0,
            "disqualify_coverage_rate": 0.0,
            "scoring_response_rate": 0.0,
            "key_param_consistency_rate": 0.0,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "cases": [],
        }

    disqual_rate = sum(item["disqualify_coverage"] for item in results) / total
    scoring_rate = sum(item["scoring_response"] for item in results) / total
    consistency_rate = sum(item["key_param_consistency"] for item in results) / total
    return {
        "total_cases": total,
        "disqualify_coverage_rate": round(disqual_rate, 4),
        "scoring_response_rate": round(scoring_rate, 4),
        "key_param_consistency_rate": round(consistency_rate, 4),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "cases": results,
    }


def to_markdown(summary: dict) -> str:
    lines = [
        "# 投标质量基准测试报告",
        "",
        f"- 生成时间: {summary['generated_at']}",
        f"- 样本数量: {summary['total_cases']}",
        f"- 废标条款覆盖率: {summary['disqualify_coverage_rate']:.2%}",
        f"- 评分项响应率: {summary['scoring_response_rate']:.2%}",
        f"- 关键参数一致性: {summary['key_param_consistency_rate']:.2%}",
        "",
        "| Case | 废标覆盖 | 评分响应 | 参数一致性 | 冲突字段 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in summary["cases"]:
        conflicts = ", ".join(item.get("key_param_conflicts") or []) or "-"
        lines.append(
            f"| {item['case_id']} | {item['disqualify_coverage']:.2%} | {item['scoring_response']:.2%} | {item['key_param_consistency']:.2%} | {conflicts} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate benchmark quality report")
    parser.add_argument(
        "--fixtures",
        default="tests/benchmark/fixtures",
        help="benchmark fixture directory",
    )
    parser.add_argument(
        "--output",
        default="docs/reports/quality-benchmark-report.md",
        help="markdown output path",
    )
    parser.add_argument(
        "--json-output",
        default="docs/reports/quality-benchmark-report.json",
        help="json output path",
    )
    args = parser.parse_args()

    fixture_dir = Path(args.fixtures)
    cases = load_cases(fixture_dir)
    results = [evaluate_case(case) for case in cases]
    summary = summarize(results)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(to_markdown(summary), encoding="utf-8")

    json_path = Path(args.json_output)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"wrote markdown report to {output_path}")
    print(f"wrote json report to {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
