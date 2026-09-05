// Shapes of the static files the pipeline bakes (parkwild/export.py,
// parkwild/photos.py). The app depends on these, never on the pipeline.

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

export interface SpeciesIndexEntry { n: string; c: string | null; k: string | null; }

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
  model: { url: string; title: string; author: string; license: string; credit: string; source: string } | null;
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
  files: Record<string, { sha256: string; bytes: number }>;
}

export interface BiasFile {
  road: {
    corridor: string; n_sightings_in_bbox: number; n_covered: number; fraction_outside_coverage: number | null;
    by_class: Record<string, { n: number; covered: number; fraction_outside: number | null }>; ring: number; h3_res: number;
  };
  seasonal: {
    images_by_month: number[]; sightings_by_month: number[]; images_summer_share: number | null; sightings_summer_share: number | null;
    months_with_no_imagery: number[];
  };
}

// A photograph: id, extension, host index, observer, licence label, observation id, date, cell (species file only)
export interface SpeciesPhoto { i: number; e: string; h: number; o: string; l: string; obs: number; d: string | null; c: string | null; }
export type CellPhotoEntry = [number, number, string, number, string, string, number, string | null];

export interface PhotosSpeciesFile { park: string; photo_hosts: string[]; species: Record<string, SpeciesPhoto[]>; licence_rule: string; }
export interface PhotosCellsFile { park: string; photo_hosts: string[]; species_index: string[]; cells: Record<string, CellPhotoEntry[]>; licence_rule: string; }

export type PhotoSize = "square" | "small" | "medium" | "large";
