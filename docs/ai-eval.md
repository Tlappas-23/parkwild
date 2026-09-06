# Ask the park: the measured question set

The language model may only write from numbered facts (ADR-0021). This set
is run in a real browser (`window.__parkwildAsk.evaluate()` on the Ask page,
after enabling the model) whenever the prompt, the fact builder or the model
changes, and the table below is replaced, never appended to.

What is measured per question:

- **cited / facts**: how many of the supplied facts the answer cited, and how many were supplied;
- **numbers not in facts**: any number in the answer that appears in no fact (the invention check);
- **says "doesn't say"**: whether the answer declined, which is the right result for questions the data cannot answer;
- **seconds** on the test machine.

## Questions

1. Where are bison seen most?
2. When is the best month to see elk?
3. How many species have been recorded here?
4. Where can I camp near Lamar Valley?
5. What trails are near Old Faithful?
6. Plan a half day from Old Faithful to see bison and elk
7. What animals are seen around Hayden Valley?
8. Which birds are seen more than usual in October?
9. How good is the camera model?
10. Are there wolves on the map? (expected: the data doesn't say / sensitive species are not mapped)
11. What is the tallest peak? (expected: the data doesn't say; peaks are not ranked in the facts)
12. Tell me about Mammoth Hot Springs

## Latest run

**Default model (Qwen2.5-1.5B-Instruct, q4f16): not yet measured.** The
automation browser used for this session refuses to store more than about
300 MB per origin in any of the three backends, so the default could not be
loaded there. The Ask page carries a "Measure it" control that runs this set
and prints the table; the first run on the live site replaces this section.

**Smoke test, SmolLM2-360M-Instruct (q4f16), 2026-09-06, automation profile,
Apple silicon.** Run to exercise the pipeline and the checks, not to judge
the feature; this model is far below the bar and is not offered to visitors.

| # | question | cited / facts | numbers not in facts | declined | s |
|---|---|---|---|---|---|
| 1 | Where are bison seen most? | 1 / 4 | — | | 1 |
| 2 | When is the best month to see elk? | 1 / 6 | — | | 1 |
| 3 | How many species have been recorded here? | 1 / 2 | — | | 0 |
| 4 | Where can I camp near Lamar Valley? | 1 / 5 | — | | 2 |
| 5 | What trails are near Old Faithful? | 2 / 4 | — | | 3 |
| 6 | Plan a half day from Old Faithful… | 2 / 11 | many (degenerate list) | | 7 |
| 7 | What animals are seen around Hayden Valley? | 2 / 4 | — | | 6 |
| 8 | Which birds are seen more than usual in October? | 1 / 3 | — | | 1 |
| 9 | How good is the camera model? | 3 / 4 | 200 | | 2 |
| 10 | Are there wolves on the map? | 2 / 2 | — | yes | 0 |
| 11 | What is the tallest peak? | 1 / 2 | — | no (named Mount Washburn; the facts do not rank peaks) | 0 |
| 12 | Tell me about Mammoth Hot Springs | 2 / 2 | 100 | | 6 |

What the smoke test showed: the fact builder supplies the right facts
(bison, elk, camping near Lamar, trails near Old Faithful, October birds,
the camera pass, a computed plan); the invention check catches numbers the
model made up (a "100-acre" Mammoth, "200" model sightings) but not made-up
words ("Trumpeter SQUARE", "Wolves 10" at Hayden Valley); the 360M model
misreads facts freely. Two follow-ups are recorded in E-041: a name check
alongside the number check, and the default model's own table.
