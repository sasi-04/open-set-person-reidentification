/*
 * Photograph the real website, step by step, for the user manual.
 *
 * In plain words: this drives the running website exactly the way a person would (click "Enroll identity", type an ID, add photos,
 * tick the boxes, press the buttons ...) and, at each step, saves a picture of the screen with RED NUMBERED BOXES drawn on top of
 * the parts the manual explains. Nothing is mocked: every picture is a screenshot of the real application answering real photos.
 *
 * Use a clean test instance (it enrols people and leaves them there):
 *     $env:REID_DATA_DIR = "D:\scratch\manual_data"; powershell -File scripts\start.ps1 -Port 8765
 *     node scripts/make_manual_images.mjs http://127.0.0.1:8765
 * Output: demo/manual_images/*.jpg   (then run scripts/build_user_manual.mjs to make the PDF)
 */
import { createRequire } from "node:module";
import { existsSync, mkdirSync, rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const require = createRequire(path.join(root, ".tools", "shots", "package.json"));
const puppeteer = require("puppeteer-core");

const base = (process.argv[2] ?? "http://127.0.0.1:8765").replace(/\/$/, "");
const samples = path.join(root, "demo", "samples");
const faces = path.join(samples, "faces");
const out = path.join(root, "demo", "manual_images");
rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });

const executablePath = [
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
].find(existsSync);
if (!executablePath) throw new Error("Neither Edge nor Chrome was found.");

const profile = path.join(root, ".tools", "tmp", "edge-profile-manual");
mkdirSync(profile, { recursive: true });
const browser = await puppeteer.launch({ executablePath, headless: true, userDataDir: profile, args: ["--no-sandbox"] });
const page = await browser.newPage();
await page.setCacheEnabled(false);
await page.emulateMediaFeatures([{ name: "prefers-reduced-motion", value: "reduce" }]);
const SCALE = 1.5;
await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: SCALE });
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// ---------------------------------------------------------------------------------------------- in-page helpers
await page.evaluateOnNewDocument(() => {
  try { localStorage.setItem("reid-theme", "light"); } catch { /* ignore */ }
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none";
  };
  const area = (el) => { const r = el.getBoundingClientRect(); return r.width * r.height; };
  // Find ONE element from a small description: {css} | {heading} | {label} | {text, tag}, optionally {within:{...}}, {closest}, {nth}.
  window.__loc = (spec) => {
    let scope = document;
    if (spec.within) { scope = window.__loc(spec.within); if (!scope) return null; }
    let list = [];
    if (spec.css) list = [...scope.querySelectorAll(spec.css)];
    else if (spec.heading) {
      list = [...scope.querySelectorAll("h1,h2,h3")]
        .filter((h) => (spec.startsWith ? h.textContent.trim().startsWith(spec.heading) : h.textContent.trim() === spec.heading))
        .map((h) => h.closest("section") || h.parentElement);
    } else if (spec.label) {
      list = [...scope.querySelectorAll("label")].filter((l) => l.textContent.trim().startsWith(spec.label))
        .map((l) => (spec.container ? l.closest(spec.container) : l.control || document.getElementById(l.htmlFor)));
    } else if (spec.text) {
      list = [...scope.querySelectorAll(spec.tag || "button")].filter((e) => e.textContent.replace(/\s+/g, " ").trim().includes(spec.text));
      list.sort((a, b) => area(a) - area(b));
    }
    list = list.filter(Boolean).filter(visible);
    if (spec.closest) list = list.map((e) => e.closest(spec.closest)).filter(Boolean);
    return list[spec.nth || 0] || null;
  };
  window.__rect = (specs) => {
    let l = 1e9, t = 1e9, r = -1e9, b = -1e9;
    for (const spec of specs) {
      const el = window.__loc(spec);
      if (!el) return null;
      const q = el.getBoundingClientRect();
      l = Math.min(l, q.left); t = Math.min(t, q.top); r = Math.max(r, q.right); b = Math.max(b, q.bottom);
    }
    return { x: l, y: t, width: r - l, height: b - t };
  };
  window.__mark = (items) => {
    document.getElementById("__marks")?.remove();
    const host = document.createElement("div");
    host.id = "__marks";
    host.style.cssText = "position:fixed;inset:0;pointer-events:none;z-index:2147483647";
    const missing = [];
    for (const it of items) {
      const el = window.__loc(it);
      if (!el) { missing.push(`${it.n}: ${JSON.stringify(it)}`); continue; }
      const r = el.getBoundingClientRect();
      const pad = it.pad ?? 5;
      const box = document.createElement("div");
      box.style.cssText = `position:absolute;left:${r.left - pad}px;top:${r.top - pad}px;width:${r.width + 2 * pad}px;height:${r.height + 2 * pad}px;border:3px solid #e53935;border-radius:8px;box-shadow:0 0 0 2px rgba(255,255,255,.75)`;
      const at = it.at || "tl";
      const bx = at.includes("r") ? r.right + pad - 17 : r.left - pad - 17;
      const by = at.includes("b") ? r.bottom + pad - 17 : r.top - pad - 17;
      const badge = document.createElement("div");
      badge.textContent = String(it.n);
      badge.style.cssText = `position:absolute;left:${Math.max(3, bx)}px;top:${Math.max(3, by)}px;width:32px;height:32px;border-radius:50%;background:#e53935;color:#fff;font:700 18px/32px Segoe UI,Arial,sans-serif;text-align:center;border:3px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.45)`;
      host.append(box, badge);
    }
    document.body.append(host);
    return missing;
  };
  window.__unmark = () => document.getElementById("__marks")?.remove();
});

