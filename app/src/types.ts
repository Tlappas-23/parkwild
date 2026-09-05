// Shapes of the static files the pipeline bakes (parkwild/export.py). The app
// depends on these, never on the pipeline or the database.

export type ConfidenceBasis = "human_verified" | "model_predicted";

export interface CellProps {
  cell: string;
  species: string;
  common_name: string | null;
  class: string | null;
  res: number;
  coarsened: boolean;
  count: number;
  human_verified: number;
  model_predicted: number;
  first: string | null;
  last: string | null;
  months: number[];
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
  suppressed: { excluded: Record<string, number>; coarsened: Record<string, number> };
}

export interface Species {
  scientific_name: string;
  common_name: string | null;
  class: string | null;
  taxon_id: string | null;
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
