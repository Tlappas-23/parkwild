// "What did I see?": a zero-shot image model ranks a visitor's photograph
// against this park's species names, on the device, as a suggestion. CLIP was
// not trained to tell a Uinta ground squirrel from a golden-mantled one, and
// the card says so; the list is a place to start, never an identification.
import { useStore } from "./store";

// CLIP_MODEL — BORROWED (OpenAI CLIP ViT-B/32 converted for Transformers.js, MIT; about 150 MB, the smallest that is any use)
export const CLIP_MODEL = "Xenova/clip-vit-base-patch32";
// MAX_LABELS — ARBITRARY (text encoding is per label per photo; the park's most-recorded species cover nearly every photo a visitor takes)
export const MAX_LABELS = 160;
// TOP_K — ARBITRARY
export const TOP_K = 5;

type Classifier = (image: string, labels: string[], opts: { hypothesis_template: string; top_k?: number }) => Promise<{ label: string; score: number }[]>;
let pipe: Classifier | null = null;
let loading: Promise<Classifier> | null = null;
export function classifierReady(): boolean { return pipe !== null; }

export function loadClassifier(onProgress: (text: string, pct: number) => void): Promise<Classifier> {
  if (pipe) return Promise.resolve(pipe);
  if (!loading) {
    loading = import("@huggingface/transformers").then(async (tf) => {
      // The onnx runtime's wasm ships with the app (scripts/copy-ort.mjs); the
      // model weights come from Hugging Face once and are cached by the browser.
      tf.env.allowLocalModels = false;
      tf.env.backends.onnx.wasm!.wasmPaths = `${import.meta.env.BASE_URL}ort/`;
      const device = "gpu" in navigator ? "webgpu" : "wasm";
      const p = await tf.pipeline("zero-shot-image-classification", CLIP_MODEL, {
        device,
        progress_callback: (ev: { status?: string; progress?: number; file?: string }) => onProgress(`${ev.status ?? ""} ${ev.file ?? ""}`.trim(), (ev.progress ?? 0) / 100),
      });
      pipe = p as unknown as Classifier;
      return pipe;
    }).catch((err) => { loading = null; throw err; });
  }
  return loading;
}

export interface Suggestion { species: string; common: string; score: number; }

export async function suggestSpecies(file: Blob): Promise<Suggestion[]> {
  const st = useStore.getState();
  const list = (st.species?.species ?? []).filter((s) => s.common_name && s.suppression?.action !== "exclude").slice(0, MAX_LABELS);
  const labels = list.map((s) => s.common_name as string);
  const p = await loadClassifier(() => undefined);
  const url = URL.createObjectURL(file);
  try {
    const out = await p(url, labels, { hypothesis_template: "a photo of a {}, a wild animal", top_k: TOP_K });
    return out.map((o) => ({ species: list.find((s) => s.common_name === o.label)?.scientific_name ?? o.label, common: o.label, score: o.score }));
  } finally {
    URL.revokeObjectURL(url);
  }
}