const problems = [];
const saved = [];
async function go(route, settle = 1500) {
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: SCALE });
  await page.goto(base + route, { waitUntil: "networkidle0" });
  await sleep(settle);
}
async function fit(max = 3600) {
  await sleep(300);
  const height = await page.evaluate(() => Math.ceil(document.documentElement.scrollHeight));
  await page.setViewport({ width: 1440, height: Math.min(Math.max(height, 900), max), deviceScaleFactor: SCALE });
  await sleep(500);
}
async function element(spec) {
  const handle = await page.evaluateHandle((s) => window.__loc(s), spec);
  const el = handle.asElement();
  if (!el) throw new Error(`not found: ${JSON.stringify(spec)} on ${page.url()}`);
  return el;
}
async function marks(items) {
  const missing = await page.evaluate((i) => window.__mark(i), items);
  if (missing.length) problems.push(`marks missing on ${page.url()}: ${missing.join(" | ")}`);
}
/** Save the screen (whole window, or the area around some elements) - with the red marks that are currently drawn. */
async function save(name, { around = null, margin = 14, mark = [], dir = out } = {}) {
  if (mark.length) await marks(mark);
  await sleep(250);
  let clip;
  if (around) {
    const rect = await page.evaluate((specs) => window.__rect(specs), around);
    if (!rect) throw new Error(`cannot clip ${name}: ${JSON.stringify(around)}`);
    const view = await page.evaluate(() => ({ w: innerWidth, h: innerHeight, sx: scrollX, sy: scrollY }));
    const x = Math.max(0, rect.x - margin), y = Math.max(0, rect.y - margin);
    // the rectangle is measured in the visible window; the picture is cut from the whole page, so add how far the page is scrolled
    clip = { x: x + view.sx, y: y + view.sy, width: Math.min(view.w - x, rect.width + 2 * margin), height: Math.min(view.h - y, rect.height + 2 * margin) };
  }
  await page.screenshot({ path: path.join(dir, `${name}.jpg`), type: "jpeg", quality: 90, ...(clip ? { clip } : {}) });
  await page.evaluate(() => window.__unmark());
  saved.push(name);
  console.log("  saved", name);
}
async function click(spec) { await (await element(spec)).click(); await sleep(350); }
async function typeInto(spec, text) {
  const el = await element(spec);
  await el.click({ clickCount: 3 });
  await el.type(text, { delay: 8 });
}
async function setChecked(spec, wanted) {
  const el = await element(spec);
  const now = await el.evaluate((node) => node.checked);
  if (now !== wanted) await el.click();
  await sleep(200);
}
async function pick(cssOrSpec, ...files) {
  const spec = typeof cssOrSpec === "string" ? { css: cssOrSpec } : cssOrSpec;
  const el = await element({ ...spec, css: spec.css });
  await el.uploadFile(...files);
  await sleep(900);
}
async function waitText(text, timeout = 90000) {
  await page.waitForFunction((t) => document.body.innerText.includes(t), { timeout }, text);
}
const D = { within: { css: '[role="dialog"]' } };

