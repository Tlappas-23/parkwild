// Shapes of the static files the pipeline bakes (parkwild/export.py). The app
// depends on these, never on the pipeline or the database.

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
  n: string;             // scientific name
  c: string | null;      // common name
  k: string | null;      // class
}

export interface CellFeature {
  type: "Feature";
  geometry: { type: "Polygon"; coordinates: number[][][] };
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
  suppression: { action: "exclude" | "coarsen"; res: number | null; why: string } | null;
  sightings: number;
  open_coordinates: number;
  obscured_coordinates: number;
  sources: { inaturalist: number; gbif: number; mapillary_cv: number };
  confidence_basis: { human_verified: number; model_predicted: number };
  first: string | null;
  last: string | null;
  months: number[];
  model: string | null;
}

export interface SpeciesFile {
  park: string;
  generated: string;
  species: Species[];
  notes: { recall: string; obscured: string };
}

export interface Manifest {
  built: string;
  git_commit: string | null;
  park: string;
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
