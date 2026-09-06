// Shapes of the static files the pipeline bakes (parkwild/export.py,
// parkwild/photos.py, parkwild/landmarks.py). The app depends on these, never
// on the pipeline.

export type ConfidenceBasis = "human_verified" | "model_predicted";

// One species entry inside a cell: [species_index, count, human_verified, model_predicted, first_year, last_year]
export type SpeciesEntry = [number, number, number, number, number | null, number | null];

export interface CellProps {
  cell: string;
  res: number;
  coarsened: boolean;
  count: number;
  hv: number;
  mp: number;
  y0: number | null;
  y1: number | null;
  sp: SpeciesEntry[];
}

export interface SpeciesIndexEntry {
  n: string;
  c: string | null;
  k: string | null;
}

export type Ring = number[][];

export interface CellFeature {
  type: "Feature";
  geometry: { type: "Polygon"; coordinates: Ring[] };
  properties: CellProps;
}

export interface CellsFile {
  type: "FeatureCollection";
  features: CellFeature[];
  park: string;
  h3_res: number;
  species_index: SpeciesIndexEntry[];
  entry: string[];
  suppressed: { excluded: Record<string, number>; coarsened: Record<string, number> };
}

export interface Species {
  scientific_name: string;
  common_name: string | null;
  class: string | null;
  taxon_id: string | null;
  aliases: string[];
  other_names?: string[]; // the common names that lost the vote ("American Elk" for Wapiti); searchable
  suppression: { action: "exclude" | "coarsen"; res: number | null; why: string } | null;
  sightings: number;
  open_coordinates: number;
  obscured_coordinates: number;
  sources: { inaturalist: number; gbif: number; mapillary_cv: number };
  confidence_basis: { human_verified: number; model_predicted: number };
  first: string | null;
  last: string | null;
  months: number[];
}

export interface SpeciesFile {
  park: string;
  generated: string;
  species: Species[];
  notes: { recall: string; obscured: string; names?: string };
}

export interface Manifest {
  built: string;
  git_commit: string | null;
  park: string;
  name?: string; // display name, written by the pipeline from config/parks.toml
  state?: string;
  files: Record<string, { sha256: string; bytes: number }>;
}

export interface BiasFile {
  road: {
    corridor: string;
    n_sightings_in_bbox: number;
    n_covered: number;
    fraction_outside_coverage: number | null;
    by_class: Record<string, { n: number; covered: number; fraction_outside: number | null }>;
    ring: number;
    h3_res: number;
  };
  seasonal: {
    images_by_month: number[];
    sightings_by_month: number[];
    images_summer_share: number | null;
    sightings_summer_share: number | null;
    months_with_no_imagery: number[];
  };
}

// A photograph: id, extension, host index, observer, licence label, observation id, date, cell (species file only)
export interface SpeciesPhoto {
  i: number;
  e: string;
  h: number;
  o: string;
  l: string;
  obs: number;
  d: string | null;
  c: string | null;
}
export type CellPhotoEntry = [number, number, string, number, string, string, number, string | null];

export interface PhotosSpeciesFile {
  park: string;
  photo_hosts: string[];
  species: Record<string, SpeciesPhoto[]>;
  licence_rule: string;
}
export interface PhotosCellsFile {
  park: string;
  photo_hosts: string[];
  species_index: string[];
  cells: Record<string, CellPhotoEntry[]>;
  licence_rule: string;
}

export type PhotoSize = "square" | "small" | "medium" | "large";

// A landmark from OpenStreetMap; `tour` is the stop index when it is on the
// curated route, and only stops carry a Wikipedia summary.
export interface LandmarkSummary {
  extract: string | null;
  url: string;
  licence: string;
  attribution: string;
}
// A photograph of the place from Wikimedia Commons (reusable licence, credited) and
// the nearest street-level image on Mapillary (linked by id, never copied).
export interface LandmarkPhoto {
  url: string;
  page: string;
  dist_m: number;
  width: number | null;
  height: number | null;
  license: string;
  license_url: string;
  artist: string;
}
export interface StreetImage {
  image_id: string;
  username: string | null;
  captured_at: string | null;
  is_pano: boolean;
  dist_m: number;
  url: string;
  license: string;
}
export interface Landmark {
  id: string;
  name: string;
  kind: string;
  lon: number;
  lat: number;
  ele_m: number | null;
  wikidata: string | null;
  url: string | null;
  tour?: number;
  summary?: LandmarkSummary | null;
  photos?: LandmarkPhoto[];
  street?: StreetImage | null;
}
export interface LandmarksFile {
  park: string;
  fetched: string;
  attribution: Record<string, string>;
  landmarks: Landmark[];
  tour: string[];
  missing_stops: string[];
}

// The park outline, an iNaturalist place polygon.
export interface BoundaryFile {
  type: "Feature";
  geometry: { type: "Polygon"; coordinates: Ring[] } | { type: "MultiPolygon"; coordinates: Ring[][] };
  properties: { park: string; name: string; source: string; place_id: number; source_url: string };
}