// =============================================================================================== 1. the first screen
console.log("1. First screen and screen map");
await go("/", 2500);
await save("01_first_screen", {
  mark: [
    { n: 1, css: 'nav[aria-label="Main"]', pad: 4, at: "tr" },
    { n: 2, css: 'a[href="/settings?tab=system"]', at: "br" },
    { n: 3, css: 'a[href="/how-it-works"]', at: "tl" },
    { n: 4, heading: "The essentials in three steps", at: "tl" },
    { n: 5, css: "#open-set-example header", at: "tl" },
  ],
});
await save("02_screen_map", {
  mark: [
    { n: 1, css: 'nav a[href="/"]', pad: 3, at: "tr" },
    { n: 2, css: 'nav a[href="/gallery"]', pad: 3, at: "tr" },
    { n: 3, css: 'nav a[href="/match"]', pad: 3, at: "tr" },
    { n: 4, css: 'nav a[href="/video"]', pad: 3, at: "tr" },
    { n: 5, css: 'nav a[href="/lookalike"]', pad: 3, at: "tr" },
    { n: 6, css: 'nav a[href="/evaluation"]', pad: 3, at: "tr" },
    { n: 7, css: 'nav a[href="/settings"]', pad: 3, at: "tr" },
  ],
});

// =============================================================================================== 1b. the example on the home page
console.log("1b. The built-in example");
const EX = { css: "#open-set-example" };
await go("/", 2500);
await page.setViewport({ width: 1440, height: 1800, deviceScaleFactor: SCALE });
await page.evaluate(() => document.getElementById("open-set-example").scrollIntoView({ block: "start" }));
await sleep(700);
await save("01a_example_before", {
  around: [{ css: "#open-set-example header" }, { css: "#photos-title" }, { css: 'li[data-case="known-2"]' }], margin: 12,
  mark: [
    { n: 1, text: "Run the example", tag: "button", within: EX, at: "tr" },
    { n: 2, heading: "Who the system knows", startsWith: true, at: "tl" },
    { n: 3, css: "#photos-title", pad: 8, at: "tl" },
    { n: 4, text: "Rules:", tag: "span", within: EX, at: "tr" },
  ],
});
await page.evaluate(() => [...document.querySelectorAll("#open-set-example button")].find((b) => b.textContent.trim() === "Run the example")?.click());
await waitText("What the example shows", 120000);
await sleep(1500);
await page.evaluate(() => document.getElementById("open-set-example").scrollIntoView({ block: "start" }));
await sleep(700);
// a clean copy (no red marks) for the presentation slides
const conclusionBox = { text: "What the example shows", tag: "div", closest: '[role="status"]' };
await save("00_home_open_set_example", { around: [conclusionBox, { css: "#open-set-example figure", nth: 1 }], margin: 12, dir: path.join(root, "demo", "screenshots") });
await save("01b_example_result", {
  around: [{ text: "What the example shows", tag: "div", closest: '[role="status"]' }, { label: "Try it", container: ".bg-surface-2" }], margin: 12,
  mark: [
    { n: 1, text: "What the example shows", tag: "div", closest: '[role="status"]', at: "tl" },
    { n: 2, css: "#open-set-example table", at: "tl" },
    { n: 3, css: "#open-set-example figure", nth: 0, at: "tl" },
    { n: 4, css: "#open-set-example figure", nth: 1, at: "tl" },
    { n: 5, label: "Try it", container: ".bg-surface-2", at: "tl" },
  ],
});
const SAME = 'li[data-case="same-1"]';
await click({ css: `${SAME} > div:nth-child(2) summary` });
await page.evaluate((s) => document.querySelector(s).scrollIntoView({ block: "start" }), SAME);
await page.evaluate(() => window.scrollBy(0, -170));
await page.setViewport({ width: 1440, height: 1000, deviceScaleFactor: SCALE });
await sleep(700);
await save("01c_example_rows", {
  around: [{ css: SAME }, { css: 'li[data-case="same-2"]' }], margin: 40,
  mark: [
    { n: 1, css: `${SAME} img`, at: "tl" },
    { n: 2, css: `${SAME} > div:nth-child(2)`, at: "tr" },
    { n: 3, css: `${SAME} > div:nth-child(3)`, at: "tr" },
    { n: 4, css: `${SAME} > div:nth-child(2) details`, at: "br" },
  ],
});

