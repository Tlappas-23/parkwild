import { ChevronDown, ChevronUp, RotateCcw, RotateCw } from "lucide-react";
import { useStore } from "../store/index";

// The map's own furniture: rotate and tilt buttons for everyone who never
// finds right-drag, and the legend that explains the cells.
export default function MapChrome({
  turn,
  tilt,
  hasModelCells,
}: {
  turn: (deg: number) => void;
  tilt: (deg: number) => void;
  hasModelCells: boolean;
}) {
  const { cameraPass, showCameraPass, setPage } = useStore();
  return (
    <>
      <div className="cam-ctrl" role="group" aria-label="Rotate and tilt">
        <button
          className="icon-btn"
          onClick={() => turn(-45)}
          aria-label="Rotate left"
          title="Rotate left (or right-drag the map)"
        >
          <RotateCcw className="ico" aria-hidden="true" />
        </button>
        <button className="icon-btn" onClick={() => turn(45)} aria-label="Rotate right" title="Rotate right">
          <RotateCw className="ico" aria-hidden="true" />
        </button>
        <button className="icon-btn" onClick={() => tilt(-15)} aria-label="Tilt down" title="Look from higher up">
          <ChevronUp className="ico" aria-hidden="true" />
        </button>
        <button className="icon-btn" onClick={() => tilt(15)} aria-label="Tilt up" title="Look from lower down">
          <ChevronDown className="ico" aria-hidden="true" />
        </button>
      </div>

      <div className="legend" aria-label="Legend">
        <span>
          <i className="swatch human" /> people saw it
        </span>
        {hasModelCells && (
          <span>
            <i className="swatch model" /> roadside camera pass{" "}
            <button className="link small" onClick={showCameraPass}>
              what's that?
            </button>
          </span>
        )}
        <span>
          <i className="dot stop" /> tour stop
        </span>
        <span>
          <i className="dot" /> landmark
        </span>
        {cameraPass && cameraPass.corridors.length > 0 && (
          <span>
            <i className="swatch pass" /> camera pass area
          </span>
        )}
        <span className="muted">
          Cells ~170 m; larger for sensitive species. Empty means nobody looked. Rotate with the arrows, a right-drag or
          two fingers.{" "}
          <button className="link small" onClick={() => setPage("about")}>
            About the data
          </button>
        </span>
      </div>
    </>
  );
}