// The park's roads and trails as a graph (parkwild/roads.py). An edge is
// [from, to, length_m, kind (0 road, 1 trail), oneway (0/1), name_index, coords].
export type RoadEdge = [number, number, number, number, number, number, number[][]];
export interface RoadsFile {
  park: string;
  fetched: string;
  attribution: string;
  nodes: number[][];
  edges: RoadEdge[];
  names: string[];
}

// The home page's park index (parkwild/parksindex.py), imported at build time.
export interface ParkHero {
  url: string;
  page: string;
  source_article: string;
  license: string;
  license_url: string;
  artist: string;
}
export interface ParkCard {
  key: string;
  name: string;
  state: string;
  status: "live" | "planned" | "seed";
  bbox?: [number, number, number, number];
  center?: [number, number];
  species: number | null;
  sightings: number | null;
  cells: number | null;
  stops: number | null;
  tour_source: string | null;
  hero: ParkHero | null;
}
// Places (parkwild/places.py): every named trail, site, campground and
// facility with the sightings people recorded within reach (500 m of a point,
// 300 m of a trail), the species, and a count per month. Landmarks with an
// article carry its average monthly readers.
export interface PlaceNear {
  n: number;
  species: number;
  top: [string, number][];
  months: number[];
}
export interface PlaceRec {
  id: string;
  src: "landmark" | "item" | "trail";
  kind: string;
  sub?: string | null;
  name: string;
  lon: number;
  lat: number;
  length_m?: number | null;
  ele_m?: number | null;
  url?: string | null;
  views_pm?: number | null;
  tags?: Record<string, string> | null;
  near: PlaceNear;
}
export interface PlacesFile {
  park: string;
  generated: string;
  point_radius_m: number;
  trail_buffer_m: number;
  attribution: string;
  notes: Record<string, string>;
  places: PlaceRec[];
}

// Typical weather by month at the park's busiest place (parkwild/climate.py):
// ten years of daily weather from the Open-Meteo archive folded into normals.
export interface ClimateMonth {
  tmax: number | null;
  tmin: number | null;
  precip_mm: number;
  snow_cm: number;
  wet_days: number;
}
export interface ClimateFile {
  park: string;
  generated: string;
  lat: number;
  lon: number;
  at: string;
  elevation_m: number | null;
  years: [number, number];
  source: string;
  months: ClimateMonth[];
}

export interface ParksIndex {
  generated: string;
  attribution: string;
  parks: ParkCard[];
  species_index?: { sha256: string; bytes: number } | null;
}

// Where each animal was seen, park by park (parkwild/speciesindex.py): one
// file for every shipped park, fetched on demand. A hotspot is
// [lon, lat, sightings, cell id, H3 resolution]; the centre of a coarsened cell
// is as vague as the cell.
export type SpeciesHotspot = [number, number, number, string, number];
export interface SpeciesParkStat {
  s: number;
  hv: number;
  mp: number;
  x: "exclude" | "coarsen" | null;
  cells: number;
  top: SpeciesHotspot[];
}
export interface SpeciesAcrossParks {
  n: string;
  c: string | null;
  k: string | null;
  other: string[];
  total: number;
  parks: Record<string, SpeciesParkStat>;
}
export interface SpeciesIndexFile {
  generated: string;
  parks: Record<string, { name: string; state: string | null }>;
  top_cells: number;
  species: SpeciesAcrossParks[];
  notes: Record<string, string>;
}

// The roadside camera pass (Track B) per park: where it ran, what it found,
// how well it did (parkwild/trackb_export.py). Numbers, never thumbnails.
export interface CameraPassBand {
  band: string;
  n: number;
  tp: number;
  precision: number | null;
  ci: [number, number] | null;
}
export interface CameraPassPrecision {
  reviewer: string;
  population: string;
  n: number;
  tp: number;
  precision: number | null;
  ci: [number, number] | null;
  bands: CameraPassBand[];
}
export interface CameraPassCorridor {
  key: string;
  name: string;
  bbox: [number, number, number, number];
  status: "reviewed" | "unreviewed" | "planned";
  images_indexed: number;
  frames_scored: number;
  frames_with_animal: number;
  sightings: number;
  named: number;
  unnamed: number;
  species_named: Record<string, number>;
  imagery_years: [number, number] | null;
  imagery_months: number[];
  contributors: number;
  precision: CameraPassPrecision | null;
}
export interface CameraPassFile {
  park: string;
  generated: string;
  model: string;
  thresholds: { detection_min_conf: number; species_min_score: number; range_m: number };
  corridors: CameraPassCorridor[];
  notes: Record<string, string>;
}

// Things to do around a place (parkwild/amenities.py): OSM items by kind, and
// named trails summed from the routing graph.
export type AmenityKind = "feature" | "trailhead" | "viewpoint" | "picnic" | "info" | "boat" | "camp" | "stay";
export interface AmenityItem {
  id: string;
  kind: AmenityKind;
  sub: string;
  name: string;
  named: boolean;
  lon: number;
  lat: number;
  tags: Record<string, string>;
}
export interface TrailItem {
  id: string;
  kind: "trail";
  name: string;
  length_m: number;
  pieces: number;
  lon: number;
  lat: number;
}
export interface AmenitiesFile {
  park: string;
  fetched: string;
  attribution: string;
  kinds: string[];
  items: AmenityItem[];
  trails: TrailItem[];
}