// =============================================================================================== 2. add a person
console.log("2. Add a person");
await go("/gallery");
await save("03_gallery_empty", { mark: [{ n: 1, text: "Enroll identity", css: undefined, tag: "button", nth: 0 }] });

async function enrol(id, description, files, { shoot = false } = {}) {
  await click({ text: "Enroll identity", tag: "button", nth: 0 });
  await page.waitForSelector('[role="dialog"]');
  await sleep(500);
  await typeInto({ ...D, label: "Reference ID" }, id);
  await typeInto({ ...D, label: "Description" }, description);
  await pick({ ...D, css: 'input[type="file"]' }, ...files);
  await setChecked({ ...D, label: "I confirm" }, true);
  await sleep(500);
  if (shoot) {
    await page.setViewport({ width: 1440, height: 1100, deviceScaleFactor: SCALE });
    await sleep(500);
    await save("04_enroll_dialog", {
      around: [{ css: '[role="dialog"]' }], margin: 20,
      mark: [
        { n: 1, ...D, label: "Reference ID", container: ".flex.flex-col", at: "tr" },
        { n: 2, ...D, label: "Description", container: ".flex.flex-col", at: "tr" },
        { n: 3, ...D, css: ".border-dashed", at: "tl" },
        { n: 4, ...D, css: 'ul[aria-label="Chosen images"]', at: "tr" },
        { n: 5, ...D, label: "Each image is already", container: ".flex.items-start", at: "tl" },
        { n: 6, ...D, label: "I confirm", container: ".flex.items-start", at: "tl" },
        { n: 7, ...D, text: "Enroll identity", tag: "button", nth: 0, at: "tr" },
      ],
    });
  }
  await click({ ...D, text: "Enroll identity", tag: "button" });
  await waitText("now has", 60000);
  await sleep(600);
  if (shoot) {
    await save("05_enroll_result", {
      around: [{ css: '[role="dialog"]' }], margin: 20,
      mark: [
        { n: 1, ...D, css: '[class*="bg-info-bg"], [class*="border-info"]', at: "tl" },
        { n: 2, ...D, css: "ul.divide-y", at: "tr" },
        { n: 3, ...D, text: "Done", tag: "button", at: "tr" },
      ],
    });
  }
  await click({ ...D, text: "Done", tag: "button" });
  await sleep(800);
}
const collinsEnrol = ["collins_enrol_1_orange_suit_1998.jpg", "collins_enrol_2_navy_jacket_early.jpg"].map((f) => path.join(faces, "enroll", "collins", f));
await enrol("subject-001", "Example person 1", collinsEnrol, { shoot: true });
await enrol("subject-002", "Example person 2 (street photo, head blurred)", [path.join(samples, "person_A_reference_1.jpg"), path.join(samples, "person_A_reference_2.jpg")]);

await go("/gallery");
await save("06_gallery_people", {
  mark: [
    { n: 1, css: 'main ul button[aria-label^="Open subject-001"]', at: "tl" },
    { n: 2, text: "with a face", tag: "span", at: "br" },
    { n: 3, text: "No face on file", tag: "span", at: "br" },
    { n: 4, css: "main dl", at: "tr" },
  ],
});

