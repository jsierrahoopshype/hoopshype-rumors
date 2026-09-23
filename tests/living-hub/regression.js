"use strict";
// Regression harness: proves the Hub and Explainer code paths are byte-identical
// between a baseline copy of hub-generator.html (main, by default) and the
// working-tree copy.
//
// It compares three things:
//   1. the shared JavaScript region, everything above the LIVING HUB banner,
//      byte for byte;
//   2. the non-script markup, line by line, as a subsequence check: the Living
//      hub may ADD markup, it may never change or remove any that exists;
//   3. the actual behavior of the Hub and Explainer paths, by running them in
//      both copies against the same fake fixtures and diffing every request
//      made and every string produced.

const fs = require("fs");
const os = require("os");
const path = require("path");
const crypto = require("crypto");
const { execFileSync } = require("child_process");

const { loadGenerator, relayReply, extractScript, REPO_ROOT, DEFAULT_HUB } = require("./env.js");
const { FAKE_ARCHIVE, FAKE_MANIFEST, FAKE_CS_INDEX } = require("./fixtures.js");

const LIVING_MARKER = "// LIVING HUB MODE";

function sha(s) { return crypto.createHash("sha256").update(s).digest("hex").slice(0, 16); }

function baselineFile(ref) {
  const out = path.join(os.tmpdir(), `hub-generator.baseline.${process.pid}.html`);
  const buf = execFileSync("git", ["show", `${ref}:hub-generator.html`], { cwd: REPO_ROOT, maxBuffer: 64 * 1024 * 1024 });
  fs.writeFileSync(out, buf);
  return out;
}

function sharedRegion(html) {
  const script = extractScript(html);
  const at = script.indexOf(LIVING_MARKER);
  if (at === -1) throw new Error("LIVING HUB banner not found; cannot isolate the shared region.");
  // Back up over the banner's own ==== rule so the cut is stable.
  const cut = script.lastIndexOf("// ===", at);
  return script.slice(0, cut === -1 ? at : cut);
}

function markupLines(html) {
  return html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, "<script/>")
    .split("\n");
}

function idsIn(html) {
  return [...html.matchAll(/\bid="([^"]+)"/g)].map(m => m[1]);
}

// --- behavior runs --------------------------------------------------------
function primeDom(g, fields) {
  Object.entries(fields).forEach(([id, v]) => {
    const el = g.document.getElementById(id);
    if (typeof v === "boolean") el.checked = v; else el.value = v;
  });
}

function archiveResponder(relayList, opts) {
  let i = 0;
  const options = opts || {};
  return async (url) => {
    const u = String(url);
    if (u.includes("/api/rumors/part/")) return { json: FAKE_ARCHIVE };
    if (u.includes("relay")) {
      const next = relayList[i++];
      if (!next) throw new Error("relay called more times than the harness programmed");
      return { json: next };
    }
    if (u.endsWith("manifest.json")) {
      return options.noStream ? { ok: false, status: 404, json: {} } : { json: FAKE_MANIFEST };
    }
    if (u.includes("/data/index/")) {
      return options.noStream ? { ok: false, status: 404, json: {} } : { json: FAKE_CS_INDEX };
    }
    return { ok: false, status: 404, json: {} };
  };
}

const HUB_FIELDS = {
  tag: "Fake Player", window: "72", customHours: "72", paras: "3",
  length: "medium", bullets: "allow", mode: "hub", questions: "",
};

async function runHub(file) {
  const g = loadGenerator({ file });
  primeDom(g, HUB_FIELDS);
  g.onFetch(archiveResponder([relayReply("<p>Fake hub body about Fake Player.</p>")]));
  await g.pick("generate")();
  return snapshot(g);
}

async function runExplainer(file) {
  const g = loadGenerator({ file });
  primeDom(g, Object.assign({}, HUB_FIELDS, {
    mode: "explainer",
    questions: "What is the state of talks?\nWhat is the deadline?",
  }));
  g.onFetch(archiveResponder([relayReply("<p>Fake explainer body.</p>")]));
  await g.pick("generate")();
  return snapshot(g);
}

async function runCount(file) {
  const g = loadGenerator({ file });
  primeDom(g, HUB_FIELDS);
  g.onFetch(archiveResponder([]));
  await g.pick("checkCount")();
  return snapshot(g);
}

