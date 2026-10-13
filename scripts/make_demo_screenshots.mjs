/*
 * Take the screenshots used in demo/DEMO_GUIDE.html.
 *
 * In plain words: it opens the REAL web interface of a running server in a headless browser, does exactly what the
 * guide tells a person to do (upload the sample pictures, click the buttons) and saves what is on the screen. Nothing
 * is drawn or edited: each PNG is a photograph of the live page.
 *
 * Use a CLEAN server instance, so no one's real gallery appears in the pictures:
 *     $env:REID_DATA_DIR = "D:\some\empty\folder"; powershell -File scripts\start.ps1 -Port 8765
 *     python demo\run_demo.py --base-url http://127.0.0.1:8765 --lab      (creates the example person, a video job and a lab run)
 *     node scripts\make_demo_screenshots.mjs http://127.0.0.1:8765
 *
 * Needs puppeteer-core (just the remote-control library, no browser download) and Microsoft Edge or Chrome:
 *     cd .tools\shots; npm install puppeteer-core
 */
import { createRequire } from "node:module";
import { existsSync, mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const require = createRequire(path.join(root, ".tools", "shots", "package.json"));
const puppeteer = require("puppeteer-core");

const base = (process.argv[2] ?? "http://127.0.0.1:8765").replace(/\/$/, "");
const samples = path.join(root, "demo", "samples");
const out = path.join(root, "demo", "screenshots");
mkdirSync(out, { recursive: true });

const browserCandidates = [
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
];
const executablePath = browserCandidates.find(existsSync);
if (!executablePath) throw new Error("Neither Edge nor Chrome was found.");

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// The browser profile goes inside the project (not the system temp folder), so a full system drive cannot break the run.
const profile = path.join(root, ".tools", "tmp", "edge-profile-shots");
mkdirSync(profile, { recursive: true });
const browser = await puppeteer.launch({ executablePath, headless: true, userDataDir: profile, args: ["--no-sandbox"] });
const page = await browser.newPage();
await page.setCacheEnabled(false); // always the newest build of the interface
await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
await page.emulateMediaFeatures([{ name: "prefers-reduced-motion", value: "reduce" }]);

let view = { width: 1440, height: 900, deviceScaleFactor: 1 };
async function setView(next) {
  view = { ...view, ...next };
  await page.setViewport(view);
}
async function open(route, settle = 1800) {
  await setView({ height: view.width > 600 ? 900 : 844 });
  await page.goto(base + route, { waitUntil: "networkidle0" });
  await sleep(settle);
}
/** The whole page as one picture: make the window as tall as the content (a "full page" shot breaks sticky headers). */
async function tallShot(name, maxHeight = 4200) {
  await sleep(400);
  const height = await page.evaluate(() => Math.ceil(document.documentElement.scrollHeight));
  await setView({ height: Math.min(Math.max(height, view.height), maxHeight) });
  await sleep(600);
  await page.screenshot({ path: path.join(out, name) });
  console.log("  saved", name);
}
/** One card of the page (found by the id of its heading), as a picture. */
async function cardShot(name, labelledBy) {
  await sleep(400);
  const card = await page.$(`[aria-labelledby="${labelledBy}"]`);
  if (!card) throw new Error(`card ${labelledBy} not found`);
  await card.screenshot({ path: path.join(out, name) });
  console.log("  saved", name);
}
async function shot(name, options = {}) {
  await sleep(400);
  await page.screenshot({ path: path.join(out, name), ...options });
  console.log("  saved", name);
}
/** Click the first element whose visible text contains `text` (buttons, tabs, labels). */
async function clickText(text, tag = "button") {
  const handle = await page.evaluateHandle(
    (t, tg) => [...document.querySelectorAll(tg)].find((el) => el.textContent.trim().includes(t) && el.offsetParent !== null),
    text, tag);
  const element = handle.asElement();
  if (!element) throw new Error(`No <${tag}> containing "${text}" on ${page.url()}`);
  await element.click();
}
async function setCheckbox(labelText, wanted) {
  const handle = await page.evaluateHandle((t) => {
    const label = [...document.querySelectorAll("label")].find((l) => l.textContent.includes(t));
    return label?.querySelector("input[type=checkbox]") ?? (label?.htmlFor ? document.getElementById(label.htmlFor) : null);
  }, labelText);
  const input = handle.asElement();
  if (!input) throw new Error(`Checkbox "${labelText}" not found`);
  const now = await input.evaluate((el) => el.checked);
  if (now !== wanted) await input.click();
}
async function upload(file) {
  const input = await page.$("input[type=file]");
  await input.uploadFile(path.join(samples, file));
  await sleep(700);
}
async function waitForText(text, timeout = 60000) {
  await page.waitForFunction((t) => document.body.innerText.includes(t), { timeout }, text);
}

console.log("Screens (desktop 1440x900, dark theme)");
await open("/how-it-works", 1500);
await tallShot("12_how_it_works.png");

await open("/gallery");
await tallShot("02_gallery.png");
// open the first person: shows, per reference photo, whether a usable face is on file
await clickText("Open demo-collins", "button").catch(() => {});
await sleep(1500);
await shot("02b_gallery_person_faces.png");

// ---- Match Studio, one query picture at a time (cropped pictures, so the detector is skipped)
async function matchOne(file, name) {
  await open("/match", 1200);
  await upload(file);
  await setCheckbox("Image is already a person crop", true);
  await clickText("Run re-identification");
  await waitForText("Ranked candidates");
  await sleep(1200);
  await tallShot(name);
}
// Face + body: the same person in different clothes (MATCH, decided by the face); a stranger (UNKNOWN); then pictures with no usable face.
await matchOne("faces/test/collins/collins_test_2_suit_jacket_2010.jpg", "03_match_studio_MATCH.png");
await matchOne("faces/test/ride/ride_stranger_2_blue_shirt_1983.jpg", "04_match_studio_UNKNOWN.png");
await matchOne("query_1_same_person.jpg", "05_match_studio_REVIEW_no_face.png");
await matchOne("query_3_blurry.jpg", "05b_match_studio_REVIEW_blurry.png");

// ---- Match Studio, a busy scene: everyone is found and decided separately
await open("/match", 1200);
await upload("scene_B_station_square.jpg");
await setCheckbox("Image is already a person crop", false);
await setCheckbox("Match everyone found in the image", true);
await clickText("Run re-identification");
await waitForText("Ranked candidates", 120000);
await sleep(1500);
await tallShot("06_match_studio_busy_scene.png");

// ---- Video Explorer: upload the clip, wait for the result
await open("/video", 1200);
const videoInput = await page.$("input[type=file]");
await videoInput.uploadFile(path.join(samples, "clip_faces.avi"));
await sleep(1200);
await tallShot("07a_video_chosen.png");
await clickText("Analyse video");
await sleep(1500);
await page.waitForFunction(() => !/\brunning\b|\bqueued\b/.test(document.body.innerText), { timeout: 120000 });
await sleep(3500);
await tallShot("07b_video_result.png");

// ---- Lookalike Failure Lab (the experiment was run by demo/run_demo.py --lab)
await open("/lookalike", 2500);
await tallShot("08a_lookalike_top.png");
async function clickTab(label) {
  const handle = await page.evaluateHandle((t) => [...document.querySelectorAll('[role="tab"]')].find((el) => el.textContent.trim().startsWith(t)), label);
  const element = handle.asElement();
  if (!element) throw new Error(`No tab "${label}"`);
  await element.click();
  await sleep(1500);
}
for (const [tab, file] of [["Challenge set", "08b_lookalike_challenge.png"], ["Mistakes", "08c_lookalike_mistakes.png"], ["Threshold sandbox", "08d_lookalike_sandbox.png"]]) {
  await setView({ height: 900 });
  await clickTab(tab);
  await cardShot(file, "lab-detail");
}
await open("/evaluation", 2000);
await tallShot("09_evaluation_lab.png");

await open("/settings?tab=model", 2200);
await tallShot("10a_settings_model_and_policy.png");
await open("/settings?tab=system", 2200);
await tallShot("10b_settings_system.png");

await open("/", 2500);
await tallShot("01_command_center.png");

// ---- A phone-sized view of the same screen, to show the interface adapts
console.log("Phone view (390x844)");
await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
view = { width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true };
await open("/match", 1200);
await upload("faces/test/collins/collins_test_2_suit_jacket_2010.jpg");
await setCheckbox("Image is already a person crop", true);
await clickText("Run re-identification");
await waitForText("Ranked candidates");
await sleep(1200);
const sideways = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
console.log(sideways > 1 ? `  WARNING: the phone view scrolls sideways by ${sideways}px` : "  phone view: no sideways scrolling");
await tallShot("11_phone_match_studio.png", 3000);

await browser.close();
console.log("Done ->", out);



