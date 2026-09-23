"use strict";
// Living hub v6 demos. Every one of them runs the tool's own functions against
// invented data and prints what came back, so each numbered change in the v6
// brief can be checked by reading the output.
//
// There is no real archive data here: every player, team, reporter, outlet,
// quote and URL below is made up.

const { loadGenerator, relayReply } = require("./env.js");

const results = [];
function demo(title, fn) {
  return Promise.resolve()
    .then(fn)
    .then(out => results.push({ title, ok: !!out.ok, lines: out.lines || [] }))
    .catch(e => results.push({ title, ok: false, lines: [`threw: ${e && e.message}`] }));
}

const HUB_ARG = (process.argv.slice(2).find(a => a.startsWith("--hub=")) || "").split("=").slice(1).join("=");
function g() { return loadGenerator(HUB_ARG ? { file: HUB_ARG } : {}); }

// --- fake archive records -------------------------------------------------
function entry(over) {
  return Object.assign({
    archive_date: "2999-01-05", outlet: "Fake Wire", reporter: "Fake Reporter",
    source_url: "https://example.com/story/1", tags: ["Fake Player"],
    text: "Fake Player and the Example Owls are talking about an extension.",
    quote: "",
  }, over || {});
}

// 18 records: 16 ordinary, 2 that the sensitive terms match.
function eighteen() {
  const list = [];
  for (let i = 0; i < 16; i++) {
    list.push(entry({
      source_url: `https://example.com/story/${i}`,
      text: `Fake Player and the Example Owls kept talking on day ${i + 1}, with an offer worth nearly 60 million dollars still on the table.`,
    }));
  }
  list.push(entry({
    source_url: "https://example.com/story/16",
    text: "A lawsuit filed in county court names Fake Player as a defendant.",
  }));
  list.push(entry({
    source_url: "https://example.com/story/17",
    text: "Fake Player was arrested on Jan. 2 according to a police report.",
  }));
  return list;
}

// A writer reply shaped like the real one.
function draft(over) {
  return Object.assign({
    headline: "Fake Player extension talks: latest updates",
    meta_description: "Fake Player and the Example Owls are talking about an extension worth nearly 60 million dollars.",
    body_html: "<p>Fake Player and the Example Owls kept talking on day 1, with an offer worth nearly 60 million dollars still on the table.</p>",
    detected_storyline: "fake player extension talks",
    storyline_entities: ["Fake Player", "Example Owls"],
    claims: [{
      sentence_start: "Fake Player and the Example Owls kept talking",
      entry_index: 0,
      source_quote: "kept talking on day 1",
    }],
    headline_claims: [{ sentence_start: "Fake Player extension talks: latest updates", entry_index: 0, source_quote: "kept talking on day 1" }],
    meta_claims: [{ sentence_start: "Fake Player and the Example Owls are talking", entry_index: 0, source_quote: "kept talking on day 1" }],
    context_sentences: [],
  }, over || {});
}

function editorOf(d) {
  return { headline: d.headline, meta_description: d.meta_description, body_html: d.body_html };
}

// Run the whole pipeline with the relay stubbed out.
async function run(gen, opts) {
  const o = opts || {};
  const writer = o.writer || draft();
  const editor = o.editor || editorOf(writer);
  gen.relayReplies([
    relayReply(writer, o.writerMeta || {}),
    relayReply(editor, o.editorMeta || {}),
  ]);
  return gen.pick("lhRunPipeline")(
    o.tag || "Fake Player", o.focus || "", o.matched || [],
    () => {}, Object.assign({ aggregators: [] }, o.options || {})
  );
}

const warn = (r, re) => (r.lint.warnings || []).filter(w => re.test(w));