// =============================================================================================== 3. check a photo
console.log("3. Check a photo");
await go("/match");
await save("07_match_empty", {
  mark: [
    { n: 1, css: "main .border-dashed", at: "tl" },
    { n: 2, label: "Image is already a person crop", container: ".flex.items-start", at: "tl" },
    { n: 3, text: "Detect people", tag: "button", at: "tr", pad: 2 },
    { n: 4, text: "Run re-identification", tag: "button", at: "br", pad: 2 },
  ],
});

async function matchPhoto(file) {
  await go("/match", 1200);
  await pick({ css: 'input[type="file"]' }, file);
  await setChecked({ label: "Image is already a person crop" }, true);
  return file;
}
async function runMatch() {
  await click({ text: "Run re-identification", tag: "button" });
  await waitText("Ranked candidates", 120000);
  await sleep(1500);
  await fit();
}
await matchPhoto(path.join(faces, "test", "collins", "collins_test_2_suit_jacket_2010.jpg"));
await save("08_match_ready", {
  around: [{ heading: "Query image" }],
  mark: [
    { n: 1, css: 'main section img[alt="Selected query"]', closest: ".flex.items-center", at: "tl" },
    { n: 2, label: "Image is already a person crop", container: ".flex.items-start", at: "tl" },
    { n: 3, text: "Run re-identification", tag: "button", at: "tr" },
  ],
});
await runMatch();
// clean crops of the three answers (no marks) are taken in the loop below; first the annotated MATCH screens
await save("ans_match", { around: [{ heading: "Decision" }], margin: 2 });
await save("09_result_decision", {
  around: [{ heading: "Decision" }], margin: 22,
  mark: [
    { n: 1, ...{ within: { heading: "Decision" } }, css: "span.badge", at: "tl" },
    { n: 2, within: { heading: "Decision" }, css: "p.text-sm", at: "tr" },
    { n: 3, within: { heading: "Decision" }, text: "Selected reference ID", tag: "div", at: "tl" },
    { n: 4, within: { heading: "Decision" }, css: '[role="meter"]', at: "br", pad: 6 },
    { n: 5, within: { heading: "Decision" }, text: "Face threshold", tag: "div", closest: ".bg-surface-2", at: "tr" },
  ],
});
await save("10_result_evidence", {
  around: [{ heading: "Evidence" }], margin: 22,
  mark: [
    { n: 1, within: { heading: "Evidence" }, css: "div.flex.flex-wrap.items-center.gap-2", at: "tl" },
    { n: 2, within: { heading: "Evidence" }, css: '[role="meter"]', nth: 0, at: "tr", pad: 7 },
    { n: 3, within: { heading: "Evidence" }, css: '[role="meter"]', nth: 1, at: "tr", pad: 7 },
    { n: 4, within: { heading: "Evidence" }, css: "figure", at: "tr" },
    { n: 5, within: { heading: "Evidence" }, css: "table", at: "tr" },
  ],
});
await save("11_result_candidates", {
  around: [{ heading: "Ranked candidates" }, { heading: "Export and next steps" }], margin: 22,
  mark: [
    { n: 1, css: 'ol[aria-label="Ranked candidates"] > li', nth: 0, at: "tl" },
    { n: 2, css: 'ol[aria-label="Ranked candidates"] > li', nth: 1, at: "tl" },
    { n: 3, css: '[role="group"][aria-label="Export the decision record"]', at: "tl" },
    { n: 4, text: "Upload another query", tag: "button", at: "tl" },
    { n: 5, text: "Decision history", tag: "a", at: "tr" },
  ],
});
await save("12_result_pictures", {
  around: [{ heading: "Detection preview" }, { heading: "Query versus closest reference" }], margin: 22,
  mark: [
    { n: 1, css: 'main button[aria-label^="Face found"]', at: "tl" },
    { n: 2, css: 'main [role="img"][aria-label^="Query person"], main img[alt="Query person"]', at: "br" },
    { n: 3, css: 'main [aria-label^="Closest reference image"], main img[alt^="Closest reference image"]', at: "tr" },
  ],
});

