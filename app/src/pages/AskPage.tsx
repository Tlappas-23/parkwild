import { useEffect, useRef, useState } from "react";
import { Camera, Sparkles } from "lucide-react";
import {
  ask,
  engineReady,
  evaluate,
  EVAL_QUESTIONS,
  loadEngine,
  MODEL_ID,
  webgpuAvailable,
  type Answer,
} from "../lib/ai";
import { CLIP_MODEL, classifierReady, loadClassifier, suggestSpecies, type Suggestion } from "../lib/photoId";
import { useStore } from "../store/index";

// Ask the park, and What did I see: two models that run on the visitor's
// device after they choose to download them. Every answer cites the facts it
// used and says when the data does not cover a question; every photo
// suggestion is labelled a suggestion. Nothing is sent anywhere (ADR-0021).
const SUGGESTED = [
  "Where are bison seen most?",
  "When is the best month to see elk?",
  "Where can I camp near Lamar Valley?",
  "Plan a half day from Old Faithful to see bison and elk",
  "Which birds are seen more than usual in October?",
  "How good is the camera model?",
];

export default function AskPage() {
  const { parkName, selectSpecies, setSpeciesFilter, setPage } = useStore();
  const [gpu] = useState(webgpuAvailable());
  const [llm, setLlm] = useState<{ state: "idle" | "loading" | "ready" | "error"; text: string; pct: number }>({
    state: engineReady() ? "ready" : "idle",
    text: "",
    pct: 0,
  });
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [partial, setPartial] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [clip, setClip] = useState<{ state: "idle" | "loading" | "ready" | "error"; text: string; pct: number }>({
    state: classifierReady() ? "ready" : "idle",
    text: "",
    pct: 0,
  });
  const [photo, setPhoto] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<Suggestion[] | null>(null);
  const [photoBusy, setPhotoBusy] = useState(false);
  const [evalRows, setEvalRows] = useState<Awaited<ReturnType<typeof evaluate>> | null>(null);
  const [evalBusy, setEvalBusy] = useState(false);
  // Storage refusals and network failures read as one plain sentence.
  const friendly = (e: unknown) => {
    const m = String((e as Error)?.message ?? e);
    if (/quota|failed to fetch|IndexedDB|opfs/i.test(m))
      return "This browser would not download or store the model (about 1 GB). Free some site storage, or try Chrome, Edge or Safari 18 on a device with more room.";
    return m;
  };
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(
    () => () => {
      if (photo) URL.revokeObjectURL(photo);
    },
    [photo],
  );

  const enable = async () => {
    setLlm({ state: "loading", text: "Starting…", pct: 0 });
    try {
      await loadEngine((text, pct) => setLlm({ state: "loading", text, pct }));
      setLlm({ state: "ready", text: "", pct: 1 });
    } catch (e) {
      setLlm({ state: "error", text: friendly(e), pct: 0 });
    }
  };
  const submit = async (question: string) => {
    if (!question.trim() || busy) return;
    setBusy(true);
    setAnswer(null);
    setPartial("");
    try {
      setAnswer(await ask(question.trim(), setPartial));
    } catch (e) {
      setAnswer({
        text: `Could not answer: ${(e as Error).message}`,
        facts: [],
        cited: [],
        uncited_numbers: [],
        ms: 0,
        grounding: { facts: [], species: [], places: [], intents: [], month: null },
      });
    } finally {
      setBusy(false);
    }
  };
  const onPhoto = async (file: File | undefined) => {
    if (!file) return;
    if (photo) URL.revokeObjectURL(photo);
    setPhoto(URL.createObjectURL(file));
    setSuggestions(null);
    setPhotoBusy(true);
    try {
      if (!classifierReady()) {
        setClip({ state: "loading", text: "Downloading the image model…", pct: 0 });
        await loadClassifier((text, pct) => setClip({ state: "loading", text, pct }));
        setClip({ state: "ready", text: "", pct: 1 });
      }
      setSuggestions(await suggestSpecies(file));
    } catch (e) {
      setClip({ state: "error", text: friendly(e), pct: 0 });
    } finally {
      setPhotoBusy(false);
    }
  };
  // Citation markers become small links to the fact list below the answer.
  const rendered = (text: string) =>
    text.split(/(\[\d+\])/g).map((part, i) => {
      const m = part.match(/^\[(\d+)\]$/);
      return m ? (
        <a key={i} className="cite" href={`#fact-${m[1]}`}>
          {m[1]}
        </a>
      ) : (
        <span key={i}>{part}</span>
      );
    });

  return (
    <div className="page ask">
      <div className="page-head">
        <div>
          <div className="eyebrow">On your device</div>
          <h1>Ask {parkName.replace(/ National Park$/, "")}</h1>
          <p className="muted">
            Questions answered from this site's own data by a small language model that runs in your browser. Every
            claim cites its fact; when the data doesn't say, it says so. Nothing you type leaves your device.
          </p>
        </div>
      </div>

      <section className="ask-card">
        {!gpu ? (
          <p className="muted">
            This needs WebGPU, which this browser does not offer. Chrome, Edge and Safari 18 on a recent device have it.
          </p>
        ) : llm.state !== "ready" ? (
          <div className="enable">
            <p>
              <strong>Enable Ask.</strong> Downloads the model once, about 1 GB, into this browser's cache. It runs on
              your graphics chip; nothing is sent anywhere.
            </p>
            {llm.state === "loading" ? (
              <div
                className="progress"
                role="progressbar"
                aria-valuenow={Math.round(llm.pct * 100)}
                aria-valuemin={0}
                aria-valuemax={100}
              >
                <div style={{ width: `${Math.round(llm.pct * 100)}%` }} />
                <span className="muted small">{llm.text}</span>
              </div>
            ) : (
              <button className="primary" onClick={() => void enable()}>
                <Sparkles className="ico" aria-hidden="true" /> Enable Ask
              </button>
            )}
            {llm.state === "error" && <p className="error small">{llm.text}</p>}
            <p className="muted small">
              Model: {MODEL_ID.replace(/-MLC$/, "")} (Apache-2.0), run with WebLLM. Slow on older phones.
            </p>
          </div>
        ) : (
          <>
            <form
              className="ask-form"
              onSubmit={(e) => {
                e.preventDefault();
                void submit(q);
              }}
            >
              <input
                type="search"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder={`Ask about ${parkName.replace(/ National Park$/, "")}…`}
                aria-label="Your question"
                autoComplete="off"
              />
              <button className="primary" type="submit" disabled={busy || !q.trim()}>
                {busy ? "Thinking…" : "Ask"}
              </button>
            </form>
            <div className="chips">
              {SUGGESTED.map((s) => (
                <button
                  key={s}
                  className="ghost small-btn"
                  onClick={() => {
                    setQ(s);
                    void submit(s);
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
            {(busy || answer) && (
              <div className="answer" aria-live="polite">
                <p className="answer-text">
                  {rendered(answer?.text ?? partial)}
                  {busy && (
                    <span className="caret" aria-hidden="true">
                      ▍
                    </span>
                  )}
                </p>
                {answer && (
                  <>
                    {answer.grounding.species.length > 0 && (
                      <div className="chips">
                        {answer.grounding.species.map((s) => (
                          <span key={s.scientific_name}>
                            <button className="ghost small-btn" onClick={() => selectSpecies(s.scientific_name)}>
                              {s.common_name ?? s.scientific_name}
                            </button>{" "}
                            <button
                              className="ghost small-btn"
                              onClick={() => {
                                setSpeciesFilter(s.scientific_name);
                                setPage("map");
                              }}
                            >
                              on the map
                            </button>
                          </span>
                        ))}
                      </div>
                    )}
                    <details className="facts-used">
                      <summary>
                        {answer.cited.length} of {answer.facts.length} facts cited · {(answer.ms / 1000).toFixed(1)} s
                        on this device
                        {answer.uncited_numbers.length
                          ? ` · numbers not in the facts: ${answer.uncited_numbers.join(", ")}`
                          : ""}
                      </summary>
                      <ol className="fact-list">
                        {answer.facts.map((f) => (
                          <li key={f.n} id={`fact-${f.n}`} className={answer.cited.includes(f.n) ? "cited" : ""}>
                            {f.href ? (
                              <>
                                <a
                                  href={f.href}
                                  onClick={(e) => {
                                    if (f.href?.startsWith("#species/")) {
                                      e.preventDefault();
                                      selectSpecies(f.href.slice(9));
                                    } else if (f.href?.startsWith("#map/")) {
                                      e.preventDefault();
                                      setSpeciesFilter(f.href.slice(5));
                                      setPage("map");
                                    }
                                  }}
                                >
                                  {f.label ?? "source"}
                                </a>
                                {" · "}
                              </>
                            ) : null}
                            {f.text}
                          </li>
                        ))}
                      </ol>
                    </details>
                    <p className="muted small">
                      Written on your device from the facts above. It can still misread them; the facts are the record.
                    </p>
                  </>
                )}
              </div>
            )}
            {/* The measured question set, runnable by anyone: the same table the repository records. */}
            <details className="measure">
              <summary>Measure it: run the {EVAL_QUESTIONS.length} fixed questions</summary>
              <p className="muted small">
                Each answer is checked for how many facts it cited, any number that appears in no fact, and whether it
                declined when it should. Takes a minute or two on this device.
              </p>
              <button
                className="ghost small-btn"
                disabled={evalBusy}
                onClick={async () => {
                  setEvalBusy(true);
                  try {
                    setEvalRows(await evaluate());
                  } finally {
                    setEvalBusy(false);
                  }
                }}
              >
                {evalBusy ? "Running…" : "Run the set"}
              </button>
              {evalRows && (
                <div className="table-wrap">
                  <table className="pass">
                    <thead>
                      <tr>
                        <th>Question</th>
                        <th>Cited / facts</th>
                        <th>Numbers not in facts</th>
                        <th>Declined</th>
                        <th>Seconds</th>
                      </tr>
                    </thead>
                    <tbody>
                      {evalRows.map((r) => (
                        <tr key={r.question}>
                          <td>{r.question}</td>
                          <td>
                            {r.cited} / {r.facts}
                          </td>
                          <td>{r.uncited_numbers.join(", ") || "—"}</td>
                          <td>{r.says_no_data ? "yes" : ""}</td>
                          <td>{(r.ms / 1000).toFixed(1)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p className="muted small">
                    Model {MODEL_ID.replace(/-MLC$/, "")}. Copy this table into docs/ai-eval.md when the prompt or the
                    facts change.
                  </p>
                </div>
              )}
            </details>
          </>
        )}
      </section>

      <section className="ask-card">
        <h2>
          <Camera className="ico" aria-hidden="true" /> What did I see?
        </h2>
        <p className="muted">
          Pick a photo and an image model ranks it against this park's {"most-recorded"} species, on your device. It is
          a suggestion to start from, not an identification: the model was not trained on wildlife and confuses
          look-alikes.
        </p>
        <div className="photo-row">
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            capture="environment"
            hidden
            onChange={(e) => void onPhoto(e.target.files?.[0])}
          />
          <button className="primary" onClick={() => fileRef.current?.click()} disabled={photoBusy}>
            <Camera className="ico" aria-hidden="true" /> {photo ? "Another photo" : "Choose a photo"}
          </button>
          {clip.state === "loading" && (
            <div
              className="progress"
              role="progressbar"
              aria-valuenow={Math.round(clip.pct * 100)}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div style={{ width: `${Math.round(clip.pct * 100)}%` }} />
              <span className="muted small">{clip.text || "Downloading the image model (about 150 MB, once)…"}</span>
            </div>
          )}
          {clip.state === "error" && <p className="error small">{clip.text}</p>}
        </div>
        {photo && (
          <div className="photo-result">
            <img src={photo} alt="Your photo" />
            <div>
              {photoBusy && clip.state !== "loading" ? (
                <p className="muted small">Looking…</p>
              ) : suggestions ? (
                <ul className="suggest-list">
                  {suggestions.map((s) => (
                    <li key={s.species}>
                      <button className="link" onClick={() => selectSpecies(s.species)}>
                        {s.common}
                      </button>
                      <div className="bar-track">
                        <div className="bar-fill" style={{ width: `${Math.round(100 * s.score)}%` }} />
                      </div>
                      <span className="muted small">{Math.round(100 * s.score)}%</span>
                    </li>
                  ))}
                </ul>
              ) : null}
              {suggestions && (
                <p className="muted small">
                  Suggestions only. Model: {CLIP_MODEL} via Transformers.js. Photos stay on your device.
                </p>
              )}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
