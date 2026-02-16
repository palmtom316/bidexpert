from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from app.core.config import settings
from app.services.expert_enterprise_defaults import enterprise_default_files

EXPERT_LIBRARY_STAGE_DIRS: tuple[str, ...] = (
    "00_config",
    "01_raw",
    "02_extracted",
    "03_enriched",
    "04_md",
    "05_chunks",
    "06_index",
    "07_review",
    "99_logs",
)


@dataclass(frozen=True)
class ExpertLibraryLayout:
    root: Path
    stage_dirs: dict[str, Path]


@dataclass(frozen=True)
class ExpertDocWorkspace:
    doc_key: str
    raw_bid_dir: Path
    extracted_dir: Path
    extracted_blocks_dir: Path
    enriched_dir: Path
    chunks_dir: Path


def normalize_doc_key(value: str) -> str:
    normalized = re.sub(r"[^\w\u4e00-\u9fff.-]+", "-", value).strip("-")
    return normalized or "doc-unknown"


def ensure_expert_library_layout(root: str | Path | None = None) -> ExpertLibraryLayout:
    root_dir = Path(root) if root is not None else Path(settings.expert_library_root)
    root_dir.mkdir(parents=True, exist_ok=True)

    stage_dirs: dict[str, Path] = {}
    for stage in EXPERT_LIBRARY_STAGE_DIRS:
        stage_path = root_dir / stage
        stage_path.mkdir(parents=True, exist_ok=True)
        stage_dirs[stage] = stage_path

    (stage_dirs["99_logs"] / "pipeline_runs").mkdir(parents=True, exist_ok=True)
    (stage_dirs["06_index"] / "qdrant").mkdir(parents=True, exist_ok=True)
    return ExpertLibraryLayout(root=root_dir, stage_dirs=stage_dirs)


def sync_enterprise_config_assets(layout: ExpertLibraryLayout) -> None:
    for rel_path, content in enterprise_default_files().items():
        target = layout.root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"{content.rstrip()}\n", encoding="utf-8")


def prepare_doc_workspace(layout: ExpertLibraryLayout, doc_key: str) -> ExpertDocWorkspace:
    normalized_key = normalize_doc_key(doc_key)
    raw_bid_dir = layout.stage_dirs["01_raw"] / normalized_key / "bid"
    extracted_dir = layout.stage_dirs["02_extracted"] / normalized_key
    extracted_blocks_dir = extracted_dir / "blocks"
    enriched_dir = layout.stage_dirs["03_enriched"] / normalized_key
    chunks_dir = layout.stage_dirs["05_chunks"] / normalized_key

    for path in (raw_bid_dir, extracted_dir, extracted_blocks_dir, enriched_dir, chunks_dir):
        path.mkdir(parents=True, exist_ok=True)

    return ExpertDocWorkspace(
        doc_key=normalized_key,
        raw_bid_dir=raw_bid_dir,
        extracted_dir=extracted_dir,
        extracted_blocks_dir=extracted_blocks_dir,
        enriched_dir=enriched_dir,
        chunks_dir=chunks_dir,
    )
