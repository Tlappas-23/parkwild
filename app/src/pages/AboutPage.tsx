import { useStore } from "../store/index";

// This page is not optional (BUILD_SPEC.md). Methods, limitations, licensing,
// and the bias figures in plain language, for the park that is open. It says
// where a computer model is involved and, more often, where it is not: the
// owner's rule is that the page never claims a model that did not run here.
export default function AboutPage() {
  const { species, manifest, cells, bias, parkName, landmarks, cameraPass } = useStore();
  const named = (list: string[]) =>
    list.map((n) => species?.species.find((s) => s.scientific_name === n)?.common_name ?? n).join(", ");
  const excluded = Object.keys(cells?.suppressed.excluded ?? {});
  const coarsened = Object.keys(cells?.suppressed.coarsened ?? {});
  const passRan = (cameraPass?.corridors ?? []).filter((c) => c.status !== "planned");
  const passQueued = (cameraPass?.corridors ?? []).filter((c) => c.status === "planned");
  const modelCells = (cells?.features ?? []).some((f) => f.properties.mp > 0);
  const total = (species?.species ?? []).reduce((a, s) => a + s.sightings, 0);
  const years = (() => {
    let lo = 9999,
      hi = 0;
    for (const f of cells?.features ?? []) {
      if (f.properties.y0) lo = Math.min(lo, f.properties.y0);
      if (f.properties.y1) hi = Math.max(hi, f.properties.y1);
    }
    return lo < hi ? `${lo} to ${hi}` : null;
  })();
  const short = parkName.replace(/ National Park.*$/, "");

  return (
    <article className="page prose">
      <h1>About this map</h1>
      <p className="lede">
        Where and when animals have been recorded in {parkName}, from public observations by people who were there,
        aggregated into hexagonal cells about 170 m across. It is a record of what people reported, not a survey of what
        lives here.
      </p>

      <h2>What you are looking at</h2>
      <p>
        Each hexagon holds every sighting whose coordinates fall inside it; the deeper the blue, the more sightings.
        Sensitive species are drawn in much larger cells or not at all.
        {modelCells
          ? " A hexagon turns amber only where the roadside camera pass added a sighting of its own; see below."
          : ` Every hexagon in ${short} is blue: every sighting here was reported by a person.`}
      </p>
      <p>
        {species
          ? `${short} holds ${total.toLocaleString()} sightings of ${species.species.length} species${years ? `, recorded ${years}` : ""}.`
          : ""}{" "}
        <span className="badge human">verified</span> means iNaturalist research grade (at least two people agreed on
        the identification) or another GBIF dataset with its own review. The photographs on this site are the observers'
        own, shown under the licence each chose and credited beside every image.
      </p>

      <h2>What the map cannot tell you</h2>
      <ul>
        <li>
          <strong>An empty cell means nobody looked</strong>, not that nothing lives there. Observations cluster on
          roads, trails and viewpoints.
        </li>
        <li>
          <strong>Seasons reflect visitors.</strong> Most observations are from June to August because that is when
          people are in the park. The species pages show a second figure, the species' share of each month against
          everyone's, which separates the animal's season from the visitors'.
        </li>
        <li>
          <strong>Recall is unmeasured.</strong> Nobody has counted every animal, so there is no way to say what
          fraction was recorded. No recall number is published because it would be invented.
        </li>
        <li>
          <strong>Positions are approximate.</strong> Sources report accuracy from a few metres to a few kilometres;
          cells are sized to that, and points are never shown.
        </li>
      </ul>

      <h2>Sensitive species</h2>
      <p>
        Some species are deliberately not mapped, or mapped only at about 3 km cells, because a precise public map of
        them would help the wrong people.
        {excluded.length > 0 && <> Not shown: {named(excluded)}.</>}
        {coarsened.length > 0 && <> Shown coarsely: {named(coarsened)}.</>} Where a source already obscures a location,
        that record is counted but never mapped, its photographs never appear in a cell, and it is never listed by
        landmark or trail.
      </p>

      <h2 id="camera-pass">Where a computer model is involved, and where it is not</h2>
      <p>Two things on this site can involve a model. Here is the state of each for {short}.</p>
      <h3>Roadside camera pass</h3>
      {passRan.length > 0 ? (
        <>
          <p>
            A computer-vision model (SpeciesNet: a detector and a species classifier) looked for animals in street-level
            photographs taken from park roads (Mapillary, CC BY-SA). It is a supplementary layer, kept apart from human
            sightings on purpose and drawn amber: it sees only what a car sees, mostly in June, and its measured
            precision is below half at the threshold used. Its counts are small and shown as they are.
          </p>
          <div className="table-wrap">
            <table className="pass">
              <thead>
                <tr>
                  <th>Corridor</th>
                  <th>Frames scored</th>
                  <th>Frames with an animal</th>
                  <th>Sightings</th>
                  <th>Named to species</th>
                  <th>Measured precision</th>
                </tr>
              </thead>
              <tbody>
                {cameraPass!.corridors.map((c) => (
                  <tr key={c.key}>
                    <td>
                      {c.name}
                      {c.status === "planned" ? <span className="muted"> · queued</span> : ""}
                    </td>
                    <td>{c.frames_scored.toLocaleString()}</td>
                    <td>{c.frames_with_animal.toLocaleString()}</td>
                    <td>{c.sightings.toLocaleString()}</td>
                    <td>
                      {c.named.toLocaleString()}
                      {Object.keys(c.species_named).length > 0
                        ? ` (${Object.entries(c.species_named)
                            .map(
                              ([k, v]) =>
                                `${species?.species.find((s) => s.scientific_name === k)?.common_name ?? k} ${v}`,
                            )
                            .join(", ")})`
                        : ""}
                    </td>
                    <td>
                      {c.precision && c.precision.precision !== null
                        ? `${Math.round(100 * c.precision.precision)}% (95% CI ${Math.round(100 * (c.precision.ci?.[0] ?? 0))} to ${Math.round(100 * (c.precision.ci?.[1] ?? 0))}%, n=${c.precision.n}, reviewer ${c.precision.reviewer})`
                        : c.status === "planned"
                          ? "—"
                          : "not yet reviewed"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted small">
            {cameraPass!.model}. A frame counts as having an animal at detector confidence{" "}
            {cameraPass!.thresholds.detection_min_conf} or better; a species is named only when the classifier scores{" "}
            {cameraPass!.thresholds.species_min_score} or better, otherwise the sighting is "unidentified large mammal".
            Precision is the share of reviewed detections that a person confirmed as an animal. Detections are
            positioned at the camera, about {cameraPass!.thresholds.range_m} m from the animal.
          </p>
        </>
      ) : (
        <p>
          <strong>No computer-vision pass has run in {short}.</strong> Every count, cell and photograph here comes from
          people.
          {passQueued.length > 0
            ? ` A pass is queued for ${passQueued.map((c) => c.name.split(",")[0]).join(" and ")}; until it runs and is reviewed, nothing on this map is machine-detected.`
            : ""}
        </p>
      )}
      <h3>Ask, on your device</h3>
      <p>
        The Ask page can run a small language model in your browser, but only after you press Enable and download it
        (about 1 GB, once). Until then no language model is involved anywhere on this site: the tour text is the opening
        of each place's Wikipedia article, the numbers are counts, the routes are shortest paths over OpenStreetMap
        roads. When enabled, the model may only write from numbered facts drawn from this data, must cite one for every
        sentence, and says "the data doesn't say" otherwise; the answer shows which facts it used and flags any number
        that is in none of them. "What did I see?" ranks a photograph against this park's species names with an image
        model, on your device, as a suggestion only. Nothing you type or photograph leaves your device. Models: Qwen2.5
        1.5B Instruct (Apache-2.0) via WebLLM, CLIP ViT-B/32 (MIT) via Transformers.js. The question set and its
        measured results are in the repository (docs/ai-eval.md).
      </p>

      <h2>Road bias and seasonal bias</h2>
      {bias ? (
        <>
          <p>
            Of {bias.road.n_sightings_in_bbox.toLocaleString()} independent sightings inside the{" "}
            {bias.road.corridor.replace("_", " ")} corridor,{" "}
            <strong>
              {Math.round(100 * (bias.road.fraction_outside_coverage ?? 0))}% fall outside street-level imagery coverage
            </strong>{" "}
            (more than about {bias.road.ring === 1 ? "350" : "170"} m from any camera position). The imagery method
            cannot see those by construction.
          </p>
          <p>
            Imagery captures are {Math.round(100 * (bias.seasonal.images_summer_share ?? 0))}% June to August; human
            sightings are {Math.round(100 * (bias.seasonal.sightings_summer_share ?? 0))}%.
            {bias.seasonal.months_with_no_imagery.length > 0 && (
              <> Months with no imagery at all: {bias.seasonal.months_with_no_imagery.join(", ")}.</>
            )}
          </p>
        </>
      ) : (
        <p className="muted">
          Not measured for {short}: these figures compare street-level imagery with human sightings, and no imagery
          corridor has been pulled here.
        </p>
      )}

      <h2>Sources and licences</h2>
      <ul>
        <li>
          iNaturalist observations and photographs: each carries its observer's chosen licence. Photographs are shown
          only under CC0, CC BY, CC BY-SA, CC BY-NC or CC BY-NC-SA, always with the observer's name and a link;
          no-derivatives and all-rights-reserved photographs are not shown.
        </li>
        <li>
          GBIF-mediated datasets: per-record licence and dataset credit stored with every record. The iNaturalist mirror
          in GBIF is excluded to avoid double counting; eBird is not included.
        </li>
        <li>
          Street-level imagery: Mapillary, CC BY-SA 4.0; image ID and contributor stored with every derived record.
          Images themselves are not redistributed; "look around" links open Mapillary.
        </li>
        <li>
          Basemap:{" "}
          <a href="https://openfreemap.org" target="_blank" rel="noreferrer">
            OpenFreeMap
          </a>
          , © OpenStreetMap contributors, ODbL. Satellite view: USGS The National Map, public domain. Relief and 3D
          terrain: Mapzen/AWS Terrain Tiles (USGS 3DEP, SRTM), open data.
        </li>
        <li>
          Landmarks, trails, campsites and facilities: OpenStreetMap, ODbL
          {landmarks ? ` (${landmarks.landmarks.length} landmarks in ${short})` : ""}. Place descriptions are the
          opening of each Wikipedia article, CC BY-SA 4.0, linked beside the text. Photographs of places: Wikimedia
          Commons, each under the licence printed beside it. The park outline is the iNaturalist place polygon the
          sightings were filtered by.
        </li>
      </ul>

      <h2>How this site is built</h2>
      <p>
        Everything is static files: a Python pipeline bakes each park's data, a React app reads it, GitHub Pages serves
        it; there is no server and no account. Every data file is hashed and the app refuses one that does not match.
        The architecture, the user guide, the decision records and the experiment ledger are in the repository:{" "}
        <a
          href="https://github.com/Tlappas-23/parkwild/blob/main/docs/ARCHITECTURE.md"
          target="_blank"
          rel="noreferrer"
        >
          architecture
        </a>
        ,{" "}
        <a href="https://github.com/Tlappas-23/parkwild/blob/main/docs/USER-GUIDE.md" target="_blank" rel="noreferrer">
          how to use the site
        </a>
        ,{" "}
        <a href="https://github.com/Tlappas-23/parkwild/blob/main/DECISIONS.md" target="_blank" rel="noreferrer">
          decisions
        </a>
        ,{" "}
        <a href="https://github.com/Tlappas-23/parkwild/blob/main/EXPERIMENTS.md" target="_blank" rel="noreferrer">
          experiments
        </a>
        .
      </p>
      <p className="muted small">
        Data build {manifest?.built ?? "(development)"}
        {manifest?.git_commit ? `, commit ${manifest.git_commit.slice(0, 8)}` : ""}.
        {species ? ` ${species.species.length} species.` : ""} Data files are integrity-checked against a manifest
        compiled into this page.
      </p>
    </article>
  );
}
