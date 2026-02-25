#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import tarfile
import urllib.request
from pathlib import Path


def _safe_write(dest_dir: Path, rel_path: str, data: bytes) -> None:
    rel = Path(rel_path)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"unsafe tar entry: {rel_path}")
    target = (dest_dir / rel).resolve(strict=False)
    dest_root = dest_dir.resolve()
    target.relative_to(dest_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def _download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "bidexpert-vendor/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def vendor_remixicon(*, version: str, dest_dir: Path) -> None:
    url = f"https://registry.npmjs.org/remixicon/-/remixicon-{version}.tgz"
    tgz = _download(url)

    dest_dir.mkdir(parents=True, exist_ok=True)

    with tarfile.open(fileobj=io.BytesIO(tgz), mode="r:gz") as tf:
        prefix = "package/fonts/"
        for member in tf.getmembers():
            if not member.isfile():
                continue
            name = member.name or ""
            if not name.startswith(prefix):
                continue
            rel_path = name[len(prefix) :]
            if not rel_path:
                continue
            file_obj = tf.extractfile(member)
            if file_obj is None:
                continue
            _safe_write(dest_dir, rel_path, file_obj.read())

    css_path = dest_dir / "remixicon.css"
    if not css_path.is_file():
        raise RuntimeError(f"remixicon.css not found under {dest_dir}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Vendor remixicon fonts/css into app/ui for offline deployments.")
    parser.add_argument("--version", default="3.5.0", help="remixicon npm version (default: 3.5.0)")
    parser.add_argument(
        "--dest",
        default="app/ui/vendor/remixicon",
        help="destination directory inside repo (default: app/ui/vendor/remixicon)",
    )
    args = parser.parse_args()

    vendor_remixicon(version=str(args.version), dest_dir=Path(args.dest))
    print(f"Vendored remixicon@{args.version} into {args.dest}")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

