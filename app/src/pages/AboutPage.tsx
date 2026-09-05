import { useStore } from "../store";

// This page is not optional (BUILD_SPEC.md). Methods, limitations, licensing,
// and the bias figures in plain language. Numbers come from the pipeline's
// exports where they exist; where they do not yet, the page says so.
export default function AboutPage() {
  const { species, manifest, cells, bias } = useStore();
  const excluded = Object.keys(cells?.suppressed.excluded ?? {});
  const coarsened = Object.keys(cells?.suppressed.coarsened ?? {});
  return (
    <article className="prose">
      <h2>About this map</h2>
      <p>
        This shows where and when animals have been recorded in Yellowstone, aggregated into hexagonal cells about 170 m across.
        It is built from public observations, mostly by people who logged what they saw. It is not a survey.
      </p>

      <h3>What the colours mean</h3>
      <p>
        <span className="badge human">human-verified</span> cells come from iNaturalist research-grade observations and other
        GBIF datasets: a person saw the animal and at least one other person agreed on the identification.{" "}
        <span className="badge model">model-predicted</span> cells come from a computer-vision pass over street-level photographs and
        are shown differently on purpose; that source is still being evaluated and is absent until it earns a place.
      </p>

      <h3>What the map cannot tell you</h3>
      <ul>
        <li><strong>An empty cell means nobody looked</strong>, not that nothing lives there. Observations cluster on roads, trails and viewpoints.</li>
        <li><strong>Seasons reflect visitors.</strong> Most observations are from June to August because that is when people are in the park.</li>
        <li><strong>Recall is unmeasured.</strong> Nobody has counted every animal, so there is no way to say what fraction was recorded. We do not publish a recall number because it would be invented.</li>
        <li><strong>Positions are approximate.</strong> Sources report accuracy from a few metres to a few kilometres; cells are sized to that, and points are never shown.</li>
      </ul>

      <h3>Sensitive species</h3>
      <p>
        Some species are deliberately not mapped, or mapped only at ~3 km cells, because a precise public map of them would help the wrong people.
        {excluded.length > 0 && <> Not shown: {excluded.join(", ")}.</>}
        {coarsened.length > 0 && <> Shown coarsely: {coarsened.join(", ")}.</>}{" "}
        Where a source already obscures a location, that record is counted but never mapped.
      </p>

      <h3>Road bias and seasonal bias</h3>
      {bias ? (
        <>
          <p>
            Of {bias.road.n_sightings_in_bbox.toLocaleString()} independent sightings inside the {bias.road.corridor.replace("_", " ")} corridor,{" "}
            <strong>{Math.round(100 * (bias.road.fraction_outside_coverage ?? 0))}% fall outside street-level imagery coverage</strong>{" "}
            (more than about {bias.road.ring === 1 ? "350" : "170"} m from any camera position). The imagery method cannot see those by construction.
          </p>
          <p>
            Imagery captures are {Math.round(100 * (bias.seasonal.images_summer_share ?? 0))}% June to August; human sightings are{" "}
            {Math.round(100 * (bias.seasonal.sightings_summer_share ?? 0))}%.
            {bias.seasonal.months_with_no_imagery.length > 0 && <> Months with no imagery at all: {bias.seasonal.months_with_no_imagery.join(", ")}.</>}
          </p>
        </>
      ) : (
        <p className="muted">Measured figures are published here once the imagery track has run; until then the qualitative statements above stand.</p>
      )}

      <h3>Sources and licenses</h3>
      <ul>
        <li>iNaturalist observations: each record carries its observer's chosen licence (CC0, CC BY, CC BY-NC and others); observer and licence are stored with every record.</li>
        <li>GBIF-mediated datasets: per-record licence and dataset credit stored with every record. The iNaturalist mirror in GBIF is excluded to avoid double counting. eBird is not included.</li>
        <li>Street-level imagery: Mapillary, CC BY-SA 4.0; image ID and contributor are stored with every derived record. Images themselves are not redistributed.</li>
        <li>Basemap: © OpenStreetMap contributors, ODbL.</li>
        <li>3D models: credited per species on this page as they are added.</li>
      </ul>
      <p className="muted small">
        Data build {manifest?.built ?? "(development)"}{manifest?.git_commit ? `, commit ${manifest.git_commit.slice(0, 8)}` : ""}.
        {species ? ` ${species.species.length} species.` : ""} Data files are integrity-checked against a manifest compiled into this page.
      </p>
    </article>
  );
}