// the three answers, one picture of the Decision card each
await matchPhoto(path.join(faces, "test", "ride", "ride_stranger_2_blue_shirt_1983.jpg"));
await runMatch();
await save("ans_unknown", { around: [{ heading: "Decision" }], margin: 2 });
await save("13_unknown_evidence", {
  around: [{ heading: "Evidence" }], margin: 22,
  mark: [
    { n: 1, within: { heading: "Evidence" }, css: '[role="meter"]', nth: 0, at: "tr", pad: 7 },
    { n: 2, within: { heading: "Evidence" }, css: "figure", at: "tl" },
  ],
});
await matchPhoto(path.join(samples, "query_1_same_person.jpg"));
await runMatch();
await save("ans_review", { around: [{ heading: "Decision" }], margin: 2 });
await save("14_review_candidates", {
  around: [{ heading: "Ranked candidates" }], margin: 22,
  mark: [
    { n: 1, within: { heading: "Ranked candidates" }, css: '[role="status"]', at: "tl" },
    { n: 2, text: "Review candidates", tag: "button", at: "tl" },
  ],
});
await click({ text: "Review candidates", tag: "button" });
await page.waitForSelector('[role="dialog"]');
await sleep(1500);
await page.setViewport({ width: 1440, height: 1000, deviceScaleFactor: SCALE });
await sleep(500);
await save("15_review_dialog", {
  around: [{ css: '[role="dialog"]' }], margin: 20,
  mark: [
    { n: 1, ...D, css: '[role="status"]', at: "tl" },
    { n: 2, ...D, css: "div.grid > div", nth: 0, at: "tr" },
    { n: 3, ...D, css: "ul", at: "tr" },
  ],
});
await page.keyboard.press("Escape");

// =============================================================================================== 4. several people
console.log("4. A photo with several people");
await go("/match", 1200);
await pick({ css: 'input[type="file"]' }, path.join(samples, "scene_B_station_square.jpg"));
await click({ text: "Detect people", tag: "button" });
await page.waitForSelector('button[aria-label^="Person 1,"]', { timeout: 90000 });
await sleep(1200);
await save("16_detect_people", {
  mark: [
    { n: 1, text: "Detect people", tag: "button", at: "tr", pad: 2 },
    { n: 2, css: "main .relative.mx-auto", at: "tl" },
    { n: 3, text: "Person 1 · detector", tag: "button", closest: "div", at: "tl" },
    { n: 4, text: "Run re-identification", tag: "button", at: "br", pad: 2 },
    { n: 5, label: "Match everyone found", container: ".flex.items-start", at: "tl" },
  ],
});
await setChecked({ label: "Match everyone found" }, true);
await click({ text: "Run re-identification", tag: "button" });
await waitText("Ranked candidates", 180000);
await sleep(1800);
await save("17_everyone_result", {
  mark: [
    { n: 1, label: "Match everyone found", container: ".flex.items-start", at: "tl" },
    { n: 2, css: "main .relative.mx-auto", at: "tl" },
    { n: 3, within: { heading: "Decision" }, css: "span.badge", at: "tl" },
    { n: 4, text: "Select a box to see", tag: "p", at: "bl" },
  ],
});

// =============================================================================================== 5. video
console.log("5. Video");
await go("/video", 1500);
await pick({ css: 'input[aria-label="Choose a video file"]' }, path.join(samples, "clip_faces.avi"));
await sleep(1200);
await page.setViewport({ width: 1440, height: 1100, deviceScaleFactor: SCALE });
await sleep(600);
await save("18_video_upload", {
  around: [{ heading: "Analyse a video" }], margin: 18,
  mark: [
    { n: 1, css: 'form[aria-label="Video analysis settings"] .border-dashed', at: "tl" },
    { n: 2, css: "video", at: "tr" },
    { n: 3, label: "Take one frame every", container: ".flex.flex-col", at: "bl" },
    { n: 4, label: "Stop after this many", container: ".flex.flex-col", at: "br" },
    { n: 5, text: "Analyse video", tag: "button", at: "tr" },
  ],
});
await click({ text: "Analyse video", tag: "button" });
await waitText("Timeline of sampled frames", 240000);
await sleep(3500);
await fit();
await save("19_video_result", {
  around: [{ heading: "clip_faces.avi" }, { heading: "Decisions in this frame" }], margin: 24,
  mark: [
    { n: 1, heading: "clip_faces.avi", at: "tl" },
    { n: 2, heading: "Timeline of sampled frames", at: "tl" },
    { n: 3, heading: "Frame 1", startsWith: true, at: "tl" },
    { n: 4, heading: "Decisions in this frame", at: "tl" },
  ],
});

