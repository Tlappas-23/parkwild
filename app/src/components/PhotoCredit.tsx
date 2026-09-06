import type { Photo } from "../lib/photos";

// Every displayed photograph carries its observer, its licence and a link to
// the observation. This is the whole of the attribution obligation, and it is
// never optional.
export default function PhotoCredit({ photo, compact = false }: { photo: Photo; compact?: boolean }) {
  return (
    <span className={"credit" + (compact ? " compact" : "")}>
      © {photo.observer} · {photo.license} ·{" "}
      <a href={photo.observationUrl} target="_blank" rel="noreferrer">
        iNaturalist
      </a>
    </span>
  );
}
