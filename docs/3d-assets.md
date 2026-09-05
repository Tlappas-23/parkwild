# 3D asset sourcing (Phase 6, started early)

The build spec says to start sourcing during Phase 1 because it is the only
part of the project with a hard external dependency. This is the working sheet:
which species need a model, where candidates were found, and the license status
of each. Nothing is downloaded until its license is recorded here as clear.

Rules (BUILD_SPEC.md): stylised low-poly is preferred; glTF, Draco-compressed,
under 2 MB each; license recorded per asset and credited on the attribution
page; unclear license is a stop-and-ask; Apple's assets are not an option.

## Target species (Yellowstone first)

The list will be replaced by the top species from `data/export/yellowstone/species.json`
once Track A has run; this is the obvious Lamar Valley set.

| Species | Candidate model | Source | License status | Notes |
|---|---|---|---|---|
| American bison | none found yet | Poly Pizza (browse, CC0 filter) | open | Poly Pizza blocks automated fetches; browse by hand |
| Elk | "Stag" | Quaternius Ultimate Animated Animal Pack | **ask** (see below) | large antlered deer reads as elk at stylised scale |
| Mule deer / white-tailed deer | "Deer" | Quaternius Ultimate Animated Animal Pack | **ask** | |
| Gray wolf | "Wolf" | Quaternius Ultimate Animated Animal Pack; also OpenGameArt "Animated Animales Low Poly" (Quaternius, listed CC0, FBX only) | **ask** | |
| Coyote | recolour of "Wolf" | as above | **ask** | derivative; QAL allows modification |
| Red fox | "Fox" | Quaternius Ultimate Animated Animal Pack | **ask** | |
| Grizzly / black bear | none confirmed CC0 | Sketchfab (filter Downloadable + CC0), Poly Pizza | open | Sketchfab hits found were royalty-free store items or unclear; keep looking |
| Moose | none confirmed | Poly Pizza search "moose" exists; license unread | open | |
| Pronghorn | none confirmed | Sketchfab tag "pronghorn" | open | |
| Bighorn sheep | "Bighorn (Demo Free Download)" by WildMesh 3D on Sketchfab | Sketchfab | open | demo of a paid model; license must be read on the page |
| Common raven / bald eagle | "Eagle" | OpenGameArt "Animated Animales Low Poly" (Quaternius, CC0 listing) | **ask** | FBX only; would need conversion to glTF |

## License record: Quaternius (decision O-5: proceed under QAL, credit anyway)

| Field | Value |
|---|---|
| Source | https://quaternius.com/license.html |
| License | Quaternius Asset License (QAL) v1.0, "Last updated: 8/28/2026" |
| Key terms | "You can use these assets, free of charge, in personal, educational, and commercial games and other projects, with no credit required. You just can't resell or redistribute the assets themselves as assets." |
| Retrieved | 2026-09-05 |
| Archive | https://web.archive.org/web/20260905165351/https://quaternius.com/license.html |
| Page hash (sha256 of the HTML as fetched) | d1b56be5228d372b049b45cc7447a823da7989a6cf7036f60cfac2284c8fcb0d |
| Pack page archive | https://web.archive.org/web/20260905165409/https://quaternius.com/packs/ultimateanimatedanimals.html |

The license page was updated eight days before this was retrieved, which is
why older listings (OpenGameArt, the pack page itself) still say CC0. Per the
decision, assets from Quaternius are used under QAL, credited on the
attribution page anyway, and the file hash of each downloaded asset is added
to the table above at download time.

## The Quaternius license question (resolved by O-5; kept for the record)

Two statements disagree, checked 2026-09-05:

- The pack page (quaternius.com/packs/ultimateanimatedanimals.html) and the
  OpenGameArt listing say **CC0**.
- The site's license page (quaternius.com/license.html) now states the
  **Quaternius Asset License (QAL) v1.0**: "You can use these assets, free of
  charge, in personal, educational, and commercial games and other projects,
  with no credit required", but "You may not extract, repackage, sublicense,
  sell, or otherwise redistribute the Assets ... as a standalone asset pack,
  stock file, template, or similar product."

For this app the practical difference: under either license we may ship the
models inside the app. Under QAL the raw `.glb` files served by the site are
technically downloadable by anyone, which is use-in-a-product rather than
redistribution-as-a-pack, but it is close enough to the line that the spec's
rule applies: **stop and ask**. Options: (a) ask Quaternius which license
applies to the pack (they answer on itch.io / Patreon); (b) treat as QAL,
credit anyway, and note it on the attribution page; (c) prefer CC0 models
from Poly Pizza where the per-model license is explicit.

## Where to look, by hand

- Poly Pizza: https://poly.pizza/explore/Animals with the license filter set
  to CC0. Each model page states author and license. Automated fetches get
  HTTP 403, so this is a browser job.
- Sketchfab: search with Downloadable + license CC0 filters. Many "free"
  models are CC-BY (fine, credit required) or store demos (not fine).
- Quaternius: https://quaternius.com/packs/ultimateanimatedanimals.html
  (12 animals, glTF included, animated). License question above.

## Pipeline once an asset is cleared

1. Record here: species, model name, author, source URL, license, date.
2. Convert to glTF if needed (Blender), Draco-compress (`gltf-transform`),
   confirm under 2 MB.
3. Store under `app/public/models/<species>.glb` with a sidecar
   `<species>.json` carrying the credit line.
4. Optional iOS path: convert to USDZ for AR Quick Look.
