"use strict";
// Loads hub-generator.html into a Node vm sandbox with a minimal fake DOM, so
// the tool's own functions can be called directly from a test.
//
// Nothing here talks to the network: fetch is a stub that must be programmed by
// the caller, and every fixture used by the tests is invented.

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const REPO_ROOT = path.resolve(__dirname, "..", "..");
const DEFAULT_HUB = path.join(REPO_ROOT, "hub-generator.html");

// --- fake DOM -------------------------------------------------------------
// Elements are created on demand, so the sandbox never needs a real parser and
// a new id in the tool does not break the harness.
function makeClassList(el) {
  const set = new Set();
  return {
    _set: set,
    add: c => set.add(c),
    remove: c => set.delete(c),
    contains: c => set.has(c),
    toggle: (c, force) => {
      const on = force === undefined ? !set.has(c) : !!force;
      if (on) set.add(c); else set.delete(c);
      return on;
    },
    toString: () => [...set].join(" "),
  };
}

function makeElement(tag, id) {
  const el = {
    tagName: (tag || "div").toUpperCase(),
    id: id || "",
    value: "",
    checked: false,
    disabled: false,
    textContent: "",
    innerHTML: "",
    className: "",
    colSpan: 1,
    children: [],
    listeners: {},
    appendChild(child) { this.children.push(child); return child; },
    addEventListener(name, fn) { (this.listeners[name] = this.listeners[name] || []).push(fn); },
    dispatch(name, ev) { (this.listeners[name] || []).forEach(fn => fn(ev)); },
  };
  el.classList = makeClassList(el);
  return el;
}

function makeDocument() {
  const byId = new Map();
  return {
    _byId: byId,
    getElementById(id) {
      if (!byId.has(id)) byId.set(id, makeElement("div", id));
      return byId.get(id);
    },
    createElement(tag) { return makeElement(tag, ""); },
    addEventListener() {},
  };
}

// --- sandbox --------------------------------------------------------------
function extractScript(html) {
  const blocks = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)].map(m => m[1]);
  if (!blocks.length) throw new Error("No <script> block found in the generator.");
  return blocks.join("\n;\n");
}

// The generator declares everything with const/function at script top level, so
// nothing lands on globalThis. A direct eval defined inside the same script can
// still see those bindings, which is how the tests reach in.
const EXPORT_HOOK = "\n;globalThis.__pick = function (name) { return eval(name); };\n";

function loadGenerator(opts) {
  const options = opts || {};
  const file = options.file || process.env.HUB_FILE || DEFAULT_HUB;
  const html = fs.readFileSync(file, "utf8");
  const document = makeDocument();

  const calls = [];              // every fetch the code made, in order
  let responder = () => { throw new Error("fetch() was called but no responder is installed."); };

  const sandbox = {
    document,
    window: {},
    navigator: { clipboard: { writeText: () => Promise.resolve() } },
    console,
    URL, URLSearchParams, Intl, Date, Math, JSON, Set, Map, Promise,
    RegExp, Array, Object, String, Number, Boolean, Error, isNaN, parseInt, parseFloat,
    setTimeout: (fn) => fn && 0,
    clearTimeout: () => {},
    fetch: async (url, init) => {
      calls.push({ url, init });
      const body = await responder(url, init, calls.length - 1);
      return {
        ok: body.ok !== false,
        status: body.status || 200,
        json: async () => body.json,
      };
    },
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(extractScript(html) + EXPORT_HOOK, sandbox, { filename: path.basename(file) });

  return {
    file,
    html,
    document,
    sandbox,
    calls,
    // Reach a top-level binding by name: pick("lhLint")(...)
    pick: name => sandbox.__pick(name),
    // Program the fetch stub. fn(url, init, callIndex) -> { json } | { ok:false }
    onFetch(fn) { responder = fn; },
    // Queue of relay replies, in call order; anything else 404s.
    relayReplies(list) {
      let i = 0;
      responder = async (url) => {
        if (String(url).includes("relay")) {
          const next = list[i++];
          if (!next) throw new Error("relay called more times than the test programmed");
          return { json: next };
        }
        return { ok: false, status: 404, json: {} };
      };
    },
  };
}

// A Claude Messages-API shaped reply carrying JSON in its text block.
function relayReply(obj, extra) {
  return Object.assign({
    content: [{ type: "text", text: typeof obj === "string" ? obj : JSON.stringify(obj) }],
  }, extra || {});
}

module.exports = { loadGenerator, relayReply, extractScript, REPO_ROOT, DEFAULT_HUB };