// The demos exercise v6 behavior, so they need a v6 generator. On a branch that
// does not carry one, say so instead of failing twenty times over.
function requireV6() {
  const gen = g();
  const missing = ["lhSensitiveDecision", "lhDuplicateRun", "lhOpeningOverlap", "lhParseAggregators", "lhRelayCapWarning"]
    .filter(n => { try { return typeof gen.pick(n) !== "function"; } catch (e) { return true; } });
  if (!missing.length) return true;
  console.log(`The generator at ${gen.file} is not the Living hub v6 build.`);
  console.log(`Missing: ${missing.join(", ")}`);
  console.log("");
  console.log("Run the demos against a v6 generator, either by checking out the");
  console.log("living-hub-v6 branch, or with:");
  console.log("  node tests/living-hub/demos.js --hub=/path/to/hub-generator.html");
  return false;
}

// ===========================================================================
async function main() {
if (!requireV6()) { process.exitCode = 2; return; }

// --- 1. sensitive gate excludes instead of blocking ------------------------
await demo("1a. 2 sensitive entries out of 18 are excluded and generation proceeds", async () => {
  const gen = g();
  const r = await run(gen, { matched: eighteen() });
  const sentEntries = (gen.calls.find(c => String(c.url).includes("relay")).init.body || "");
  return {
    ok: r.status !== "sensitive" && r.sensitiveExcluded === 2 && r.entriesUsed === 16
      && !!r.body && !/lawsuit|arrested/i.test(sentEntries),
    lines: [
      `status: ${r.status}, entries used: ${r.entriesUsed} of 18`,
      `note: ${r.sensitiveNote}`,
      `body produced: ${r.body ? "yes" : "no"}, ${r.words} words`,
      `"lawsuit"/"arrested" present in the writer request: ${/lawsuit|arrested/i.test(sentEntries)}`,
    ],
  };
});

await demo("1b. block when matched entries are >= 30% of the tag", async () => {
  const gen = g();
  const matched = eighteen().slice(0, 4).concat(eighteen().slice(16)); // 4 clean + 2 sensitive
  const r = await run(gen, { matched });
  return {
    ok: r.status === "sensitive" && gen.calls.every(c => !String(c.url).includes("relay")),
    lines: [`status: ${r.status}`, `note: ${r.note}`, `relay calls: ${gen.calls.filter(c => String(c.url).includes("relay")).length}`],
  };
});

await demo("1c. block when 4 or more entries match, even below 30%", async () => {
  const gen = g();
  const clean = [];
  for (let i = 0; i < 20; i++) clean.push(entry({ source_url: `https://example.com/c/${i}`, text: `Ordinary talk number ${i} about Fake Player and the Example Owls.` }));
  const sensitive = ["a lawsuit", "an arrest", "a police report", "an investigation"].map((t, i) =>
    entry({ source_url: `https://example.com/s/${i}`, text: `Reports mention ${t} involving Fake Player.` }));
  const r = await run(gen, { matched: clean.concat(sensitive) });
  return {
    ok: r.status === "sensitive",
    lines: [`24 entries, 4 sensitive (16.7%)`, `status: ${r.status}`, `note: ${r.note}`],
  };
});

await demo("1d. block when fewer than 2 entries would survive the exclusion", async () => {
  const gen = g();
  const matched = [
    entry({ text: "Fake Player and the Example Owls are talking about an extension." }),
    entry({ source_url: "https://example.com/story/2", text: "A lawsuit names Fake Player." }),
    entry({ source_url: "https://example.com/story/3", text: "Fake Player was arrested on Jan. 2." }),
  ];
  const r = await run(gen, { matched });
  const decision = gen.pick("lhSensitiveDecision")(gen.pick("lhBuildEntries")(matched, []));
  return {
    ok: r.status === "sensitive" && decision.kept.length < 2,
    lines: [`entries left after exclusion: ${decision.kept.length} (minimum 2)`,
            `status: ${r.status}`, `note: ${r.note}`,
            "(the share rule fires first on a set this small; the remaining-count rule is the backstop)"],
  };
});

await demo("1e. the override checkbox still bypasses the gate", async () => {
  const gen = g();
  const matched = eighteen().slice(0, 4).concat(eighteen().slice(16));
  const r = await run(gen, { matched, options: { sensitiveOverride: true } });
  return { ok: r.status !== "sensitive" && r.entriesUsed === 6, lines: [`status: ${r.status}, entries used: ${r.entriesUsed}`] };
});

// --- 2. dedupe by entity set ----------------------------------------------
await demo("2a. same entity set in a different order is a duplicate", async () => {
  const gen = g();
  const prior = [{ tag: "Hornets", entities: ["Fake Hornets", "Fake Hawks"], entriesUsed: 9, status: "ok" }];
  const r = await run(gen, {
    tag: "Hawks",
    matched: [entry(), entry({ source_url: "https://example.com/story/2" })],
    writer: draft({ storyline_entities: ["fake hawks", "FAKE HORNETS"] }),
    options: { priorRuns: prior },
  });
  return {
    ok: r.status === "duplicate" && r.duplicateOf === "Hornets",
    lines: [`this run: ${r.entriesUsed} entries, entities ${JSON.stringify(r.entities)}`,
            `prior run "Hornets": 9 entries, entities ["Fake Hornets","Fake Hawks"]`,
            `status: ${r.status}`, `note: ${r.note}`],
  };
});

await demo("2b. the row with more entries is the one kept", async () => {
  const gen = g();
  const prior = { tag: "Hornets", entities: ["Fake Hornets", "Fake Hawks"], entriesUsed: 2, status: "ok", note: "" };
  const matched = [];
  for (let i = 0; i < 9; i++) matched.push(entry({ source_url: `https://example.com/d/${i}` }));
  const r = await run(gen, {
    tag: "Hawks", matched,
    writer: draft({ storyline_entities: ["Fake Hawks", "Fake Hornets"] }),
    options: { priorRuns: [prior] },
  });
  return {
    ok: r.status !== "duplicate" && prior.status === "duplicate" && prior.duplicateOf === "Hawks",
    lines: [`later run "Hawks": ${r.entriesUsed} entries, status ${r.status}`,
            `earlier run "Hornets": 2 entries, status ${prior.status}`,
            `earlier run note: ${prior.note}`],
  };
});

await demo("2c. one shared entity is not enough", async () => {
  const gen = g();
  const prior = [{ tag: "Hornets", entities: ["Fake Hornets", "Fake Guard"], entriesUsed: 9, status: "ok" }];
  const r = await run(gen, {
    tag: "Hawks", matched: [entry(), entry({ source_url: "https://example.com/story/2" })],
    writer: draft({ storyline_entities: ["Fake Hawks", "Fake Hornets"] }),
    options: { priorRuns: prior },
  });
  return { ok: r.status !== "duplicate", lines: [`shared entities: 1 (Fake Hornets)`, `status: ${r.status}`] };
});

// --- 3. claim lint mechanics ----------------------------------------------
await demo("3a. a quote running across 3 sentences stays one sentence and maps to one claim", async () => {
  const gen = g();
  const body = '<p>Fake Reporter said the talks are live. Fake Player said: "I like it here. The city is great. I want to stay." The Example Owls have not answered.</p>';
  const sentences = gen.pick("lhSentences")(body);
  const matched = [entry({ text: 'Fake Player said: "I like it here. The city is great. I want to stay."' })];
  const warnings = gen.pick("lhVerifyClaims")(
    {
      claims: [
        { sentence_start: "Fake Reporter said the talks are live", entry_index: 0, source_quote: "I like it here" },
        { sentence_start: 'Fake Player said: "I like it here', entry_index: 0, source_quote: "I like it here" },
        { sentence_start: "The Example Owls have not answered", entry_index: 0, source_quote: "I like it here" },
      ],
      headline_claims: [{ sentence_start: "h", entry_index: 0, source_quote: "I like it here" }],
      meta_claims: [{ sentence_start: "m", entry_index: 0, source_quote: "I like it here" }],
      context_sentences: [], storyline_entities: ["Fake Player"],
    },
    gen.pick("lhBuildEntries")(matched, []), body, false
  );
  return {
    ok: sentences.length === 3 && warnings.length === 0,
    lines: [`sentences: ${sentences.length}`, ...sentences.map(s => `  - ${s}`), `warnings: ${warnings.length ? warnings.join(" | ") : "none"}`],
  };
});

await demo('3b. "Durant ’s" is normalized to "Durant’s" after tags are stripped', async () => {
  const gen = g();
  const html = "<p><strong>Durant</strong>’s extension , per <em>Fake Wire</em> , is close .</p>";
  const out = gen.pick("lhStripTags")(html);
  return { ok: out === "Durant’s extension, per Fake Wire, is close.", lines: [`in:  ${html}`, `out: ${out}`] };
});

await demo("3c. an editor-tightened sentence still maps to its claim", async () => {
  const gen = g();
  const body = "<p>The Example Owls offered nearly 60 million dollars to Fake Player.</p>";
  const claimStart = "The Example Owls have quietly offered nearly 60 million dollars";
  const score = gen.pick("lhOpeningOverlap")(gen.pick("lhStripTags")(body), claimStart);
  const warnings = gen.pick("lhVerifyClaims")(
    {
      claims: [{ sentence_start: claimStart, entry_index: 0, source_quote: "offered nearly 60 million" }],
      headline_claims: [{ sentence_start: "h", entry_index: 0, source_quote: "offered nearly 60 million" }],
      meta_claims: [{ sentence_start: "m", entry_index: 0, source_quote: "offered nearly 60 million" }],
      context_sentences: [], storyline_entities: ["Example Owls", "Fake Player"],
    },
    gen.pick("lhBuildEntries")([entry({ text: "The Example Owls have quietly offered nearly 60 million dollars to Fake Player." })], []),
    body, false
  );
  return {
    ok: score >= 0.7 && warnings.filter(w => /unsourced/i.test(w)).length === 0,
    lines: [`claim start:  ${claimStart}`, `final sentence: ${gen.pick("lhStripTags")(body)}`,
            `opening overlap: ${(score * 100).toFixed(0)}% (threshold 70%)`,
            `unsourced warnings: ${warnings.filter(w => /unsourced/i.test(w)).length}`],
  };
});

// --- 4. self-referential, padding, off-storyline ---------------------------
await demo("4a. a self-referential sentence is linted", async () => {
  const gen = g();
  const body = "<p>The Example Owls made an offer. No specific deadline was cited in the available reports.</p>";
  const lint = gen.pick("lhLint")("h", "m", body, [], [], { min: 1, max: 900 }, {});
  const hits = lint.warnings.filter(w => /^Self-referential/.test(w));
  return { ok: hits.length > 0, lines: [`body: ${gen.pick("lhStripTags")(body)}`, ...hits.map(h => `  - ${h}`)] };
});

await demo('4b. a "What comes next" section with no date or event is linted', async () => {
  const gen = g();
  const padded = "<p>Lead.</p><h3>What comes next</h3><p>A decision is expected at some point.</p>";
  const dated = "<p>Lead.</p><h3>What comes next</h3><p>The Example Owls must decide by Jan. 20.</p>";
  const a = gen.pick("lhLint")("h", "m", padded, [], [], { min: 1, max: 900 }, {}).warnings.filter(w => /What comes next/.test(w));
  const b = gen.pick("lhLint")("h", "m", dated, [], [], { min: 1, max: 900 }, {}).warnings.filter(w => /What comes next/.test(w));
  return { ok: a.length === 1 && b.length === 0, lines: [`padded section: ${a[0] || "no warning"}`, `dated section: ${b.length ? b[0] : "no warning (correct)"}`] };
});

await demo("4c. a claim resting on an entry about someone else is linted Off-storyline", async () => {
  const gen = g();
  const entries = gen.pick("lhBuildEntries")([
    entry({ text: "Fake Player and the Example Owls kept talking about the extension." }),
    entry({ text: "Other Player wants out of the Fake Bears and has asked for a trade." }),
  ], []);
  const warnings = gen.pick("lhVerifyClaims")(
    {
      claims: [
        { sentence_start: "Fake Player and the Example Owls kept talking", entry_index: 0, source_quote: "kept talking about the extension" },
        { sentence_start: "Other Player has asked for a trade", entry_index: 1, source_quote: "has asked for a trade" },
      ],
      headline_claims: [{ sentence_start: "h", entry_index: 0, source_quote: "kept talking" }],
      meta_claims: [{ sentence_start: "m", entry_index: 0, source_quote: "kept talking" }],
      context_sentences: [], storyline_entities: ["Fake Player", "Example Owls"],
    },
    entries,
    "<p>Fake Player and the Example Owls kept talking about the extension. Other Player has asked for a trade.</p>",
    false
  );
  const hits = warnings.filter(w => /^Off-storyline/.test(w));
  return { ok: hits.length === 1, lines: [`storyline entities: Fake Player, Example Owls`, ...hits.map(h => `  - ${h}`)] };
});

// --- 5. aggregator accounts and generic links ------------------------------
await demo("5a. an aggregator entry reaches the writer as a speaker, not as a source", async () => {
  const gen = g();
  const aggregators = gen.pick("lhParseAggregators")("ohnohedidnt24, Oh No He Didn't");
  const entries = gen.pick("lhBuildEntries")([
    entry({
      reporter: "ohnohedidnt24", outlet: "ohnohedidnt24",
      source_url: "https://example.social/ohnohedidnt24/post/9",
      text: "Fake Player: I am happy here, he said at media day.",
      quote: "I am happy here",
    }),
  ], aggregators);
  const payload = gen.pick("lhEntriesPayload")(entries);
  return {
    ok: entries[0].aggregator === true && entries[0].reporter === "Fake Player" && !/OUTLET|REPORTER/.test(payload) && /AGGREGATOR: yes/.test(payload),
    lines: [`parsed accounts: ${JSON.stringify(aggregators)}`, "payload:", ...payload.split("\n").map(l => `  ${l}`)],
  };
});

await demo("5b. naming the aggregator in the body is linted", async () => {
  const gen = g();
  const aggregators = gen.pick("lhParseAggregators")("ohnohedidnt24, Oh No He Didn't");
  const good = '<p><strong>Fake Player</strong> <a href="https://example.social/ohnohedidnt24/post/9">said</a> at media day that he is happy.</p>';
  const bad = '<p>According to ohnohedidnt24, <strong>Fake Player</strong> is happy.</p>';
  const a = gen.pick("lhLint")("h", "m", good, [], [], { min: 1, max: 900 }, { aggregators }).warnings.filter(w => /^Aggregator/.test(w));
  const b = gen.pick("lhLint")("h", "m", bad, [], [], { min: 1, max: 900 }, { aggregators }).warnings.filter(w => /^Aggregator/.test(w));
  return {
    ok: a.length === 0 && b.length === 1,
    lines: [`speaker attribution, verb linked: ${a.length ? a[0] : "no warning (correct)"}`, `aggregator named: ${b[0]}`],
  };
});

await demo("5c. a /social/ URL is not offered to the writer as a link, and is linted if used", async () => {
  const gen = g();
  const generic = ["https://example.net/social/", "https://example.net/rumors/", "https://example.net/news", "https://example.net", "https://example.net/"];
  const story = ["https://example.net/social/post/12", "https://example.com/news/2999/the-story"];
  const entries = gen.pick("lhBuildEntries")([entry({ source_url: "https://example.net/social/" })], []);
  const payload = gen.pick("lhEntriesPayload")(entries);
  const lint = gen.pick("lhLint")("h", "m", '<p><a href="https://example.net/social/">Fake Reporter</a> reported it.</p>', [], [], { min: 1, max: 900 }, {});
  const hits = lint.warnings.filter(w => /^Generic section URL/.test(w));
  return {
    ok: generic.every(u => gen.pick("lhIsGenericUrl")(u)) && story.every(u => !gen.pick("lhIsGenericUrl")(u))
      && /URL: NO LINK/.test(payload) && hits.length === 1,
    lines: [
      `generic: ${generic.map(u => `${u} -> ${gen.pick("lhIsGenericUrl")(u)}`).join(", ")}`,
      `story:   ${story.map(u => `${u} -> ${gen.pick("lhIsGenericUrl")(u)}`).join(", ")}`,
      `payload URL line: ${payload.split("\n").find(l => l.includes("URL"))}`,
      `lint when linked anyway: ${hits[0]}`,
    ],
  };
});

// --- 6. content stream polish ---------------------------------------------
await demo("6a. a five-word title counts only tokens that contain a letter", async () => {
  const gen = g();
  const cases = [
    ["Fake Player extension talks are moving", true],
    ["Fake Player 1 2 3 4", false],
    ["Fake Player extension talks", false],
    ["Trade talks:", false],
  ];
  const got = cases.map(([t]) => [t, gen.pick("lhUsableTitle")(t)]);
  return {
    ok: cases.every(([t, want], i) => got[i][1] === want),
    lines: got.map(([t, v], i) => `${v ? "usable    " : "not usable"}  ${JSON.stringify(t)} (expected ${cases[i][1] ? "usable" : "not usable"})`),
  };
});

await demo('6b. "‼" and friends are stripped from a stream title', async () => {
  const gen = g();
  const raw = "Fake Player extension talks are moving ‼ ⁉ ✔ ⭐ 🚀 #NBA";
  const out = gen.pick("lhCleanTitle")(raw, true);
  return { ok: !/[‼⁉✔⭐]/.test(out) && out === "Fake Player extension talks are moving", lines: [`in:  ${JSON.stringify(raw)}`, `out: ${JSON.stringify(out)}`] };
});

// --- 7. relay diagnostics --------------------------------------------------
await demo("7a. stop reason and output tokens are reported per call", async () => {
  const gen = g();
  const r = await run(gen, {
    matched: [entry(), entry({ source_url: "https://example.com/story/2" }), entry({ source_url: "https://example.com/story/3" })],
    writerMeta: { stop_reason: "end_turn", usage: { input_tokens: 2100, output_tokens: 1450 } },
    editorMeta: { stop_reason: "end_turn", usage: { input_tokens: 1900, output_tokens: 700 } },
  });
  const notes = gen.pick("lhRunNotes")(r);
  return {
    ok: /stop reason end_turn/.test(notes[0]) && /output tokens 1450/.test(notes[0]) && notes.length === 2,
    lines: notes,
  };
});

await demo("7b. a writer call capped below the requested 12000 is linted", async () => {
  const gen = g();
  const r = await run(gen, {
    matched: [entry(), entry({ source_url: "https://example.com/story/2" }), entry({ source_url: "https://example.com/story/3" })],
    writerMeta: { stop_reason: "max_tokens", usage: { output_tokens: 4096 } },
  });
  const hits = warn(r, /^Relay capped output/);
  const cats = gen.pick("lhCategorize")(r.lint.warnings);
  return {
    ok: hits.length === 1 && cats.truncated >= 1,
    lines: [`requested max_tokens: ${gen.pick("LH_WRITER_MAX_TOKENS")}`, `lint: ${hits[0]}`, `batch column "truncated": ${cats.truncated}`],
  };
});

// --- batch surface ---------------------------------------------------------
await demo("8. the batch row shows the sensitive exclusion and the new columns", async () => {
  const gen = g();
  const r = await run(gen, { matched: eighteen() });
  const label = gen.pick("lhBatchStatusLabel")(r);
  const order = gen.pick("LH_BATCH_CAT_ORDER");
  return {
    ok: /excluded as sensitive/.test(label) && order.includes("self-referential") && order.includes("off-storyline/source"),
    lines: [`status cell: ${label}`, `batch columns: ${order.join(", ")}`],
  };
});

// --- report ----------------------------------------------------------------
results.forEach(r => {
  console.log(`${r.ok ? "PASS" : "FAIL"}  ${r.title}`);
  r.lines.forEach(l => console.log(`        ${l}`));
  console.log("");
});
const failed = results.filter(r => !r.ok).length;
console.log(`${results.length - failed}/${results.length} demos passed.`);
process.exitCode = failed ? 1 : 0;
}

main().catch(e => { console.error(e); process.exitCode = 1; });
