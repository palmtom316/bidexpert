#!/usr/bin/env python3
"""Quality benchmark report generator.

Runs the benchmark test suite and produces a summary report.
Usage: python scripts/quality_benchmark_report.py
"""
from __future__ import annotations

import json
import subprocess
import sys


def main() -> None:
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "tests/benchmark/test_bid_quality_benchmark.py",
            "app/tests/test_tender_parser_disqualify_coverage.py",
            "app/tests/test_pricing_guard_regression_matrix.py",
            "app/tests/test_generation_pipeline_conflict_and_disqualify.py",
            "--tb=short", "-q", "--no-header",
        ],
        capture_output=True,
        text=True,
    )

    print("=" * 60)
    print("BidExpert Quality Benchmark Report")
    print("=" * 60)
    print()
    print(result.stdout)
    if result.stderr:
        print(result.stderr)

    passed = result.returncode == 0
    print("=" * 60)
    print(f"Overall: {'PASS' if passed else 'FAIL'}")
    print("=" * 60)

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
