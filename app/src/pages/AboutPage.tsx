import { useStore } from "../store";

// This page is not optional (BUILD_SPEC.md). Methods, limitations, licensing,
// and the bias figures in plain language. Numbers come from the pipeline's
// exports where they exist; where they do not yet, the page says so.
export default function AboutPage() {
  const { species, manifest, cells, bias } = useStore();
  const named = (list: string[]) => list.map((n) => species?.species.find((s) => s.scientific_name === n)?.common_name ?? n).join(", ");
  const excluded = Object.keys(cells?.suppressed.excluded ?? {});
  const coarsened = Object.keys(cells?.suppressed.coarsened ?? {});
  return (
    <article className="page prose">
      <h1>About this map</h1>
      <p className="lede">
        Where and when animals have been recorded in Yellowstone, from public observations, aggregated into hexagonal cells about 170 m across.
        Most of it is people logging what they saw. It is not a survey.
      </p>

      <h2>What you are looking at</h2>
      <p>
        <span className="badge human">verified</span> cells come from iNaturalist research-grade observations and other GBIF datasets: a person saw the animal and at least one other person agreed on the identification. The photographs on this site are theirs, shown under the licence each chose and credited beside every image.{" "}
        <span className="badge model">model</span> cells come from a computer-vision pass over street-level photographs and are drawn in a different colour on purpose; that source is a supplementary layer with measured precision of about 40% at its threshold.
      </p>

      <h2>What the map cannot tell you</h2>
      <ul>
        <li><strong>An empty cell means nobody looked</strong>, not that nothing lives there. Observations cluster on roads, trails and viewpoints.</li>
        <li><strong>Seasons reflect visitors.</strong> Most observations are from June to August because that is when people are in the park.</li>
        <li><strong>Recall is unmeasured.</strong> Nobody has counted every animal, so there is no way to say what fraction was recorded. No recall number is published because it would be invented.</li>
        <li><strong>Positions are approximate.</strong> Sources report accuracy from a few metres to a few kilometres; cells are sized to that, and points are never shown.</li>
      </ul>

      <h2>Sensitive species</h2>
      <p>
        Some species are deliberately not mapped, or mapped only at ~3 km cells, because a precise public map of them would help the wrong people.
        {excluded.length > 0 && <> Not shown: {named(excluded)}.</>}
        {coarsened.length > 0 && <> Shown coarsely: {named(coarsened)}.</>}{" "}
        Where a source already obscures a location, that record is counted but never mapped, and its photographs never appear in a cell.
      </p>

      <h2>Road bias and seasonal bias</h2>
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
        <p className="muted">Measured figures are published here once the imagery track has run.</p>
      )}

      <h2>Sources and licences</h2>
      <ul>
        <li>iNaturalist observations and photographs: each carries its observer's chosen licence. Photographs are shown only under CC0, CC BY, CC BY-SA, CC BY-NC or CC BY-NC-SA, always with the observer's name and a link; no-derivatives and all-rights-reserved photographs are not shown.</li>
        <li>GBIF-mediated datasets: per-record licence and dataset credit stored with every record. The iNaturalist mirror in GBIF is excluded to avoid double counting; eBird is not included.</li>
        <li>Street-level imagery: Mapillary, CC BY-SA 4.0; image ID and contributor stored with every derived record. Images themselves are not redistributed.</li>
        <li>Basemap: <a href="https://openfreemap.org" target="_blank" rel="noreferrer">OpenFreeMap</a>, © OpenStreetMap contributors, ODbL.</li>
        <li>
          3D models:{" "}
          {(species?.species.filter((x) => x.model) ?? []).length === 0 ? "none yet." : species!.species.filter((x) => x.model).map((x) => (
            <span key={x.scientific_name}>{x.common_name ?? x.scientific_name}: <a href={x.model!.source} target="_blank" rel="noreferrer">{x.model!.credit}</a>. </span>
          ))}
        </li>
      </ul>
      <p className="muted small">
        Data build {manifest?.built ?? "(development)"}{manifest?.git_commit ? `, commit ${manifest.git_commit.slice(0, 8)}` : ""}.
        {species ? ` ${species.species.length} species.` : ""} Data files are integrity-checked against a manifest compiled into this page.
      </p>
    </article>
  );
}
