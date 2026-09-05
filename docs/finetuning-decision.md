# Should we fine-tune the models? A decision walkthrough

Written before Phase 0 has run, so this is the *procedure* for deciding, not the
decision. The short version: fine-tuning is a response to a measured failure
mode, never a default, and there are four cheaper levers to pull first.

## 0. Do not decide before Phase 0 reports

Fine-tuning fixes a model that is wrong in a specific way on a specific
distribution. Until the five Phase 0 numbers exist, there is no failure mode to
target. The only thing to do now is make sure Phase 0 measures the things the
decision needs, which it does: detection rate, precision on inspection, range,
species agreement, and the raw volume of imagery.

## 1. Name the failure mode, because each one has a different fix

There are three separate models in the ensemble and each fails differently.

| Symptom in Phase 0 | Which part is failing | Cheapest fix first | Fine-tune only if |
|---|---|---|---|
| Few boxes at all, but I can see animals in frames when I scan them myself | MegaDetector **recall** on small, distant objects | Tiled inference: cut each frame into overlapping crops, run the detector per crop, merge boxes. No training. | Tiling helps but plateaus, and I have hand-drawn boxes for the misses |
| Plenty of boxes, mostly rocks, shrubs, logs, car parts | MegaDetector **precision** (domain shift from camera traps) | Raise the threshold; require the classifier to agree (SpeciesNet already rolls low-confidence animals to "blank"); temporal consistency across consecutive frames in a sequence | Precision stays bad above 0.8 confidence and I have a few hundred labelled hard negatives |
| Boxes are right, species label is wrong | **Classifier** | Geofence to the state (`--admin1_region`), restrict with `--target_species_txt` to the dozen species that occur in the corridor, accept rollups to genus/family as correct | Confusions persist among the corridor's own species (elk vs mule deer, bison vs cattle) |
| Few frames contain any animal at all, boxes are correct when present | Nothing is failing. This is **base rate**. | Pre-filter by Mapillary's own `animal--ground-animal` labels, choose corridors with higher density, accept a low hit rate and crawl more | Never. Training cannot manufacture animals that are not in the frames. |

If Phase 0 lands in the last row, the honest report is "the pipeline works but
the source is sparse", and the decision is about scale, not models.

## 2. Zero-training levers, in the order I would try them

1. **Threshold and gating.** Report precision by confidence band (the notebook
   does this). If 0.8+ is clean, use 0.8 and accept the recall hit.
2. **Geofence and target species.** `--country USA --admin1_region WY` is
   already on. A `target_species_txt` for the corridor removes most impossible
   confusions.
3. **Temporal consistency.** Street-level frames come in sequences at a few
   metres apart. A real bison appears in 5 consecutive frames, drifting
   predictably; a rock that fooled the detector once usually does not fool it
   at the next angle. This is a Phase 2 filter, cheap, and specific to this
   data source. Camera-trap models never had it.
4. **Tiled inference.** Measure recall on the manual set at whole-image vs 2x2
   and 3x3 overlapping tiles. Cost is linear in tiles; on an M2 Pro that is
   minutes per hundred images, so it is affordable for a corridor and painful
   for a park.

Only after these four have been measured does fine-tuning enter.

## 3. If fine-tuning is warranted: what, on what data, where

**What to tune.** The classifier head is cheap and local: it takes crops, and
crops from street-level frames are not that different from crops from camera
traps once the animal fills them. The detector is the expensive one; it needs
box labels and a GPU, and the domain gap is the whole image, not the crop.
So: classifier first, detector only with evidence from row 1 of the table.

**Where labels come from, at zero cost.**

- My own Phase 0 and Phase 2 review CSVs. Every `tp`/`fp` verdict is a labelled
  crop; every corrected `true_species` is a classifier label. This is the only
  source that is actually in-domain.
- iNaturalist research-grade photos of the corridor's species, filtered by
  `license_code` to CC0 / CC-BY / CC-BY-NC / CC-BY-SA. Not street-level, but
  real animals at varied distances and angles, and thousands of them. Good for
  the classifier, useless for the detector's domain problem.
- Mapillary frames that Mapillary's own segmentation tagged `animal--ground-animal`.
  Weak labels, but free and in-domain. Worth pulling with
  `phase0.py pull --with-mapillary-detections` and checking how they overlap
  with MegaDetector's boxes.

**Licensing.** Mapillary imagery is CC BY-SA 4.0. Training on it and keeping
the weights private is fine. Publishing fine-tuned weights raises the
share-alike question, which is unsettled for models; I would treat published
weights as BY-SA and say so. iNaturalist photos are licensed per photo; keep
the `license_code` and observer with every training image.

**Compute.** Kaggle's 30 free GPU hours a week cover a classifier fine-tune many
times over and a small detector fine-tune (a few thousand images, a few epochs)
once or twice. The M2 Pro with MPS handles classifier-head training locally.
Nothing here needs a card.

## 4. How to test it without fooling myself

- **Split by sequence, never by image.** Consecutive frames are near-duplicates.
  A random image split leaks the training set into the test set and produces a
  number that means nothing.
- **Better: split by corridor.** Train on Lamar, test on Cades Cove. That
  measures whether the fine-tune generalises or memorised one road.
- **Freeze a test set before any tuning.** The Phase 0 review set is the seed of
  it. It is never trained on and never looked at while iterating.
- **Score both models into `predictions_raw` under different `model_version`
  values.** The schema already keys on `(image_id, model_version)`, so baseline
  vs fine-tuned is one SQL join against `manual_review`, and the raw output of
  each is preserved.
- **Report precision, recall and species top-1 side by side, on the same
  frozen set, with counts.** Thirty samples is enough to notice a disaster and
  not enough to claim a 5-point improvement; say which.

## 5. The rule

Fine-tune only when a specific, measured failure survives the four zero-training
levers, and only with a frozen, sequence-disjoint test set already in hand.
Write the before/after numbers in RESULTS.md, including the ones that got worse.
