import { useStore } from "../store";

// This page is not optional (BUILD_SPEC.md). Methods, limitations, licensing,
// and the bias figures in plain language. Numbers come from the pipeline's
// exports where they exist; where they do not yet, the page says so.
export default function AboutPage() {
  const { species, manifest, cells, bias, parkName, landmarks, cameraPass } = useStore();
  const named = (list: string[]) => list.map((n) => species?.species.find((s) => s.scientific_name === n)?.common_name ?? n).join(", ");
  const excluded = Object.keys(cells?.suppressed.excluded ?? {});
  const coarsened = Object.keys(cells?.suppressed.coarsened ?? {});
  return (
    <article className="page prose">
      <h1>About this map</h1>
      <p className="lede">
        Where and when animals have been recorded in {parkName}, from public observations, aggregated into hexagonal cells about 170 m across.
        Most of it is people logging what they saw. It is not a survey.
      </p>

      <h2>What you are looking at</h2>
      <p>
        On the map, each hexagon is about 170 m across and holds every sighting whose coordinates fall inside it; the deeper the blue, the more sightings. A hexagon turns amber only where the roadside camera pass added a sighting of its own, which so far happens in one Yellowstone valley.
      </p>
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

      <h2>Ask, on your device</h2>
      <p>
        The Ask page runs a small language model in your browser after you choose to download it (about 1 GB, once). It may only write from
        numbered facts drawn from this site's data, must cite a fact for every sentence, and says "the data doesn't say" when the facts do not cover a
        question; the answer shows which facts it used and flags any number that is in none of them. "What did I see?" ranks a photograph against
        this park's species names with an image model, on your device, as a suggestion only. Nothing you type or photograph leaves your device.
        Models: Qwen2.5 1.5B Instruct (Apache-2.0) via WebLLM, CLIP ViT-B/32 (MIT) via Transformers.js. The question set and its measured results are in the repository (docs/ai-eval.md).
      </p>

      <h2 id="camera-pass">Roadside camera pass</h2>
      <p>
        Besides what people reported, a computer-vision model looked for animals in street-level photographs taken from park roads
        (Mapillary, CC BY-SA; <span className="badge model">model</span> on the map). It is a supplementary layer, kept apart from human
        sightings on purpose: it sees only what a car sees, mostly in June, and it is right less than half the time at the threshold used.
        Its counts are small and they are shown as they are.
      </p>
      {cameraPass && cameraPass.corridors.length > 0 ? (
        <div className="table-wrap">
          <table className="pass">
            <thead><tr><th>Corridor</th><th>Frames scored</th><th>Frames with an animal</th><th>Sightings</th><th>Named to species</th><th>Measured precision</th></tr></thead>
            <tbody>
              {cameraPass.corridors.map((c) => (
                <tr key={c.key}>
                  <td>{c.name}{c.status === "planned" ? <span className="muted"> · queued</span> : ""}</td>
                  <td>{c.frames_scored.toLocaleString()}</td>
                  <td>{c.frames_with_animal.toLocaleString()}</td>
                  <td>{c.sightings.toLocaleString()}</td>
                  <td>{c.named.toLocaleString()}{Object.keys(c.species_named).length > 0 ? ` (${Object.entries(c.species_named).map(([k, v]) => `${species?.species.find((s) => s.scientific_name === k)?.common_name ?? k} ${v}`).join(", ")})` : ""}</td>
                  <td>{c.precision && c.precision.precision !== null ? `${Math.round(100 * c.precision.precision)}% (95% CI ${Math.round(100 * (c.precision.ci?.[0] ?? 0))} to ${Math.round(100 * (c.precision.ci?.[1] ?? 0))}%, n=${c.precision.n}, reviewer ${c.precision.reviewer})` : c.status === "planned" ? "—" : "not yet reviewed"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted">The camera pass has not run in {parkName}.</p>
      )}
      {cameraPass && (
        <p className="muted small">
          {cameraPass.model}. A frame counts as having an animal at detector confidence {cameraPass.thresholds.detection_min_conf} or better; a species is named only when the classifier scores {cameraPass.thresholds.species_min_score} or better, otherwise the sighting is "unidentified large mammal".
          Precision is the share of reviewed detections that a person confirmed as an animal. Recall is unmeasured and will stay so: nobody counted every animal beside those roads.
          Detections are positioned at the camera, about {cameraPass.thresholds.range_m} m from the animal.
        </p>
      )}

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
        <li>Basemap: <a href="https://openfreemap.org" target="_blank" rel="noreferrer">OpenFreeMap</a>, © OpenStreetMap contributors, ODbL. Satellite view: USGS The National Map, public domain. Relief and 3D terrain: Mapzen/AWS Terrain Tiles (USGS 3DEP, SRTM), open data.</li>
        <li>Landmarks and tour stops: OpenStreetMap features with a Wikidata link, ODbL{landmarks ? ` (${landmarks.landmarks.length} in ${parkName})` : ""}. Stop descriptions are the opening of each Wikipedia article, CC BY-SA 4.0, linked beside the text. The park outline is the iNaturalist place polygon the sightings were filtered by.</li>
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