async function runSuggest(file) {
  const g = loadGenerator({ file });
  primeDom(g, HUB_FIELDS);
  g.onFetch(archiveResponder([relayReply("Question one?\nQuestion two?")]));
  await g.pick("checkCount")();
  await g.pick("suggestQuestions")();
  return snapshot(g);
}

async function runStreamRender(file) {
  const g = loadGenerator({ file });
  g.onFetch(archiveResponder([], {}));
  const cs = await g.pick("csFetchMentions")("Fake Player", 72);
  return JSON.stringify({ cs, html: g.pick("csRenderHtml")(cs) }, null, 1);
}

function snapshot(g) {
  const d = g.document;
  const ids = ["status", "countMsg", "htmlOut", "preview", "questions", "suggestMsg", "lhBody", "lhHeadline", "lhMeta"];
  const dom = {};
  ids.forEach(id => {
    const el = d._byId.get(id);
    if (!el) return;
    dom[id] = { value: el.value, text: el.textContent, html: el.innerHTML, cls: el.className };
  });
  return JSON.stringify({ calls: g.calls, dom }, null, 1);
}

// --- driver ---------------------------------------------------------------
async function main() {
  const args = process.argv.slice(2);
  const arg = n => { const hit = args.find(a => a.startsWith(`--${n}=`)); return hit ? hit.split("=").slice(1).join("=") : ""; };
  const ref = arg("baseline") || "main";
  const candidateFile = arg("hub") || process.env.HUB_FILE || DEFAULT_HUB;
  const baseFile = arg("baseline-file") || baselineFile(ref);

  const baseHtml = fs.readFileSync(baseFile, "utf8");
  const candHtml = fs.readFileSync(candidateFile, "utf8");

  const results = [];
  const check = (name, ok, detail) => { results.push({ name, ok, detail: detail || "" }); };

  // 1. shared JS region
  const a = sharedRegion(baseHtml), b = sharedRegion(candidateFile === baseFile ? baseHtml : candHtml);
  check("shared JS region (config, helpers, Content Stream, Hub, Explainer, wiring) is byte-identical",
    a === b, `baseline ${sha(a)} / candidate ${sha(b)}, ${a.length} vs ${b.length} bytes`);

  // 2. markup: additive only
  const baseLines = markupLines(baseHtml), candLines = markupLines(candHtml);
  let i = 0, missing = null;
  for (const line of baseLines) {
    const at = candLines.indexOf(line, i);
    if (at === -1) { missing = line; break; }
    i = at + 1;
  }
  check("every baseline markup line still present, in order (Living hub may only add)",
    missing === null, missing === null ? `${baseLines.length} lines` : `first missing line: ${missing.trim().slice(0, 90)}`);

  // 3. element ids
  const baseIds = idsIn(baseHtml), candIds = new Set(idsIn(candHtml));
  const lostIds = baseIds.filter(id => !candIds.has(id));
  check("no element id removed or renamed", lostIds.length === 0, lostIds.join(", ") || `${baseIds.length} ids intact`);

  // 4-8. behavior
  const runs = [
    ["Hub mode: identical relay request and identical output HTML", runHub],
    ["Explainer mode: identical relay request and identical output HTML", runExplainer],
    ["Check count: identical archive request and identical message", runCount],
    ["Suggest questions: identical relay request and identical question list", runSuggest],
    ["Content Stream mentions: identical fetches and identical rendered HTML", runStreamRender],
  ];
  for (const [name, fn] of runs) {
    const x = await fn(baseFile);
    const y = await fn(candidateFile);
    let detail = `${x.length} bytes, sha ${sha(x)}`;
    if (x !== y) {
      const at = [...x].findIndex((c, k) => c !== y[k]);
      detail = `first difference at byte ${at}:\n  baseline:  ${JSON.stringify(x.slice(Math.max(0, at - 40), at + 60))}\n  candidate: ${JSON.stringify(y.slice(Math.max(0, at - 40), at + 60))}`;
    }
    check(name, x === y, detail);
  }

  const pad = Math.max(...results.map(r => r.name.length));
  console.log(`baseline:  ${ref} (${baseFile})`);
  console.log(`candidate: ${candidateFile}\n`);
  results.forEach(r => console.log(`${r.ok ? "PASS" : "FAIL"}  ${r.name.padEnd(pad)}  ${r.detail}`));
  const failed = results.filter(r => !r.ok).length;
  console.log(`\n${results.length - failed}/${results.length} checks passed.`);
  process.exitCode = failed ? 1 : 0;
}

main().catch(e => { console.error(e); process.exitCode = 1; });
