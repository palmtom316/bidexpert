"""Unpack .tender.zip, load manifest, validate package structure."""

from __future__ import annotations

import io
import json
import logging
import zipfile
from pathlib import Path

from app.tender.schemas import TenderManifest

logger = logging.getLogger(__name__)

REQUIRED_FILES = {"manifest.json", "original.pdf", "full.md"}
ALLOWED_DERIVED_NAMES = frozenset({
    "tender_sections.json",
    "compliance_check.json",
    "preliminary_evaluation.json",
    "scoring_model.json",
    "technical_requirements.json",
    "deviation_tables.json",
    "format_signature_constraints.json",
    "key_personnel_constraints.json",
    "fatal_gate_report.json",
    "bid_blueprint.json",
    "import_report.json",
})


class TenderPackageError(Exception):
    """Raised when the .tender.zip is invalid."""


def unpack_zip(zip_bytes: bytes, workspace: Path) -> Path:
    """Extract .tender.zip contents into *workspace* directory.

    Returns the root directory containing the extracted files.
    """
    workspace.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            # Security: reject path traversal entries
            for name in zf.namelist():
                if name.startswith("/") or ".." in name:
                    raise TenderPackageError(f"unsafe zip entry: {name}")

            zf.extractall(workspace)
    except zipfile.BadZipFile as exc:
        raise TenderPackageError("file is not a valid zip archive") from exc

    # Handle nested directory: if zip contains a single root folder, descend
    entries = [e for e in workspace.iterdir() if not e.name.startswith(".")]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return workspace


def load_manifest(root: Path) -> TenderManifest:
    """Load and parse manifest.json from unpacked package root."""
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise TenderPackageError("manifest.json not found in package")

    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise TenderPackageError(f"invalid manifest.json: {exc}") from exc

    try:
        return TenderManifest.model_validate(raw)
    except Exception as exc:
        raise TenderPackageError(f"manifest.json schema validation failed: {exc}") from exc


def validate_tender_package(root: Path, manifest: TenderManifest) -> list[str]:
    """Validate the unpacked package. Returns list of warnings (empty = OK).

    Raises TenderPackageError if required files are missing.
    """
    warnings: list[str] = []

    # Check required files
    for required in REQUIRED_FILES:
        if not (root / required).exists():
            raise TenderPackageError(f"required file missing: {required}")

    # Check full.md is non-empty
    full_md = root / "full.md"
    if full_md.stat().st_size == 0:
        raise TenderPackageError("full.md is empty")

    # Check optional files and warn
    optional_files = {"content_list_v2.json", "block_list.json"}
    for opt in optional_files:
        if not (root / opt).exists():
            warnings.append(f"optional file missing: {opt}")

    # Warn if images/ directory is missing
    if not (root / "images").is_dir():
        warnings.append("images/ directory not found")

    # Validate manifest.tender_id
    if not manifest.tender_id.strip():
        raise TenderPackageError("manifest.tender_id is empty")

    return warnings


def read_full_markdown(root: Path) -> str:
    """Read the full.md file from package root."""
    full_md = root / "full.md"
    if not full_md.exists():
        raise TenderPackageError("full.md not found")
    return full_md.read_text(encoding="utf-8")


def is_allowed_derived_name(name: str) -> bool:
    """Check if a derived file name is in the whitelist."""
    return name in ALLOWED_DERIVED_NAMES
