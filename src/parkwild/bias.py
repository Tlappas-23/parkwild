"""Bias measurements: Track A against the Mapillary index (BUILD_SPEC.md Phase 3).

PROBLEM: street-level imagery can only see animals near where cameras
drove, and contributors upload in summer. Both biases are invisible from
inside Track B; they can only be measured against independent observations.

CURRENT:
  road bias      share of canonical, open-coordinate sightings in the corridor
                 bbox whose H3 r9 cell is not within RING cells of any image
                 position. That share is invisible to the imagery method by
                 construction and goes in the UI.
  seasonal bias  month histograms of imagery captures vs sightings, and the
                 June-to-August share of each.

Ring 1 (~350 m from a camera) is generous: whole-image detection is not
expected to work that far, so the road-bias figure is a lower bound on what
the imagery cannot see.

UNRESOLVED: the sightings themselves are road-biased (people observe from
roads too), so "fraction outside coverage" understates how much of the park
nobody has looked at. Neither source can measure that.
"""
from __future__ import annotations

import h3

from .decisionlog import log_filter
from .geo import BBox
from .storage import Store

# H3_RES — BORROWED (same cell size as the export, so coverage and cells line up)
H3_RES = 9

# RING — ASSUMED
# Cells within one ring of an image cell count as covered: roughly 350 m from
# a camera at r9. Generous on purpose; see the module docstring.
# REVISIT IF: Phase 0 measures a working detection range; then RING should
#   be derived from it.
RING = 1


def image_coverage_cells(store: Store, corridor: str, *, res: int = H3_RES, ring: int = RING) -> set[str]:
    """H3 cells within `ring` of any indexed image position in the corridor."""
    covered: set[str] = set()
    for lon, lat in store.sql("SELECT lon, lat FROM images WHERE corridor = ? AND lon IS NOT NULL", [corridor]):
        cell = h3.latlng_to_cell(lat, lon, res)
        covered.update(h3.grid_disk(cell, ring))
    return covered


def road_bias(store: Store, park: str, corridor: str, bbox: BBox, *, res: int = H3_RES, ring: int = RING) -> dict:
    """Share of canonical, open-coordinate sightings inside the corridor bbox
    that lie outside Mapillary coverage. Reported overall and by class."""
    covered = image_coverage_cells(store, corridor, res=res, ring=ring)
    rows = store.sql(
        """
        SELECT lon, lat, taxon_class FROM sightings
        WHERE park = ? AND duplicate_of IS NULL AND coordinate_status = 'open'
          AND lon BETWEEN ? AND ? AND lat BETWEEN ? AND ?
        """,
        [park, bbox.min_lon, bbox.max_lon, bbox.min_lat, bbox.max_lat],
    )
    by_class: dict[str, dict[str, int]] = {}
    n_covered = 0
    for lon, lat, cls in rows:
        inside = h3.latlng_to_cell(lat, lon, res) in covered
        n_covered += inside
        c = by_class.setdefault(cls or "unknown", {"n": 0, "covered": 0})
        c["n"] += 1
        c["covered"] += inside
    n = len(rows)
    result = {
        "park": park, "corridor": corridor, "h3_res": res, "ring": ring,
        "n_sightings_in_bbox": n,
        "n_covered": n_covered,
        "fraction_outside_coverage": (1 - n_covered / n) if n else None,
        "by_class": {k: {**v, "fraction_outside": (1 - v["covered"] / v["n"]) if v["n"] else None} for k, v in by_class.items()},
        "n_coverage_cells": len(covered),
    }
    log_filter("bias.road", f"sightings within ring {ring} of an image cell (H3 r{res}) count as covered", n, n_covered,
               park=park, corridor=corridor)
    return result


def seasonal_bias(store: Store, park: str, corridor: str) -> dict:
    """Month histograms (Jan..Dec) for imagery captures in the corridor and for
    sightings in the park, plus the share of each in June to August."""
    img = [0] * 12
    for m, c in store.sql("SELECT month(captured_at), count(*) FROM images WHERE corridor = ? AND captured_at IS NOT NULL GROUP BY 1", [corridor]):
        img[int(m) - 1] = c
    obs = [0] * 12
    for m, c in store.sql(
        "SELECT month(observed_on), count(*) FROM sightings WHERE park = ? AND duplicate_of IS NULL AND observed_on IS NOT NULL GROUP BY 1", [park]
    ):
        obs[int(m) - 1] = c

    def summer_share(h: list[int]) -> float | None:
        total = sum(h)
        return (sum(h[5:8]) / total) if total else None

    return {
        "park": park, "corridor": corridor,
        "images_by_month": img, "sightings_by_month": obs,
        "images_summer_share": summer_share(img), "sightings_summer_share": summer_share(obs),
        "months_with_no_imagery": [i + 1 for i, c in enumerate(img) if c == 0],
    }


def render_bias_markdown(road: dict, season: dict) -> str:
    fo = road["fraction_outside_coverage"]
    lines = [
        f"**Road bias** ({road['corridor']} imagery vs {road['park']} sightings inside the corridor bbox, H3 r{road['h3_res']}, ring {road['ring']})",
        "",
        f"- {road['n_sightings_in_bbox']:,} independent open-coordinate sightings in the bbox; {road['n_covered']:,} within imagery coverage",
        f"- **{100 * fo:.0f}% fall outside coverage** and are invisible to the imagery method by construction" if fo is not None else "- no sightings in bbox",
    ]
    for cls, v in sorted(road["by_class"].items()):
        if v["fraction_outside"] is not None:
            lines.append(f"- {cls}: {v['n']:,} sightings, {100 * v['fraction_outside']:.0f}% outside coverage")
    months = "JFMAMJJASOND"
    lines += [
        "",
        "**Seasonal bias**",
        "",
        "| | " + " | ".join(months) + " |",
        "|---|" + "---|" * 12,
        "| imagery | " + " | ".join(f"{c:,}" for c in season["images_by_month"]) + " |",
        "| sightings | " + " | ".join(f"{c:,}" for c in season["sightings_by_month"]) + " |",
        "",
        f"- June to August share: imagery {100 * (season['images_summer_share'] or 0):.0f}%, sightings {100 * (season['sightings_summer_share'] or 0):.0f}%",
        f"- months with no imagery at all: {season['months_with_no_imagery'] or 'none'}",
        "",
    ]
    return "\n".join(lines)
