"""
parkwild: find animals in crowdsourced street-level photos of US national parks.

The package is a set of boring, deterministic batch steps:

    geo        -> bbox tiling and distance math (no I/O)
    config     -> paths, token, corridor definitions
    mapillary  -> Graph API client that respects the bbox/pagination limits
    overpass   -> road/trail length inside a bbox (for image-density numbers)
    storage    -> DuckDB schema and upserts
    download   -> fetch full-resolution frames for a sample of images
    speciesnet_runner -> run MegaDetector + SpeciesNet, parse its JSON
    review     -> build the manual-inspection gallery and CSV
    report     -> compute the Phase 0 numbers and write RESULTS.md

`scripts/phase0.py` strings these together as CLI subcommands.
"""

__version__ = "0.0.1"
