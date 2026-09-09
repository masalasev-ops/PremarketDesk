// Drives every desk screen against the real payload under a minimal DOM, so a
// RUNTIME error is caught. node --check cannot see this class of bug at all:
// "bare is not a function" parses perfectly and blanks a whole screen.
const fs = require("fs");
const vm = require("vm");

const js = fs.readFileSync(process.argv[2], "utf8");
const indexJson = fs.readFileSync(process.argv[3], "utf8");
const blobsJson = fs.readFileSync(process.argv[4], "utf8");

const errors = [];
let hashHandler = null;

const written = [];   // every innerHTML assignment, in order

function el(id) {
  const node = {
    id,
    textContent: "",
    _html: "",
    dataset: {},
    children: [],
    style: {},
    hidden: false,
    open: false,
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    addEventListener(type, fn) { if (type === "hashchange") hashHandler = fn; },
    removeEventListener() {},
    setAttribute() {},
    getAttribute: () => null,
    appendChild() {},
    removeChild() {},
    closest: () => null,
    querySelector: () => el("q"),
    querySelectorAll: () => [],
    getBoundingClientRect: () => ({ width: 900, height: 400, top: 0, left: 0 }),
    scrollIntoView() {},
    focus() {},
    click() {},
    insertBefore() {},
    replaceChild() {},
    cloneNode() { return el(id); },
    contains: () => false,
    firstChild: null,
    nextSibling: null,
  };
  Object.defineProperty(node, "innerHTML", {
    get() { return node._html; },
    set(v) { node._html = String(v); written.push(String(v)); },
  });
  node.parentNode = {
    replaceChild() {}, removeChild() {}, insertBefore() {}, appendChild() {},
  };
  return node;
}

const nodes = new Map();
const document = {
  documentElement: el("html"),
  body: el("body"),
  getElementById(id) {
    if (id === "desk-index") return { ...el(id), textContent: indexJson };
    if (id === "desk-payloads") return { ...el(id), textContent: blobsJson };
    if (!nodes.has(id)) nodes.set(id, el(id));
    return nodes.get(id);
  },
  createElement: (t) => el(t),
  createElementNS: (ns, t) => el(t),
  querySelector: () => el("q"),
  querySelectorAll: () => [],
  addEventListener(type, fn) { if (type === "hashchange") hashHandler = fn; },
};

const location = { hash: "#/" };
const window = {
  document,
  location,
  matchMedia: () => ({ matches: false, addEventListener() {} }),
  addEventListener(type, fn) { if (type === "hashchange") hashHandler = fn; },
  removeEventListener() {},
  print() {},
  scrollTo() {},
  scrollY: 0,
  requestAnimationFrame(fn) { fn(0); },
  getComputedStyle: () => ({ getPropertyValue: () => "" }),
};

const sandbox = {
  document, window, location, console,
  localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  setTimeout: (fn) => { try { fn(); } catch (e) { errors.push("setTimeout: " + e.message); } },
  clearTimeout() {}, setInterval() {}, clearInterval() {},
  atob, btoa, TextDecoder, TextEncoder, Uint8Array, Response,
  DecompressionStream, ReadableStream, Blob, URL, Promise, JSON, Math, Date,
  encodeURIComponent, decodeURIComponent, isNaN, parseFloat, parseInt,
};
sandbox.globalThis = sandbox;
sandbox.self = sandbox;

process.on("unhandledRejection", (e) =>
  errors.push("unhandled rejection: " + (e && e.message ? e.message : e)));

try {
  vm.runInNewContext(js, sandbox, { filename: "deck.js" });
} catch (e) {
  errors.push("boot: " + e.message);
}

const index = JSON.parse(indexJson);
const day = (index.sessions && index.sessions[0] && index.sessions[0].date) ||
  Object.keys(JSON.parse(blobsJson))[0];

// The REAL routes. The nav's hrefs are rewritten by setNav to
// #/session/<date>/<screen>; "#/precedent" is not a route at all and falls
// through to Sessions, which is how the first version of this harness
// rendered eleven screens without ever reaching the one that was broken.
const screens = ["morning", "precedent", "midday", "report", "session"];
const routes = ["#/", "#/sessions", "#/record", "#/health", `#/health/${day}`,
  `#/name/QCOM`, "#/nonsense"]
  .concat(screens.map((s) => `#/session/${day}/${s === "session" ? "" : s}`));

// A REAL wait, on the host's timer and not the sandbox's. The shim's
// setTimeout runs its callback at once and ignores the delay, which is right
// for driving the page and useless for waiting on it.
const settle = (ms) => new Promise((r) => setTimeout(r, ms));

// A screen that only ever said this never decompressed its payload. It is not
// a screen that rendered nothing worth checking; it is a screen that was still
// being cancelled when the harness looked at it.
const PLACEHOLDER = /^\s*(<[^>]*>|\s)*Reading[^<]*(<[^>]*>|\s)*$/;

(async () => {
  for (const route of routes) {
    const before = written.length;
    location.hash = route;
    try {
      if (hashHandler) hashHandler();
      // EACH ROUTE SETTLES BEFORE THE NEXT ONE STARTS. render() cancels a run
      // that is no longer the current hash, so driving routes back to back
      // measures the placeholder of every screen and the content of none.
      await settle(250);
    } catch (e) {
      errors.push(`${route}: ${e.message}`);
    }
    const drawn = written.slice(before);
    const last = drawn.length ? drawn[drawn.length - 1] : "";
    if (!drawn.length) {
      errors.push(`${route}: rendered nothing at all`);
    } else if (PLACEHOLDER.test(last)) {
      errors.push(`${route}: never got past its placeholder, so nothing on ` +
        `this screen was checked (last write was ${JSON.stringify(last.slice(0, 60))})`);
    }
  }
  await settle(250);

  // render() catches its own rejection and writes err.message into the page,
  // which is why nothing throws and why the first version of this harness
  // reported twelve clean screens over a build whose Precedent screen was one
  // sentence reading "bare is not a function". These substrings cannot occur
  // in the desk's own prose.
  const JS_ERRORS = ["is not a function", "is not defined",
    "Cannot read propert", "undefined is not", "null is not",
    "Maximum call stack"];
  for (const html of written) {
    for (const needle of JS_ERRORS) {
      if (html.includes(needle)) errors.push("rendered error: " + html.slice(0, 160));
    }
  }

  if (errors.length) {
    console.log(`RUNTIME ERRORS (${errors.length}):`);
    for (const e of [...new Set(errors)]) console.log("  " + e);
    process.exit(1);
  }
  console.log(`all ${routes.length} routes rendered with no runtime error`);
})();
