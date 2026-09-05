#!/usr/bin/env python
"""
Turn downloaded GLB files into app assets with their provenance recorded.

For each entry in config/models.toml whose raw file exists under
app/public/models/raw/: hash the raw file, Draco-compress it with
gltf-transform into app/public/models/<key>.glb, refuse anything over the
2 MB budget (BUILD_SPEC.md Phase 6), and write app/public/models/index.json:
species -> {url, credit, license, source, sha256_raw, sha256, bytes}. The
export reads that index to fill `model` in species.json, and the About page
prints the credit lines from it. Missing raw files are reported, not fatal.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "app" / "public" / "models" / "raw"
OUT_DIR = ROOT / "app" / "public" / "models"
# CONFIG — DERIVED (the species-to-model mapping lives in config/models.toml)
CONFIG = ROOT / "config" / "models.toml"

# MAX_BYTES — BORROWED (BUILD_SPEC.md Phase 6: "under 2 MB each")
MAX_BYTES = 2 * 1024 * 1024


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compress(src: Path, dst: Path) -> None:
    """Draco-compress via gltf-transform (npx, from app/node_modules). Falls back
    to a plain copy if the CLI is missing, and says so."""
    cli = ROOT / "app" / "node_modules" / ".bin" / "gltf-transform"
    if not cli.exists():
        print("  gltf-transform not installed (cd app && npm i -D @gltf-transform/cli); copying uncompressed")
        shutil.copy2(src, dst)
        return
    subprocess.run([str(cli), "optimize", str(src), str(dst), "--compress", "draco", "--texture-compress", "webp"], check=True,
                   capture_output=True, text=True)


def main() -> int:
    with open(CONFIG, "rb") as fh:
        entries = tomllib.load(fh)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index: dict[str, dict] = {}
    missing: list[str] = []
    for key, e in entries.items():
        raw = RAW_DIR / e["file"]
        if not raw.exists():
            missing.append(f"{key}: {e['file']}")
            continue
        dst = OUT_DIR / f"{key}.glb"
        raw_hash = sha256(raw)
        compress(raw, dst)
        size = dst.stat().st_size
        if size > MAX_BYTES:
            print(f"  {key}: {size / 1024:.0f} KB exceeds the 2 MB budget; not shipped")
            dst.unlink()
            continue
        index[e["species"]] = {
            "url": f"models/{key}.glb", "title": e["title"], "author": e["author"], "source": e["source"],
            "license": e["license"], "license_line": e["license_line"], "credit": e["credit"],
            "sha256_raw": raw_hash, "sha256": sha256(dst), "bytes": size, "raw_file": e["file"],
        }
        print(f"  {key}: {raw.stat().st_size / 1024:.0f} KB -> {size / 1024:.0f} KB  ({e['license']})")
    (OUT_DIR / "index.json").write_text(json.dumps(index, indent=1))
    print(f"wrote {OUT_DIR / 'index.json'} with {len(index)} models")
    if missing:
        print("missing raw files (drop them into app/public/models/raw/):")
        for m in missing:
            print("  " + m)
    return 0


if __name__ == "__main__":
    sys.exit(main())