// =============================================================================================== 6. history
console.log("6. History");
await go("/history", 1800);
await save("20_history", { mark: [{ n: 1, css: "main table, main ul", at: "tl" }] });

// =============================================================================================== 7. manage people
console.log("7. Manage people");
await go("/gallery", 1500);
await save("21_gallery_buttons", {
  around: [{ text: "Enroll identity", tag: "button", nth: 0 }, { text: "Reset demo gallery", tag: "button" }], margin: 32,
  mark: [
    { n: 1, text: "Enroll identity", tag: "button", nth: 0, at: "tl" },
    { n: 2, text: "Rebuild embeddings", tag: "button", at: "tl" },
    { n: 3, text: "Analyse faces", tag: "button", at: "tl" },
    { n: 4, text: "Reset demo gallery", tag: "button", at: "tr" },
  ],
});
await click({ css: 'main ul button[aria-label^="Open subject-001"]' });
await page.waitForSelector('[role="dialog"]');
await sleep(2000);
await page.setViewport({ width: 1440, height: 1100, deviceScaleFactor: SCALE });
await sleep(600);
await save("22_person_dialog", {
  around: [{ css: '[role="dialog"]' }], margin: 20,
  mark: [
    { n: 1, ...D, text: "with a face", tag: "span", at: "tr" },
    { n: 2, ...D, css: 'ul[aria-label="Reference images"]', at: "tl" },
    { n: 3, ...D, text: "Add images", tag: "button", at: "bl" },
    { n: 4, ...D, text: "Delete identity", tag: "button", at: "tr" },
  ],
});
await page.keyboard.press("Escape");

// =============================================================================================== 8. settings
console.log("8. Settings");
await go("/settings?tab=model", 2200);
await fit(3200);
await save("23_settings_policy", {
  around: [{ heading: "Active decision policy" }], margin: 22,
  mark: [
    { n: 1, css: "dl dd", nth: 0, within: { heading: "Active decision policy" }, at: "tr" },
    { n: 2, css: "dl dd", nth: 1, within: { heading: "Active decision policy" }, at: "tr" },
    { n: 3, css: "span.badge", within: { heading: "Active decision policy" }, at: "tl" },
    { n: 4, css: '[role="status"]', within: { heading: "Active decision policy" }, at: "tl" },
  ],
});
await save("24_settings_rules", {
  around: [{ heading: "Experimental: set the rules by hand" }], margin: 22,
  mark: [
    { n: 1, within: { heading: "Experimental: set the rules by hand" }, label: "Matching mode", at: "tr" },
    { n: 2, within: { heading: "Experimental: set the rules by hand" }, label: "Face threshold", at: "tr" },
    { n: 3, within: { heading: "Experimental: set the rules by hand" }, text: "Save settings", tag: "button", at: "tr" },
  ],
});

// =============================================================================================== 9. summary screen
console.log("9. Command Center after use");
await go("/", 2500);
await page.evaluate(() => document.getElementById("status-title").scrollIntoView({ block: "start" }));
await page.evaluate(() => window.scrollBy(0, -80));
await sleep(700);
await save("25_command_center_used", {
  mark: [
    { n: 1, css: ".grid > .card", nth: 4, at: "tl" },
    { n: 2, css: ".grid > .card", nth: 5, at: "tl" },
    { n: 3, css: ".grid > .card", nth: 6, at: "tl" },
    { n: 4, heading: "Recent decisions", at: "tl" },
  ],
});
await go("/how-it-works", 1500);
await save("26_how_it_works", {});

await browser.close();
console.log(`\n${saved.length} pictures saved to ${out}`);
if (problems.length) {
  console.log("\nMARKS THAT COULD NOT BE PLACED (fix the finders, then run again):");
  problems.forEach((p) => console.log("  - " + p));
}
