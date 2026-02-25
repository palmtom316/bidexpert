"""Unpack .tender.zip, load manifest, validate package structure."""

from __future__ import annotations

import io
import json
import logging
import shutil
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


def _zip_safety_limits() -> tuple[int, int, int, float]:
    # Imported lazily to avoid config import side effects in tooling contexts.
    from app.core.config import settings

    max_entries = max(1, int(settings.tender_zip_max_entries))
    max_total = max(1, int(settings.tender_zip_max_total_uncompressed_bytes))
    max_single = max(1, int(settings.tender_zip_max_single_file_bytes))
    max_ratio = float(settings.tender_zip_max_compression_ratio)
    if max_ratio <= 1:
        max_ratio = 100.0
    return max_entries, max_total, max_single, max_ratio


def _safe_extract_zip(zf: zipfile.ZipFile, workspace: Path) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    workspace_root = workspace.resolve()

    max_entries, max_total, max_single, max_ratio = _zip_safety_limits()
    entries = [info for info in zf.infolist() if info.filename and not info.is_dir()]
    if len(entries) > max_entries:
        raise TenderPackageError(f"zip has too many entries: {len(entries)} > {max_entries}")

    total_uncompressed = 0
    for info in entries:
        name = str(info.filename or "")
        normalized = name.replace("\\", "/")
        entry_path = Path(normalized)

        if entry_path.is_absolute() or ".." in entry_path.parts:
            raise TenderPackageError(f"unsafe zip entry: {name}")

        # Basic decompression bomb guard (ZipInfo is untrusted; enforced again during copy).
        uncompressed = int(getattr(info, "file_size", 0) or 0)
        compressed = int(getattr(info, "compress_size", 0) or 0)
        if uncompressed > max_single:
            raise TenderPackageError(f"zip entry too large: {name}")
        if compressed > 0 and uncompressed / max(1, compressed) > max_ratio:
            raise TenderPackageError(f"zip entry compression ratio too high: {name}")
        total_uncompressed += uncompressed
        if total_uncompressed > max_total:
            raise TenderPackageError("zip uncompressed size exceeds limit")

        target = (workspace_root / entry_path).resolve(strict=False)
        try:
            target.relative_to(workspace_root)
        except ValueError as exc:
            raise TenderPackageError(f"unsafe zip entry: {name}") from exc

        target.parent.mkdir(parents=True, exist_ok=True)

        copied = 0
        with zf.open(info, "r") as src, target.open("wb") as dst:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                copied += len(chunk)
                if copied > max_single:
                    raise TenderPackageError(f"zip entry too large: {name}")
                dst.write(chunk)


def unpack_zip(zip_bytes: bytes, workspace: Path) -> Path:
    """Extract .tender.zip contents into *workspace* directory.

    Returns the root directory containing the extracted files.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            _safe_extract_zip(zf, workspace)
    except zipfile.BadZipFile as exc:
        raise TenderPackageError("file is not a valid zip archive") from exc
    except TenderPackageError:
        shutil.rmtree(workspace, ignore_errors=True)
        raise

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
