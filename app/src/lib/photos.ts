// Photo URL assembly and a normalised photo shape shared by cards, heroes,
// galleries, the cell strip and the tour. URLs are rebuilt from id +
// extension + host so the data files stay small; iNaturalist's CDN serves
// square/small/medium/large.
import type { CellPhotoEntry, PhotoSize, PhotosCellsFile, PhotosSpeciesFile, SpeciesPhoto } from "../data/types";

export interface Photo {
  id: number;
  observer: string;
  license: string;
  observationId: number;
  date: string | null;
  species: string | null;
  cell: string | null; // the H3 cell it was taken in, when its coordinates are open
  url: (size: PhotoSize) => string;
  observationUrl: string;
}

function make(
  hosts: string[],
  id: number,
  ext: string,
  host: number,
  observer: string,
  license: string,
  obs: number,
  date: string | null,
  species: string | null,
  cell: string | null,
): Photo {
  return {
    id,
    observer,
    license,
    observationId: obs,
    date,
    species,
    cell,
    url: (size) => `${hosts[host] ?? hosts[0]}${id}/${size}.${ext}`,
    observationUrl: `https://www.inaturalist.org/observations/${obs}`,
  };
}

export function speciesPhotos(file: PhotosSpeciesFile | null, species: string): Photo[] {
  if (!file) return [];
  return (file.species[species] ?? []).map((p: SpeciesPhoto) =>
    make(file.photo_hosts, p.i, p.e, p.h, p.o, p.l, p.obs, p.d, species, p.c),
  );
}

export function cellPhotos(file: PhotosCellsFile | null, cell: string): Photo[] {
  if (!file) return [];
  return (file.cells[cell] ?? []).map((e: CellPhotoEntry) =>
    make(file.photo_hosts, e[1], e[2], e[3], e[4], e[5], e[6], e[7], file.species_index[e[0]] ?? null, cell),
  );
}
