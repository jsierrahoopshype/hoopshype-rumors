# Living hub test harness

Two Node scripts that run `hub-generator.html` directly, with no browser and no
network. Both are plain Node: no npm install, no dependencies outside Node's own
built-ins, no workflow files.

Every fixture in here is invented. No archive record, quote, reporter, outlet or
URL in this directory comes from the HoopsHype rumors archive, and nothing in
here reads it.

## Running

From the repository root:

    node tests/living-hub/regression.js
    node tests/living-hub/demos.js

Both print one line per check and exit non-zero if anything fails.

Options, on either script:

    node tests/living-hub/regression.js --baseline=main     # the ref to compare against (default: main)
    node tests/living-hub/regression.js --hub=/path/to/hub-generator.html
    node tests/living-hub/demos.js --hub=/path/to/hub-generator.html

`HUB_FILE=/path/to/hub-generator.html` does the same as `--hub=`.

The demos exercise Living hub v6 behavior, so they need a v6 generator. On a
branch that does not carry one they say so and exit 2 instead of failing every
demo; point `--hub=` at a v6 copy, or run them on the `living-hub-v6` branch.

## regression.js

Proves the Hub and Explainer paths did not move. It loads a baseline copy of
`hub-generator.html` (read out of git, `main` by default) and the working-tree
copy, and checks:

1. **Shared JavaScript is byte-identical.** Everything in the `<script>` above
   the LIVING HUB banner: config, helpers, the archive fetch, the Content Stream
   renderer, the Hub and Explainer prompts, `generate()`, `checkCount()`,
   `suggestQuestions()` and the wiring.
2. **Markup is additive only.** Every line of the baseline's markup still
   appears, in order. The Living hub may add fields and table columns; it may
   not change or delete anything that was there.
3. **No element id was removed or renamed.**
4. **Hub mode** produces an identical relay request and identical output HTML.
5. **Explainer mode** produces an identical relay request and identical output.
6. **Check count** makes the same archive request and writes the same message.
7. **Suggest questions** sends the same request and fills the same list.
8. **Content Stream mentions** fetch the same files and render the same HTML.

Checks 4 to 8 run the real functions in both copies against the same fake
fixtures, with `fetch` stubbed, and diff the result byte for byte, reporting the
first differing byte when they disagree.

## demos.js

One demo per numbered change in the v6 brief, each printing the evidence it
checked:

- **1a-1e** the sensitive gate: 2 of 18 entries excluded and generation
  proceeding; the three conditions that still block the whole tag (>= 30%, >= 4
  entries, fewer than 2 left); the override checkbox.
- **2a-2c** storyline dedupe on the entity set: the same two entities in a
  different order and a different case collapse; the row with more entries is
  kept and the thinner earlier row is demoted; one shared entity is not enough.
- **3a-3c** claim mechanics: a quote running across three sentences stays one
  sentence and maps to one claim; `Durant 's` is normalized; an
  editor-tightened sentence still maps to its claim at 80% overlap.
- **4a-4c** self-referential and padding sentences, an undated "What comes next"
  section, and an off-storyline claim.
- **5a-5c** aggregator accounts and generic links: the payload the writer gets,
  the lint when the account is named, and a `/social/` URL that is not linked.
- **6a-6b** content stream polish: the five-word minimum counting only tokens
  with a letter, and `‼` and friends stripped from a title.
- **7a-7b** relay diagnostics: stop reason and token usage per call, and the
  lint for a writer call capped below the requested 12000.
- **8** the batch row: the sensitive-exclusion note and the new columns.

## env.js and fixtures.js

`env.js` reads the generator, pulls its `<script>` out, and runs it in a Node
`vm` context with a small fake DOM (elements created on demand), a stubbed
`fetch` the test programs, and a stubbed clipboard. The tool's top-level
`const`s and functions are reached through a direct `eval` installed inside the
same script scope, so nothing in `hub-generator.html` has to change to be
testable.

`fixtures.js` holds the fake archive, manifest and content-stream index used by
the regression runs.
