"""Slice equirectangular panoramas into horizon windows for the detector.

PROBLEM: 87% of Lamar Valley's imagery is 360-degree panoramas (E-006). Fed
whole, a 4096 x 2048 panorama is resized by MegaDetector to 1280 px on the
long side, so a distant animal becomes three pixels and every straight line is
bent. The model was trained on ordinary photos.

CURRENT: cut the horizon band into four 90-degree yaw windows by plain
cropping of the equirectangular image. Near the horizon the equirectangular
projection is close enough to a perspective view that the crop reads as a
normal photo; distortion grows toward the poles, which the vertical band
excludes.

What this does NOT do: add pixels. A 4096-wide panorama is ~11 px per degree
of yaw; a 90-degree window is 1024 px wide whether or not it is cut out. A
bison at 100 m is ~11 px tall in it either way. Never read slice results as
"extended range" (BUILD_SPEC.md, Do not).

CONSIDERED, NOT DONE: true gnomonic reprojection (py360convert or a few lines
of numpy). Correct at the window edges where plain cropping stretches by
~15% at ±45 degrees, but that stretch is far smaller than the detector's own
tolerance, and it is one more dependency. Revisit if slice precision is
clearly worse than perspective precision for reasons that look geometric.

UNRESOLVED: whether slicing changes the detection rate at all versus feeding
the whole panorama. EXPERIMENTS.md Q-2 is the ablation; nothing has run yet.

Naming: <image_id>__yaw090.jpg. Yaw is degrees clockwise from the frame
centre, which on Mapillary panoramas is the camera's compass heading, so
Phase 4 can recover a bearing per slice.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

# YAWS — ARBITRARY
# Four non-overlapping windows cover the full circle with no seam handling
# between windows; an animal straddling a boundary is cut. Overlapping
# windows (e.g. every 45 degrees) would double inference cost to fix a case
# that has not been observed yet.
# REVISIT IF: review shows animals cut by window edges.
YAWS = (0, 90, 180, 270)

# DEFAULT_HFOV — ASSUMED
# 90 degrees is a wide-angle phone camera, i.e. what the perspective
# population looks like, so the two populations are roughly comparable per
# frame. 60 would be more "normal lens" but needs six windows.
# REVISIT IF: Q-2 shows a strong FOV dependence.
DEFAULT_HFOV = 90.0

# DEFAULT_VFOV — ASSUMED
# The band from 30 degrees above the horizon to 30 below. Animals are on the
# ground within a few degrees of the horizon at any distance that matters;
# the band is generous so a near animal or a hillside is not cut.
DEFAULT_VFOV = 60.0


def slice_equirectangular(
    pano_path: Path,
    image_id: str,
    out_dir: Path,
    *,
    yaws: tuple[int, ...] = YAWS,
    hfov_deg: float = DEFAULT_HFOV,
    vfov_deg: float = DEFAULT_VFOV,
    quality: int = 92,
) -> list[Path]:
    """Write one JPEG per yaw window. Idempotent: existing slices are kept."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with Image.open(pano_path) as im:
        im = im.convert("RGB")
        W, H = im.size
        # Rows: pitch runs +90 (top) to -90 (bottom) across H pixels.
        y0 = int(round((90 - vfov_deg / 2) / 180 * H))
        y1 = int(round((90 + vfov_deg / 2) / 180 * H))
        half = hfov_deg / 360 * W / 2
        for yaw in yaws:
            dest = out_dir / f"{image_id}__{variant_name(yaw)}.jpg"
            if dest.exists():
                written.append(dest)
                continue
            cx = W / 2 + (yaw % 360) / 360 * W     # centre column of this window
            tile = _crop_wrapped(im, int(round(cx - half)), int(round(cx + half)), y0, y1)
            tile.save(dest, quality=quality)
            written.append(dest)
    return written


def slice_all(pano_rows: list[dict], out_dir: Path, **kwargs) -> dict[str, int]:
    """pano_rows: dicts with image_id and local_path (from Store.downloaded)."""
    n_panos = n_slices = 0
    for row in pano_rows:
        paths = slice_equirectangular(Path(row["local_path"]), row["image_id"], out_dir, **kwargs)
        n_panos += 1
        n_slices += len(paths)
    return {"panos": n_panos, "slices": n_slices}


# ---- pure helpers ---------------------------------------------------------------------

def variant_name(yaw: int) -> str:
    return f"yaw{int(yaw) % 360:03d}"


def variant_yaw(variant: str) -> float | None:
    """'yaw090' -> 90.0; 'full' -> None."""
    if variant.startswith("yaw") and variant[3:].isdigit():
        return float(variant[3:])
    return None


def slices_dir_for(pano_dir: Path) -> Path:
    """data/images/<corridor>_pano -> data/images/<corridor>_pano_slices"""
    return pano_dir.with_name(pano_dir.name + "_slices")


def slice_path_for(pano_path: Path, image_id: str, variant: str) -> Path:
    return slices_dir_for(Path(pano_path).parent) / f"{image_id}__{variant}.jpg"


def _crop_wrapped(im: Image.Image, x0: int, x1: int, y0: int, y1: int) -> Image.Image:
    """Crop columns x0..x1 where x may run past either edge; the panorama
    wraps, so the missing part comes from the other side."""
    W = im.width
    x0m, x1m = x0 % W, x1 % W
    if x0m < x1m:
        return im.crop((x0m, y0, x1m, y1))
    left = im.crop((x0m, y0, W, y1))
    right = im.crop((0, y0, x1m, y1))
    out = Image.new("RGB", (left.width + right.width, y1 - y0))
    out.paste(left, (0, 0))
    out.paste(right, (left.width, 0))
    return out
