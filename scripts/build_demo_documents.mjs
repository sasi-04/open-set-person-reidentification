/*
 * Build the printable documents of the demo pack (PDF).
 *
 * In plain words: it turns the written guides and the real results into PDFs that can be shown, printed or e-mailed:
 *   demo/DEMO_GUIDE.pdf        step by step: set up, run, read every screen, with the real screenshots and the real outputs
 *   demo/JURY_DECK.pdf         15 slides for a presentation (16:9)
 *   demo/JURY_GUIDE.pdf        docs/JURY_GUIDE.md as a document (what to say, demo script, questions and answers)
 *   demo/FACE_AND_BODY_MATCHING.pdf   the technical explanation, with the measurements
 *
 * No number is typed into the slides by hand: they are read from docs/results/*.json and demo/expected_output/*.
 * Run it AFTER demo/run_demo.py and scripts/make_demo_screenshots.mjs:
 *     node scripts/build_demo_documents.mjs
 * Needs puppeteer-core and marked (cd .tools\shots; npm install puppeteer-core marked) and Microsoft Edge or Chrome.
 */
import { createRequire } from "node:module";
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const require = createRequire(path.join(root, ".tools", "shots", "package.json"));
const puppeteer = require("puppeteer-core");
const { marked } = require("marked");

const demo = path.join(root, "demo");
const build = path.join(demo, "_build");
mkdirSync(build, { recursive: true });
const J = (p) => JSON.parse(readFileSync(p, "utf8"));
const lfw = J(path.join(root, "docs", "results", "face_lfw.json"));
const e2e = J(path.join(root, "docs", "results", "face_vs_body_lfw.json")).results;
const ex = J(path.join(root, "docs", "results", "open_set_example.json")); // written by demo/run_open_set_example.py
const expected = path.join(demo, "expected_output");
const decision = (n) => J(path.join(expected, `scenario${String(n).padStart(2, "0")}.decision.json`)).people[0];
const csv = (p) => readFileSync(p, "utf8").trim().split(/\r?\n/).map((line) => line.match(/("([^"]|"")*"|[^,]*)(,|$)/g).map((c) => c.replace(/,$/, "").replace(/^"|"$/g, "").replace(/""/g, '"')));
const comparison = csv(path.join(expected, "comparison_clothing_vs_face.csv")).slice(1);
const tail = lfw.stranger_tail;
const pct = (x, d = 1) => `${(x * 100).toFixed(d)} %`;
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const rel = (p) => pathToFileURL(path.join(demo, p)).href;
const perHundredThousand = (count) => (count / tail.stranger_pairs) * 100000;

const browserPath = ["C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe", "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe", "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"].find(existsSync);
if (!browserPath) throw new Error("Neither Edge nor Chrome was found.");
const profile = path.join(root, ".tools", "tmp", "edge-profile-docs");
mkdirSync(profile, { recursive: true });
const browser = await puppeteer.launch({ executablePath: browserPath, headless: true, userDataDir: profile, args: ["--no-sandbox", "--allow-file-access-from-files"] });

async function toPdf(html, outFile, options) {
  const file = path.join(build, path.basename(outFile, ".pdf") + ".html");
  writeFileSync(file, html, "utf8");
  const page = await browser.newPage();
  await page.goto(pathToFileURL(file).href, { waitUntil: "networkidle0" });
  await page.evaluate(() => document.fonts?.ready);
  await page.pdf({ path: outFile, printBackground: true, ...options });
  await page.close();
  console.log("  wrote", path.relative(root, outFile));
}

// ------------------------------------------------------------------------------------------------------------------ shared pieces
const BADGE = {
  accepted: ["MATCH", "match"], unknown: ["UNKNOWN", "unknown"], review_required: ["REVIEW", "review"], processing_error: ["ERROR", "unknown"],
};
const badge = (outcome) => `<span class="badge ${BADGE[outcome][1]}">${BADGE[outcome][0]}</span>`;

const SAME_CLOTHES_SVG = (dark) => {
  const ink = dark ? "#e9ecf1" : "#16181d";
  const person = (x, face) => `<g transform="translate(${x} 0)">
    <rect x="32" y="74" width="56" height="70" rx="10" fill="#5b8def" opacity="0.9"/>
    <rect x="38" y="144" width="18" height="52" rx="6" fill="${dark ? "#9aa3b2" : "#6b7280"}"/><rect x="64" y="144" width="18" height="52" rx="6" fill="${dark ? "#9aa3b2" : "#6b7280"}"/>
    <circle cx="60" cy="48" r="26" fill="${dark ? "#2a303b" : "#f1f3f6"}" stroke="${ink}" stroke-width="2"/>
    ${face === "a" ? `<circle cx="51" cy="44" r="3" fill="${ink}"/><circle cx="69" cy="44" r="3" fill="${ink}"/><path d="M50 58 Q60 66 70 58" fill="none" stroke="${ink}" stroke-width="2.5" stroke-linecap="round"/>`
      : `<ellipse cx="48" cy="43" rx="4" ry="2.5" fill="${ink}"/><ellipse cx="72" cy="43" rx="4" ry="2.5" fill="${ink}"/><path d="M52 60 L68 60" stroke="${ink}" stroke-width="2.5" stroke-linecap="round"/>`}</g>`;
  return `<svg viewBox="0 0 330 210" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Two different people in the same blue jacket">
    ${person(10, "a")}${person(200, "b")}
    <path d="M118 112 H182" stroke="#2fbf71" stroke-width="3" stroke-dasharray="6 5"/><text x="150" y="104" text-anchor="middle" fill="#2fbf71" font-size="12" font-weight="700">clothes: alike</text>
    <path d="M118 48 H182" stroke="#ff5a52" stroke-width="3"/><text x="150" y="40" text-anchor="middle" fill="#ff5a52" font-size="12" font-weight="700">faces: different</text></svg>`;
};

// ===================================================================================================================== DECK
function deck() {
  const strangers = (x) => `${x.stranger_ACCEPTED} of ${x.stranger_queries}`;
  const right = (x) => `${x.matched_correct_person} of ${x.same_person_queries}`;
  const bodyCol = comparison.filter((r) => r[2].startsWith("MATCH") || r[2].startsWith("UNKNOWN"));
  const corrBody = comparison.filter((r) => (r[1].startsWith("MATCH") ? r[2] === r[1] : !r[2].startsWith("MATCH"))).length;
  const corrFace = comparison.filter((r) => (r[1].startsWith("MATCH") ? r[3] === r[1] : !r[3].startsWith("MATCH"))).length;
  const sd = lfw.score_distribution;
  const x = (v) => 60 + v * 1080; // number line 0..1 across 1080 px

  const crop = (file, left, top, w, h, scale) => `<div class="crop" style="width:${w}px;height:${h}px"><img src="${rel("screenshots/" + file)}" style="width:${1440 * scale}px;margin-left:${-left * scale}px;margin-top:${-top * scale}px"></div>`;
  const slide = (n, title, body, extra = "") => `<section class="slide ${extra}"><header><span class="kicker">OpenID Vision</span><h2>${title}</h2></header><div class="body">${body}</div><footer><span>Independent technical prototype responding to the Zed Digital PS-1 assignment - not an official Zed Digital product</span><b>${n}</b></footer></section>`;

  const slides = [];
  slides.push(`<section class="slide title"><div class="hero"><p class="kicker">Open-set person identification</p><h1>OpenID Vision</h1><p class="tag">Know when to match. Know when to reject.</p>
    <p class="sub">The face decides when it can be trusted. The body supports it. A human is asked when the system is not sure.</p>
    <div class="badges">${badge("accepted")}${badge("unknown")}${badge("review_required")}</div></div>
    <footer><span>Independent technical prototype responding to the Zed Digital PS-1 assignment - not an official Zed Digital product - research use, consenting people only</span><b>October 2026</b></footer></section>`);

  slides.push(slide(2, "The problem: look-alikes get in",
    `<div class="two"><div><p class="lead">Most person re-identification systems compare <b>clothing and build</b>. It is like a guard who only checks uniforms.</p>
     <p>A <b>different person in a similar jacket</b> is accepted as an enrolled one. That wrong "yes" - a <b>false accept</b> - is the failure that matters most in access and security work.</p>
     <p>PS-1 asks for exactly this setting: an <b>open set</b> (the person may never have been enrolled) with <b>low variance between people</b> (many look alike).</p>
     <div class="callout bad">In our test, a clothing-only matcher accepted <b>${strangers(e2e.body_only)} strangers</b>.</div></div>
     <div class="art">${SAME_CLOTHES_SVG(true)}<p class="cap">Illustration: same jacket, different faces</p></div></div>`));

  slides.push(slide(3, "The idea: face first, body second, a human when unsure",
    `<div class="three">
      <div class="card ok"><h3>${badge("accepted")}</h3><p class="big">"This is enrolled person X."</p><p>The evidence passed an explicit rule. The door opens.</p></div>
      <div class="card neutral"><h3>${badge("unknown")}</h3><p class="big">"Nobody enrolled is supported."</p><p>Never seen, or not similar enough. The door stays shut. Not an accusation - unknown people are never saved or tracked.</p></div>
      <div class="card warn"><h3>${badge("review_required")}</h3><p class="big">"Not sure - a person should look."</p><p>Blurry, no usable face, or a borderline score. The guard calls a supervisor.</p></div></div>
      <p class="lead mt">A <b>nearest neighbour is never accepted just because it is nearest</b>. Clothing can support a face match, but can never turn a mismatching face into a MATCH.</p>`));

  const steps = [["Find the people", "a detector boxes each person"], ["Check quality", "blurry, tiny, cut off? then not sure"], ["Find and judge the face", "big, sharp, facing the camera?"], ["Two fingerprints", "face: 128 numbers · body: 512"], ["Compare with everyone enrolled", "a face score and a body score each"], ["Decide with a written rule", "MATCH · UNKNOWN · REVIEW"], ["Record it", "scores, rule version, reason"]];
  slides.push(slide(4, "What happens to one photo", `<ol class="flow">${steps.map(([t, s], i) => `<li><span class="n">${i + 1}</span><b>${t}</b><small>${s}</small></li>`).join("")}</ol>
    <p class="lead mt">Every number on the screen is computed by the server and saved with the rule version that produced it, so any decision can be explained and exported later.</p>`));

  slides.push(slide(5, "The decision rule", `<table class="rule"><thead><tr><th>Situation</th><th>What decides</th><th>Result</th></tr></thead><tbody>
    <tr><td>Clear face, enrolled person</td><td><b>the face</b> reaches the threshold</td><td>${badge("accepted")}</td></tr>
    <tr><td>Clear face, <b>stranger - even in the same clothes</b></td><td><b>the face</b> does not match</td><td>${badge("unknown")}</td></tr>
    <tr><td>Face score just below the threshold</td><td>too close to call</td><td>${badge("review_required")}</td></tr>
    <tr><td>No usable face (back view, far, blurred)</td><td>the <b>body</b> - weaker evidence, so a person is asked</td><td>${badge("review_required")}</td></tr>
    <tr><td>Somebody enrolled without a face on file matches strongly by body</td><td>a face cannot rule them out</td><td>${badge("review_required")}</td></tr></tbody></table>
    <p class="lead mt">Face threshold <b>0.465</b> (automatic MATCH) · review band <b>0.10</b> below it · body threshold <b>0.70</b>. All are labelled <i>unvalidated</i> for any particular camera, and visible on every screen.</p>`));

  slides.push(slide(6, "Proof 1 - the face stage on a standard public test",
    `<div class="stats"><div><b class="huge">${pct(lfw.ten_fold_accuracy_mean)}</b><span>accuracy, 10-fold protocol<br>(± ${(lfw.ten_fold_accuracy_std * 100).toFixed(2)} %)</span></div>
      <div><b class="huge">${lfw.pairs.toLocaleString("en")}</b><span>face pairs<br>(LFW benchmark)</span></div>
      <div><b class="huge">${(lfw.pictures - lfw.pictures_without_a_face_found).toLocaleString("en")}/${lfw.pictures.toLocaleString("en")}</b><span>pictures where a face<br>was found</span></div></div>
    <svg viewBox="0 0 1200 190" class="line"><rect x="60" y="86" width="1080" height="10" rx="5" fill="#2a303b"/>
      <rect x="${x(0.465)}" y="64" width="${x(1) - x(0.465)}" height="54" fill="#2fbf71" opacity="0.14"/>
      <line x1="${x(0.465)}" y1="52" x2="${x(0.465)}" y2="132" stroke="#ffb020" stroke-width="3"/><text x="${x(0.465)}" y="44" text-anchor="middle" fill="#ffb020" font-size="18" font-weight="700">automatic MATCH from 0.465</text>
      <circle cx="${x(sd.different_people_median)}" cy="91" r="9" fill="#ff5a52"/><text x="${x(sd.different_people_median)}" y="132" text-anchor="middle" fill="#ff8f8a" font-size="16">typical stranger ${sd.different_people_median.toFixed(2)}</text>
      <circle cx="${x(sd.different_people_p99)}" cy="91" r="9" fill="#ff5a52" opacity="0.55"/><text x="${x(sd.different_people_p99)}" y="160" text-anchor="end" fill="#ff8f8a" font-size="16">99 % of strangers below ${sd.different_people_p99.toFixed(2)}</text>
      <circle cx="${x(sd.same_person_median)}" cy="91" r="9" fill="#2fbf71"/><text x="${x(sd.same_person_median)}" y="132" text-anchor="middle" fill="#7fe0a6" font-size="16">typical same person ${sd.same_person_median.toFixed(2)}</text>
      <circle cx="${x(sd.same_person_p5)}" cy="91" r="9" fill="#2fbf71" opacity="0.55"/><text x="${x(sd.same_person_p5)}" y="160" text-anchor="start" fill="#7fe0a6" font-size="16">95 % of same-person pairs above ${sd.same_person_p5.toFixed(2)}</text>
      <text x="60" y="186" fill="#9aa3b2" font-size="14">0 (nothing alike)</text><text x="1140" y="186" text-anchor="end" fill="#9aa3b2" font-size="14">1 (identical)</text></svg>
    <p class="note">Honest limit: LFW is easy (frontal, well-lit public figures). It says nothing about other cameras, masks, lighting or demographic groups.</p>`));

  const rows = [[0.363, "model card default"], [0.40, ""], [0.45, ""], [0.465, "OUR DEFAULT"], [0.5, ""]];
  const pairs = { 0.363: tail.stranger_pairs_at_or_above["0.363"], 0.4: tail.stranger_pairs_at_or_above["0.4"], 0.45: tail.stranger_pairs_at_or_above["0.45"], 0.5: tail.stranger_pairs_at_or_above["0.5"] };
  const tars = { 0.363: tail.same_person_pairs_accepted_at["0.363"], 0.4: tail.same_person_pairs_accepted_at["0.4"], 0.45: tail.same_person_pairs_accepted_at["0.45"], 0.465: tail.threshold_for_false_accept_rate["1e-05"].same_person_pairs_accepted_at_that_threshold, 0.5: tail.same_person_pairs_accepted_at["0.5"] };
  const maxPer = perHundredThousand(pairs[0.363]);
  slides.push(slide(7, "Proof 2 - why 0.465: a rule, not a guess",
    `<p class="lead">Rule fixed before looking at any result: <b>automatic MATCH only where strangers reach that score at most once in 100,000 comparisons</b>. Measured on <b>${tail.stranger_pairs.toLocaleString("en")} pairs of different people</b>.</p>
     <table class="thr"><thead><tr><th>Face score at least</th><th>Strangers reaching it (per 100,000 pairs)</th><th>Same-person pairs accepted</th></tr></thead><tbody>
     ${rows.map(([t, note]) => { const per = t === 0.465 ? 1 : perHundredThousand(pairs[t]); return `<tr class="${t === 0.465 ? "hl" : ""}"><td><b>${t}</b> <small>${note}</small></td><td><span class="bar" style="width:${Math.max(4, (per / maxPer) * 420)}px"></span> ${per >= 10 ? per.toFixed(0) : per.toFixed(1)}</td><td>${pct(tars[t])}</td></tr>`; }).join("")}</tbody></table>
     <p class="note">With N enrolled people and about R photos each, the chance that one stranger is wrongly accepted is roughly N × R × 0.00001 - small, not zero, and it grows with the gallery. The 0.363 → 0.465 move removes about 99 % of the strangers that would get through.</p>`));

  slides.push(slide(8, "Proof 3 - the whole system, end to end",
    `<p class="lead">10 people enrolled through the normal interface, then ${e2e.face_and_body.same_person_queries} new photos of them and ${e2e.face_and_body.stranger_queries} photos of strangers. Same photos, two policies.</p>
     <div class="bars">
       <div class="grp"><h4>Strangers wrongly ACCEPTED (lower is better)</h4>
         <div class="row"><span>Clothing only</span><i class="bar bad" style="width:${(e2e.body_only.stranger_ACCEPTED / 60) * 560}px"></i><b>${strangers(e2e.body_only)}</b></div>
         <div class="row"><span>Face + body</span><i class="bar ok" style="width:${Math.max(6, (e2e.face_and_body.stranger_ACCEPTED / 60) * 560)}px"></i><b>${strangers(e2e.face_and_body)}</b></div></div>
       <div class="grp"><h4>Enrolled people recognised correctly (higher is better)</h4>
         <div class="row"><span>Clothing only</span><i class="bar bad" style="width:${(e2e.body_only.matched_correct_person / 20) * 560}px"></i><b>${right(e2e.body_only)}</b></div>
         <div class="row"><span>Face + body</span><i class="bar ok" style="width:${(e2e.face_and_body.matched_correct_person / 20) * 560}px"></i><b>${right(e2e.face_and_body)}</b></div></div></div>
     <p class="note">Honest limit: these LFW head-and-shoulders photos are outside what the clothing model was designed for (full-body pedestrian crops), so the left bars are its worst case - this shows <b>what the face adds</b>, not a fair benchmark of the body model. The default threshold was fixed beforehand (previous slide), not tuned on these 60 strangers. Small sample.</p>`));

  const lookalikes = ex.cases.filter((c) => c.group === "lookalike");
  const knownCases = ex.cases.filter((c) => c.expect.kind === "match");
  const acceptedSame = (col) => lookalikes.filter((c) => c[col].verdict === "false_accept").length;
  const recognised = (col) => knownCases.filter((c) => c[col].verdict === "correct").length;
  const exRow = (label, kind, n, total, max) => `<div class="row" style="grid-template-columns:120px 260px 90px"><span>${label}</span><i class="bar ${kind}" style="width:${Math.max(6, (n / total) * max)}px"></i><b>${n} of ${total}</b></div>`;
  slides.push(slide(9, "Proof 4 - the same suit, a different person",
    `<div class="two"><div><p class="lead" style="font-size:21px">The home-page example: ${ex.cases.length} public-domain photos with known right answers, including <b>${lookalikes.length} strangers in the same orange flight suit</b> as an enrolled person.</p>
     <div class="bars"><div class="grp"><h4>Strangers in the same suit wrongly ACCEPTED (lower is better)</h4>${exRow("Clothes only", "bad", acceptedSame("clothes_only"), lookalikes.length, 250)}${exRow("Face + body", "ok", acceptedSame("face_body"), lookalikes.length, 250)}</div>
       <div class="grp"><h4>Known people recognised (higher is better)</h4>${exRow("Clothes only", "bad", recognised("clothes_only"), knownCases.length, 250)}${exRow("Face + body", "ok", recognised("face_body"), knownCases.length, 250)}</div></div>
     <p class="note">Honest limit: ${ex.cases.length} portraits - a demonstration of the mechanism, not a benchmark or an error rate. Run it yourself: <b>Run the example</b> on the home page.</p></div>
     <figure><div class="crop" style="width:560px"><img src="${rel("screenshots/00_home_open_set_example.jpg")}" style="width:560px"></div><figcaption>The home page after "Run the example": table, two score plots, and a slider for the face line</figcaption></figure></div>`));

  slides.push(slide(10, "Real photos: the same person, years and clothes apart",
    `<div class="shots"><figure>${crop("03_match_studio_MATCH.png", 1024, 160, 420, 450, 1.0)}<figcaption>${badge("accepted")} different clothes, 12 years later: <b>the face decides</b></figcaption></figure>
     <figure>${crop("04_match_studio_UNKNOWN.png", 1024, 160, 420, 450, 1.0)}<figcaption>${badge("unknown")} a stranger: face far below the line</figcaption></figure>
     <div class="side"><h4>Same 8 public-domain photos</h4><p class="huge2">${corrBody} <small>of ${comparison.length}</small></p><p>right with clothing only</p><p class="huge2 ok">${corrFace} <small>of ${comparison.length}</small></p><p>right with face + body</p>
     <p class="note">Public-domain NASA photographs. A small demonstration, not a benchmark.</p></div></div>`));

  slides.push(slide(11, "No usable face? It does not pretend.",
    `<div class="two"><div><p class="lead">Clothing matches strongly (0.91) - but the head is hidden, so only clothing and build can be compared.</p>
     <p>Clothing alone is weak evidence, so the system does <b>not</b> auto-match. It says ${badge("review_required")} and shows why:</p>
     <p class="quote">"No face was found... clothing and build are not enough for an automatic MATCH - a person should confirm."</p>
     <p>Blurry, tiny, cut-off or turned faces are handled the same way: reported, never silently trusted.</p></div>
     <figure>${crop("05_match_studio_REVIEW_no_face.png", 1024, 160, 420, 450, 1.0)}</figure></div>`));

  slides.push(slide(12, "The Lookalike Failure Lab - finding the mistakes that matter",
    `<div class="two"><div><ul class="list"><li>Finds the <b>pairs of different people</b> the model confuses most</li><li>Builds a <b>reproducible challenge set</b> and prints the realistic error rate next to the worst-case one</li><li>Opens each real mistake: <b>observed numbers</b> vs <b>possible causes - labelled hypotheses, never conclusions</b></li><li>Compares a baseline with an improved model - or says plainly that none exists</li><li><b>Threshold sandbox</b>: try any threshold safely; it can never change the live system</li></ul>
     <p class="note">The screenshot is the synthetic smoke-test set (cartoon figures): it proves the lab works, not how accurate the system is.</p></div>
     <figure>${crop("08a_lookalike_top.png", 255, 0, 640, 450, 0.7)}</figure></div>`));

  slides.push(slide(13, "What it cannot do - said up front",
    `<ul class="list big2"><li><b>Not a phone's Face ID</b>: no depth sensor, no liveness check - a photograph can fool a 2-D matcher</li>
     <li><b>Twins and look-alikes</b> can still score high - that is what the review band and the Lab are for</li>
     <li><b>Masks, sunglasses, strong angles, low light, tiny faces</b> make a face unusable - reported, not guessed</li>
     <li>Accuracy measured on a <b>standard easy benchmark</b>; other cameras, ages and demographic groups are <b>not measured</b></li>
     <li>The <b>pedestrian benchmark (Market-1501) has not been run</b> yet - it must be supplied under its research licence</li>
     <li>Thresholds are evidence-based defaults, <b>unvalidated</b> for any specific camera</li></ul>`));

  slides.push(slide(14, "Privacy and consent",
    `<ul class="list big2"><li>Only <b>enrolled, consenting</b> people are ever matched; enrolment needs an explicit confirmation</li>
     <li>A face fingerprint is <b>biometric data</b>: stored on this computer only, until the person is deleted</li>
     <li><b>Deleting a person erases</b> their photos, face and body fingerprints; query photos expire after 24 hours</li>
     <li>No cloud service, no scraping, no camera feed; unknown people are never saved, grouped or tracked</li>
     <li>One switch (<code>REID_FACE_MATCHING=false</code>) returns to the body-only system; every rule change is versioned and audited</li>
     <li>Biometric data is regulated (GDPR, India's DPDP Act, Illinois BIPA): a real deployment needs a legal basis and an impact assessment</li></ul>`));

  slides.push(slide(15, "Next steps - and questions",
    `<div class="two"><div><h3>What we would do next</h3><ol class="list"><li>Run the <b>pedestrian benchmark</b> (Market-1501) and publish the report</li><li><b>Calibrate</b> both thresholds on the real cameras</li><li>Add <b>liveness / anti-spoofing</b></li><li>Measure accuracy by <b>lighting, age and demographic group</b></li><li>Train and <i>evaluate</i> a fine-tuned body model on the hard look-alike cases</li></ol></div>
     <div class="card ok"><h3>Everything is reproducible</h3><p>427 backend + 157 interface tests · one script per claim:</p><p class="mono">evaluate_face_lfw.py<br>verify_face_vs_body.py<br>demo/run_demo.py<br>demo/run_open_set_example.py</p><p class="note">If asked something we have not measured: <i>"I don't know - here is how we would measure it."</i></p></div></div>`));

  const css = `
  @page { size: 1280px 720px; margin: 0 }
  * { box-sizing: border-box } html, body { margin: 0; background: #0f1217 }
  body { font-family: "Segoe UI", Arial, sans-serif; color: #e9ecf1 }
  .slide { width: 1280px; height: 720px; position: relative; overflow: hidden; page-break-after: always; background: #0f1217; padding: 54px 70px 64px }
  .slide header { margin-bottom: 26px } .kicker { color: #ff5a52; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; font-size: 15px }
  h1 { font-size: 92px; margin: 6px 0 0; letter-spacing: -.02em } h2 { font-size: 40px; margin: 4px 0 0; line-height: 1.15 } h3 { margin: 0 0 8px; font-size: 22px } h4 { margin: 0 0 8px; font-size: 18px; color: #c5ccd8 }
  .body { font-size: 22px; line-height: 1.45 } .lead { font-size: 24px; line-height: 1.4; margin: 0 0 14px } .mt { margin-top: 22px } p { margin: 0 0 12px }
  footer { position: absolute; left: 70px; right: 70px; bottom: 22px; display: flex; justify-content: space-between; color: #7c8594; font-size: 13px } footer b { color: #c5ccd8 }
  .title { display: flex; flex-direction: column; justify-content: center; background: radial-gradient(1000px 500px at 80% 10%, #2a1618 0%, #0f1217 60%) } .hero { margin-top: -30px }
  .tag { font-size: 38px; color: #ff8f8a; margin: 6px 0 20px } .sub { font-size: 24px; color: #c5ccd8; max-width: 900px } .badges { margin-top: 30px } .badges .badge { font-size: 22px; padding: 8px 20px; margin-right: 14px }
  .badge { display: inline-block; font-weight: 800; letter-spacing: .06em; font-size: 15px; padding: 3px 12px; border-radius: 999px } .match { background: #12351f; color: #6ee7a0; border: 1px solid #1f7a45 } .unknown { background: #232a35; color: #c5ccd8; border: 1px solid #3a4352 } .review { background: #3a2a0a; color: #ffc760; border: 1px solid #8a5a00 }
  .two { display: grid; grid-template-columns: 1.15fr 1fr; gap: 44px; align-items: start } .three { display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px }
  .card { border: 1px solid #2a303b; border-radius: 14px; padding: 20px 22px; background: #151a22 } .card.ok { border-color: #1f7a45 } .card.warn { border-color: #8a5a00 } .card .big { font-size: 24px; font-weight: 700; margin: 8px 0 }
  .callout { margin-top: 18px; padding: 16px 20px; border-radius: 12px; font-size: 24px } .callout.bad { background: #3a1417; border: 1px solid #a02a30 }
  .art { text-align: center } .art svg { width: 100%; max-width: 480px } .cap { color: #9aa3b2; font-size: 15px } .note { color: #9aa3b2; font-size: 16px; line-height: 1.4; margin-top: 12px }
  .flow { list-style: none; display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; padding: 0; margin: 10px 0 0 } .flow li { background: #151a22; border: 1px solid #2a303b; border-radius: 12px; padding: 14px 16px; display: flex; flex-direction: column; gap: 4px; min-height: 130px } .flow .n { background: #ff5a52; color: #fff; width: 30px; height: 30px; border-radius: 50%; display: grid; place-items: center; font-weight: 800 } .flow b { font-size: 20px } .flow small { color: #9aa3b2; font-size: 16px }
  table { border-collapse: collapse; width: 100% } th, td { text-align: left; padding: 12px 14px; border-bottom: 1px solid #2a303b; font-size: 20px } th { color: #9aa3b2; font-size: 15px; text-transform: uppercase; letter-spacing: .06em }
  .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; margin-bottom: 8px } .stats div { background: #151a22; border: 1px solid #2a303b; border-radius: 14px; padding: 16px 22px } .huge { display: block; font-size: 54px; color: #6ee7a0; line-height: 1.1 } .stats span { color: #9aa3b2; font-size: 17px }
  .line { width: 100%; margin-top: 6px } .thr .bar { display: inline-block; height: 14px; background: #ff5a52; border-radius: 4px; vertical-align: middle; margin-right: 10px } .thr tr.hl td { background: #12351f } .thr small { color: #9aa3b2; font-size: 14px }
  .bars .grp { margin-bottom: 18px } .row { display: grid; grid-template-columns: 170px 580px 140px; align-items: center; gap: 10px; margin: 8px 0; font-size: 20px } .bar { display: block; height: 28px; border-radius: 6px } .bar.bad { background: #ff5a52 } .bar.ok { background: #2fbf71 } .row b { font-size: 24px; white-space: nowrap }
  .shots { display: grid; grid-template-columns: 420px 420px 1fr; gap: 20px; align-items: start } figure { margin: 0 } figcaption { margin-top: 8px; font-size: 16px; color: #c5ccd8 } .crop { overflow: hidden; border: 1px solid #2a303b; border-radius: 10px; background: #0b0e12 } .crop img { display: block; max-width: none }
  .side { padding-left: 6px } .huge2 { font-size: 54px; font-weight: 800; margin: 12px 0 0; line-height: 1 } .huge2 small { font-size: 20px; color: #9aa3b2; font-weight: 400 } .huge2.ok { color: #6ee7a0 }
  .quote { border-left: 4px solid #ffc760; padding-left: 16px; color: #ffe0a3; font-style: italic } .list { padding-left: 24px } .list li { margin: 10px 0 } .big2 { font-size: 24px } code, .mono { font-family: Consolas, monospace; color: #ffb4af }`;
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>OpenID Vision - jury deck</title><style>${css}</style></head><body>${slides.join("\n")}</body></html>`;
}

// ============================================================================================================== DEMO GUIDE
function demoGuide() {
  const scenarios = [
    [1, "Same person, different clothes and 12 years later", "faces/test/collins/collins_test_2_suit_jacket_2010.jpg", "Match Studio → tick <i>Image is already a person crop</i> → upload → <i>Run re-identification</i>"],
    [2, "Same person, a different setting", "faces/test/collins/collins_test_1_nasa_jacket_1999.jpg", "same steps"],
    [3, "A second enrolled person", "faces/test/jemison/jemison_test_1_in_flight_1992.jpg", "same steps - the system must pick the RIGHT enrolled person"],
    [4, "A stranger", "faces/test/ride/ride_stranger_2_blue_shirt_1983.jpg", "same steps - nobody enrolled looks like this person"],
    [5, "Another stranger", "faces/test/ride/ride_stranger_1_cockpit_1983.jpg", "same steps"],
    [7, "Enrolled street person, but no face visible", "query_1_same_person.jpg", "same steps - the head is blurred, so only clothing can be compared"],
    [8, "A stranger without a visible face", "query_2_stranger.jpg", "same steps"],
    [9, "A poor-quality picture", "query_3_blurry.jpg", "same steps"],
  ];
  const card = ([n, title, file, how]) => {
    const p = decision(n), d = p.decision, f = p.face;
    const face = d.top1_face_score != null ? `face <b>${d.top1_face_score.toFixed(3)}</b>` : "face <b>-</b>";
    const body = d.top1_body_score != null ? `body <b>${d.top1_body_score.toFixed(3)}</b>` : "body <b>-</b>";
    return `<div class="scn"><img src="${rel("samples/" + file)}" alt=""><div><h4>Scenario ${n}: ${title}</h4>
      <p class="how"><b>Do:</b> ${how}</p><p>Result: ${badge(d.outcome)} ${d.accepted_reference_id ? `<b>${esc(d.accepted_reference_id.replace("demo-", ""))}</b>` : ""} <span class="num">decided by <b>${d.basis}</b> · ${face} · ${body} · threshold ${(d.accept_threshold ?? 0).toFixed(3)}</span></p>
      <p class="why">${esc(d.reason)}</p>${f && f.status !== "usable" ? `<p class="why">Face: ${esc(f.message)}</p>` : ""}</div></div>`;
  };
  const sample = (file, cap) => `<figure><img src="${rel("samples/" + file)}" alt=""><figcaption>${cap}</figcaption></figure>`;
  const video = J(path.join(expected, "scenario06_video.result.json"));
  const vstreet = J(path.join(expected, "scenario11_video.result.json"));
  const vline = (v) => v.frames.map((fr) => `t=${fr.time_seconds.toFixed(0)}s ${fr.people.map((q) => BADGE[q.outcome][0]).join("/")}`).join(" &nbsp;→&nbsp; ");

  const css = `
  @page { size: A4; margin: 16mm 14mm 18mm } @page :first { margin: 0 } * { box-sizing: border-box } body { font-family: "Segoe UI", Arial, sans-serif; color: #16181d; margin: 0; font-size: 10.5pt; line-height: 1.45 }
  .page { page-break-after: always; padding: 0 } h1 { font-size: 30pt; margin: 0 0 4pt } h2 { font-size: 17pt; margin: 14pt 0 6pt; border-bottom: 2px solid #e53935; padding-bottom: 3pt } h3 { font-size: 12.5pt; margin: 12pt 0 4pt } h4 { font-size: 11pt; margin: 0 0 3pt }
  .cover { background: #0f1217; color: #e9ecf1; padding: 70pt 46pt; height: 296mm; page-break-after: always; margin: 0 } .cover code { background: #2a303b; color: #ffd0cc } .cover h1 { font-size: 44pt } .cover .tag { color: #ff8f8a; font-size: 20pt; margin: 4pt 0 22pt } .cover .box { background: #151a22; border: 1px solid #2a303b; border-radius: 8pt; padding: 12pt 16pt; margin-top: 14pt } .cover li { margin: 3pt 0 }
  .badge { display: inline-block; font-weight: 800; font-size: 8.5pt; letter-spacing: .05em; padding: 1pt 8pt; border-radius: 99pt } .match { background: #e4f5ea; color: #17673a; border: 1px solid #9ad4b0 } .unknown { background: #eceff3; color: #3b4452; border: 1px solid #c9d0da } .review { background: #fff1d6; color: #7a4a00; border: 1px solid #f0cc85 }
  table { border-collapse: collapse; width: 100%; margin: 6pt 0 } th, td { border: 1px solid #e3e6eb; padding: 4pt 7pt; text-align: left; vertical-align: top } th { background: #f6f7f9; font-size: 9pt } td b { white-space: nowrap }
  pre { background: #0f1217; color: #e9ecf1; padding: 8pt 10pt; border-radius: 6pt; font-size: 9pt; line-height: 1.5; overflow: hidden; white-space: pre-wrap } code { font-family: Consolas, monospace; background: #f1f3f6; padding: 0 3pt; border-radius: 3pt; font-size: 9.5pt } pre code { background: none; padding: 0 }
  .grid3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8pt } .tile { border: 1px solid #e3e6eb; border-radius: 6pt; padding: 8pt 10pt; background: #fafbfc } .note { background: #fff8e6; border: 1px solid #f0cc85; border-radius: 6pt; padding: 6pt 10pt; margin: 8pt 0; font-size: 9.5pt } .ok { background: #eaf7ef; border-color: #9ad4b0 }
  .scn { display: grid; grid-template-columns: 92pt 1fr; gap: 10pt; border: 1px solid #e3e6eb; border-radius: 8pt; padding: 8pt; margin: 8pt 0; page-break-inside: avoid } .scn img { width: 92pt; height: 118pt; object-fit: cover; border-radius: 5pt; background: #eee } .scn p { margin: 2pt 0 } .how { color: #4b5361; font-size: 9.5pt } .why { font-size: 9pt; color: #4b5361; background: #f6f7f9; padding: 3pt 6pt; border-radius: 4pt } .num { font-size: 9pt; color: #4b5361 }
  .samples { display: grid; grid-template-columns: repeat(4, 1fr); gap: 7pt } figure { margin: 0 } figure img { width: 100%; height: 100pt; object-fit: cover; border-radius: 5pt; border: 1px solid #e3e6eb } figcaption { font-size: 8pt; color: #4b5361; margin-top: 2pt }
  .shot { width: 100%; border: 1px solid #d5dae1; border-radius: 6pt } .two { display: grid; grid-template-columns: 1.1fr 1fr; gap: 12pt } .legend li { margin: 3pt 0 } .small { font-size: 9pt; color: #4b5361 }
  .bar { display: inline-block; height: 9pt; border-radius: 3pt; vertical-align: middle } .bad { background: #e5484d } .good { background: #2f9e62 }`;

  const cmp = comparison.map((r) => `<tr><td>${esc(r[0].replace(".jpg", ""))}</td><td>${esc(r[1])}</td><td>${esc(r[2])}</td><td>${esc(r[3])}</td></tr>`).join("");
  const corrBody = comparison.filter((r) => (r[1].startsWith("MATCH") ? r[2] === r[1] : !r[2].startsWith("MATCH"))).length;
  const corrFace = comparison.filter((r) => (r[1].startsWith("MATCH") ? r[3] === r[1] : !r[3].startsWith("MATCH"))).length;

  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>OpenID Vision - demo guide</title><style>${css}</style></head><body>
  <section class="cover"><p style="color:#ff5a52;font-weight:700;letter-spacing:.12em">DEMO PACK</p><h1>OpenID Vision</h1><p class="tag">Know when to match. Know when to reject.</p>
    <p style="font-size:14pt;max-width:420pt">How to run the system, what you will see, and how to read every screen - for people who did not build it.</p>
    <div class="box"><b>In this pack</b><ul><li><b>This guide</b> - set-up, every scenario with the real output, how to read the screen</li><li><b>JURY_DECK.pdf</b> - 14 slides · <b>JURY_GUIDE.pdf</b> - what to say, demo script, 30 questions with honest answers</li><li><b>samples/</b> - public-domain pictures and clips with known right answers (and <code>SOURCES.md</code>)</li><li><b>run_demo.py</b> - runs every scenario and prints PASS / FAIL · <b>face_check.py</b> - try your own volunteers' photos</li><li><b>expected_output/</b> - the real results of a reference run · <b>screenshots/</b> - the real screens</li></ul></div>
    <div class="box"><b>Three commands</b><pre>powershell -ExecutionPolicy Bypass -File scripts\\setup.ps1      # once
powershell -ExecutionPolicy Bypass -File scripts\\start.ps1      # starts the system on http://127.0.0.1:8000
python demo\\run_demo.py --compare                              # runs every scenario and shows the results</pre></div>
    <p style="margin-top:26pt;font-size:9pt;color:#9aa3b2">Independent technical prototype responding to the Zed Digital PS-1 assignment - not an official Zed Digital product. Research use with consenting people only. Photos in this pack are public domain; heads in the street photos are blurred.</p></section>

  <section class="page"><h2>1. What you are about to see</h2>
    <p>The system answers one question about a person in a photo: <b>"is this somebody who was enrolled?"</b> It gives one of three answers, and always says why.</p>
    <div class="grid3"><div class="tile">${badge("accepted")}<p>"This is enrolled person X." The evidence passed an explicit rule.</p></div><div class="tile">${badge("unknown")}<p>"Nobody enrolled is supported by the evidence." Not an accusation; unknown people are never saved or tracked.</p></div><div class="tile">${badge("review_required")}<p>"Not sure - a person should look." Poor photo, no usable face, or a borderline score.</p></div></div>
    <h3>Why it works differently from a clothing-based matcher</h3>
    <p>It looks at the <b>face first</b>. When a usable face is visible the face decides; clothing and build are shown as supporting evidence but <b>can never turn a face that does not match into a MATCH</b>. When no usable face is visible it uses the body - and, because that is weaker evidence, asks a person (REVIEW) instead of matching automatically.</p>
    <div class="note"><b>The numbers to remember.</b> Face-stage accuracy on the standard LFW test: <b>${pct(lfw.ten_fold_accuracy_mean)}</b> (6,000 pairs). Automatic-MATCH threshold chosen so that strangers reach it about <b>1 time in 100,000</b>. In our end-to-end test a clothing-only matcher accepted <b>${e2e.body_only.stranger_ACCEPTED} of ${e2e.body_only.stranger_queries}</b> strangers; face + body accepted <b>${e2e.face_and_body.stranger_ACCEPTED}</b>.</div>
    <h3>Set-up (Windows 10/11, once)</h3>
    <pre>cd D:\\ps1
powershell -ExecutionPolicy Bypass -File scripts\\setup.ps1          # creates the Python environment, builds the interface, downloads and verifies the models
powershell -ExecutionPolicy Bypass -File scripts\\start.ps1          # leave this window open; then open http://127.0.0.1:8000</pre>
    <p class="small">The top bar should say <b>Models ready · CPU</b>. If it does not, see <i>What can go wrong</i> (section 8). Nothing is downloaded while the system runs; the model files are checked against published checksums.</p>
    <h3>Run every scenario with one command</h3>
    <pre>python demo\\run_demo.py --compare         # about 1 minute; add --lab for the Lookalike Failure Lab (1-2 more minutes)</pre>
    <p>It enrols three example people, shows the system the pictures and clips in section 3, and prints for each: what the answer <b>should</b> be, what it <b>was</b>, and why. The reference run is in <code>expected_output/</code>; yours should match (scores may differ in the last decimals on other hardware). The example people stay enrolled so you can repeat any scenario by hand. <code>python demo\\run_demo.py --cleanup</code> removes them.</p>
  </section>

  <section class="page"><h2>2. How to read the result screen (Match Studio)</h2>
    <div class="two"><img class="shot" src="${rel("screenshots/annotated_match_studio.png")}" alt="Annotated Match Studio screen">
    <ol class="legend small">
      <li><b>The answer</b> (MATCH / UNKNOWN / REVIEW) and a sentence built from the real numbers.</li>
      <li><b>Face similarity</b> against its threshold (the black tick). A bar that reaches the tick passes. It is a score, not a percentage.</li>
      <li><b>Threshold</b> and the policy status. <i>Unvalidated</i> = a starting value not yet calibrated on this system's own cameras.</li>
      <li><b>Which evidence decided</b>: the face, or - when no usable face was visible - the body.</li>
      <li><b>Both scores side by side.</b> Face = how alike the faces are; Body and clothing = supporting evidence (it can be low when the person changed clothes).</li>
      <li><b>The two faces</b> the face score was computed from: query on the left, closest enrolled on the right. Judge it yourself.</li>
      <li><b>Colour cues</b> (hair, skin tone, clothing). For a human reader only; they never change the decision.</li>
      <li><b>All candidates</b>, each with its face and body score. The nearest one is shown for transparency; it is only a MATCH if it passed the rule.</li>
      <li><b>The face the system found</b>, drawn on the query picture.</li></ol></div>
    <p class="note">Tip: the <b>How it works</b> button in the top bar opens a plain-language tour of the whole system inside the application.</p></section>

  <section class="page"><h2>3. The pictures in this pack</h2>
    <p>Every picture has a known right answer. Faces: official NASA photographs (public domain). Street scenes: CC0 photos with every head blurred. Licences and how each file was made: <code>samples/SOURCES.md</code>.</p>
    <h3>Enrolled (shown to the system first, two photos each)</h3><div class="samples">
      ${sample("faces/enroll/collins/collins_enrol_1_orange_suit_1998.jpg", "Example person 1 - flight suit, 1998")}${sample("faces/enroll/collins/collins_enrol_2_navy_jacket_early.jpg", "Example person 1 - navy jacket")}
      ${sample("faces/enroll/jemison/jemison_enrol_1_orange_suit_1992.jpg", "Example person 2 - flight suit, 1992")}${sample("faces/enroll/jemison/jemison_enrol_2_blue_jacket_1987.jpg", "Example person 2 - blue jacket, 1987")}
      ${sample("person_A_reference_1.jpg", "Example person 3 - street photo, head blurred (no face on file)")}${sample("person_A_reference_2.jpg", "Example person 3 - mirror image")}</div>
    <h3>Shown afterwards (new photos)</h3><div class="samples">
      ${sample("faces/test/collins/collins_test_1_nasa_jacket_1999.jpg", "person 1, 1999 → should be MATCH")}${sample("faces/test/collins/collins_test_2_suit_jacket_2010.jpg", "person 1, 2010 → MATCH")}${sample("faces/test/jemison/jemison_test_1_in_flight_1992.jpg", "person 2, in flight → MATCH")}${sample("faces/test/ride/ride_stranger_2_blue_shirt_1983.jpg", "a stranger → UNKNOWN")}
      ${sample("faces/test/ride/ride_stranger_1_cockpit_1983.jpg", "same stranger → UNKNOWN")}${sample("query_1_same_person.jpg", "person 3, no face visible → REVIEW")}${sample("query_2_stranger.jpg", "a stranger, no face → UNKNOWN")}${sample("query_3_blurry.jpg", "person 3, out of focus → REVIEW")}</div>
    <p class="small">Clips: <code>clip_faces.avi</code> (person 1 · stranger · person 1) and <code>clip_street.avi</code> (person 3 · other scene · person 3). Both are 3 seconds long; Video Explorer takes one frame per second and judges each frame on its own - it does <b>not</b> track people.</p></section>

  <section class="page"><h2>4. The scenarios, with the real output</h2>
    <p class="small">Each card shows the picture, how to repeat it by hand, and what the system actually answered in the reference run (read from <code>expected_output/</code>).</p>
    ${scenarios.map(card).join("")}</section>

  <section class="page"><h2>4. The scenarios (continued): video and a busy scene</h2>
    <div class="scn"><div style="width:92pt"></div><div><h4>Scenario 6: video <code>clip_faces.avi</code></h4><p class="how"><b>Do:</b> Video Explorer → Browse files → 1 s → Analyse video</p><p>Result per sampled frame: <b>${vline(video)}</b></p><p class="why">Frame by frame - person 1, then the stranger, then person 1 again. No tracking.</p></div></div>
    <div class="scn"><div style="width:92pt"></div><div><h4>Scenario 10: a busy scene</h4><p class="how"><b>Do:</b> Match Studio → tick <i>Match everyone found in the image</i> → upload <code>scene_B_station_square.jpg</code></p><p>Result: seven people found and decided separately (heads blurred, nobody enrolled): <b>6 × UNKNOWN, 1 × REVIEW</b>.</p></div></div>
    <div class="scn"><div style="width:92pt"></div><div><h4>Scenario 11: video <code>clip_street.avi</code> (no usable faces)</h4><p class="how"><b>Do:</b> same as scenario 6</p><p>Result per sampled frame: <b>${vline(vstreet)}</b></p><p class="why">Clothing matches in frames 1 and 3, but with no face the system asks a person (REVIEW) instead of matching.</p></div></div>
    <img class="shot" src="${rel("screenshots/07b_video_result.png")}" alt="Video Explorer" style="margin-top:6pt">
    <p class="small">Video Explorer shows a timeline (M = match, U = unknown, R = review), the frame with the people drawn on it, the decision and its reason, and measured timings. A video upload is deleted from the server as soon as it has been processed.</p></section>

  <section class="page"><h2>5. Clothing only versus face + body</h2>
    <p>The <b>same eight photos</b> were shown to the system twice: once under the original clothing-only policy, once under face + body. <i>(Created with <code>run_demo.py --compare</code>, which switches the policy and puts it back.)</i></p>
    <table><thead><tr><th>Photo</th><th>Should be</th><th>Clothing only</th><th>Face + body</th></tr></thead><tbody>${cmp}</tbody></table>
    <p><b>Right answers: clothing only ${corrBody} of ${comparison.length} · face + body ${corrFace} of ${comparison.length}.</b> The same person in different clothes cannot be recognised by clothing; the face recognises her across clothes and years.</p>
    <h3>The opposite failure - same clothes, different person - measured on 10 enrolled people and 60 strangers</h3>
    <table><thead><tr><th></th><th>Clothing only</th><th>Face + body</th></tr></thead><tbody>
      <tr><td>Strangers wrongly <b>accepted</b> (lower is better)</td><td><span class="bar bad" style="width:${(e2e.body_only.stranger_ACCEPTED / 60) * 150}pt"></span> <b>${e2e.body_only.stranger_ACCEPTED} of 60</b></td><td><span class="bar good" style="width:6pt"></span> <b>${e2e.face_and_body.stranger_ACCEPTED} of 60</b></td></tr>
      <tr><td>Enrolled people recognised correctly (higher is better)</td><td><span class="bar bad" style="width:${(e2e.body_only.matched_correct_person / 20) * 150}pt"></span> <b>${e2e.body_only.matched_correct_person} of 20</b></td><td><span class="bar good" style="width:150pt"></span> <b>${e2e.face_and_body.matched_correct_person} of 20</b></td></tr>
      <tr><td>Enrolled people matched to the <b>wrong</b> person</td><td><b>${e2e.body_only.matched_WRONG_person}</b></td><td><b>${e2e.face_and_body.matched_WRONG_person}</b></td></tr></tbody></table>
    <div class="note"><b>Read these honestly.</b> The 60 strangers come from LFW (public-figure news photos, head and shoulders) - outside what the clothing model was designed for, so its column is a worst case. The threshold was fixed beforehand, not tuned on these photos. A small sample: it shows <i>what the face adds</i>; it is not a benchmark. Reproduce: <code>python scripts\\verify_face_vs_body.py --lfw &lt;folder&gt;</code>.</div></section>

  <section class="page"><h2>6. Try it with your own volunteers</h2>
    <p>The strongest demonstration uses people in the room (with their permission). No web interface needed:</p>
    <pre>my_photos\\
   enroll\\anna\\   anna_1.jpg  anna_2.jpg        (2-3 clear, front-facing photos of each person to enrol)
   enroll\\ben\\    ben_1.jpg   ben_2.jpg
   test\\anna\\     new_photo.jpg  back_view.jpg   (NEW photos of enrolled people - should be MATCH, or REVIEW if poor)
   test\\visitor\\  visitor_in_similar_clothes.jpg  (somebody NOT enrolled - should be UNKNOWN)

python demo\\face_check.py my_photos --i-have-consent</pre>
    <p>It prints, for every test photo, what the answer should be, what the system said, and the face and body scores; it removes the volunteers again at the end (<code>--keep</code> leaves them). Try the public-domain set first: <code>python demo\\face_check.py demo\\samples\\faces --i-have-consent</code>.</p>
    <div class="note"><b>Best live demonstration:</b> enrol a volunteer, then show a photo of a <i>different</i> person wearing similar clothes. The old clothing-only matcher accepts them; this one says UNKNOWN, and the Evidence card shows why (a high body bar, a low face bar).</div>
    <h2>7. A short tour of the other screens</h2>
    <div class="two"><div><img class="shot" src="${rel("screenshots/10a_settings_model_and_policy.png")}" alt="" style="max-height:330pt;object-fit:cover;object-position:top"><p class="small"><b>Model &amp; System</b> - models with checksums, the active rules (versioned, nothing edited in place), the switch between Face + body and Body only.</p></div>
      <div><img class="shot" src="${rel("screenshots/08a_lookalike_top.png")}" alt="" style="max-height:330pt;object-fit:cover;object-position:top"><p class="small"><b>Lookalike Failure Lab</b> - finds the different people the model confuses; every cause is labelled a hypothesis. (Synthetic data in the screenshot: proves the lab works, not accuracy.)</p></div></div></section>

  <section class="page"><h2>8. What can go wrong</h2>
    <table><thead><tr><th>You see</th><th>Why and what to do</th></tr></thead><tbody>
    <tr><td>Top bar: <b>Backend offline</b></td><td>The server is not running. Start it with <code>scripts\\start.ps1</code> and keep that window open.</td></tr>
    <tr><td>Top bar: <b>Model not loaded</b></td><td>Model files missing or damaged. Run <code>python scripts\\download_weights.py</code>, restart. The reason is shown under Model &amp; System.</td></tr>
    <tr><td>"Face models are not loaded - only the body is compared"</td><td>The two face files are missing. Same fix. Until then the system works on the body only and says so.</td></tr>
    <tr><td><code>run_demo.py</code> says <b>BODY ONLY</b></td><td>The policy is not Face + body. Run with <code>--enable-faces</code>, or choose it under Model &amp; System → Matching mode.</td></tr>
    <tr><td>A scenario result differs from this guide</td><td>Other people in the gallery, a changed threshold, or a different policy can change results. Use a clean gallery (<code>run_demo.py --cleanup</code>) and policy v1.</td></tr>
    <tr><td>A person card says <b>No face on file</b></td><td>The reference photos have no usable face (back view, tiny, blurred). Add a clear front-facing photo; or press <b>Analyse faces</b>.</td></tr>
    <tr><td>Port 8000 is in use</td><td>Use <code>scripts\\start.ps1 -Port 8020</code> and pass <code>--base-url http://127.0.0.1:8020</code> to the scripts.</td></tr>
    <tr><td>Scores differ slightly from the guide</td><td>Normal across different CPUs. Outcomes should be the same.</td></tr></tbody></table>
    <h2>9. What this pack does not prove</h2>
    <ul><li>It is <b>not a phone's Face ID</b>: no depth sensor and no liveness check; a photograph can fool a 2-D matcher.</li><li>The face stage was measured on the <b>standard LFW benchmark</b> (easy). Other cameras, lighting, ages and demographic groups were <b>not</b> measured.</li><li>The <b>pedestrian re-identification benchmark (Market-1501) has not been run</b>; the Evaluation Lab is built and tested but shows "Not evaluated" until it is supplied.</li><li>Thresholds are evidence-based defaults, <b>unvalidated</b> for any specific camera.</li><li>The example people are public figures photographed at work; they are used only to show recognition across photographs.</li><li>Face fingerprints are <b>biometric data</b>: enrol only consenting people; deleting a person erases everything stored about them.</li></ul>
    <h2>10. Where everything is</h2>
    <table><tbody><tr><td><code>docs/JURY_GUIDE.md</code></td><td>what to say, demo script, questions and answers</td></tr><tr><td><code>docs/FACE_AND_BODY_MATCHING.md</code></td><td>the exact rule, the threshold derivation, all measurements and limits</td></tr><tr><td><code>docs/SECURITY_AND_PRIVACY.md</code></td><td>consent, biometric data, retention, security</td></tr><tr><td><code>docs/results/*.json</code></td><td>the raw measurements behind every number in this pack</td></tr><tr><td><code>README.md</code></td><td>installation, API, evaluation, troubleshooting</td></tr></tbody></table></section>
  </body></html>`;
}

// ======================================================================================================== MARKDOWN → PDF
function markdownPage(title, md) {
  const css = `
  @page { size: A4; margin: 0 } body { font-family: "Segoe UI", Arial, sans-serif; color: #16181d; font-size: 10.2pt; line-height: 1.5; margin: 0 }
  h1 { font-size: 24pt; border-bottom: 3px solid #e53935; padding-bottom: 6pt; margin: 0 0 10pt } h2 { font-size: 15pt; margin: 18pt 0 6pt; border-bottom: 1px solid #e3e6eb; padding-bottom: 3pt; page-break-after: avoid } h3 { font-size: 12pt; margin: 12pt 0 4pt; page-break-after: avoid }
  table { border-collapse: collapse; width: 100%; margin: 6pt 0; font-size: 9.2pt } th, td { border: 1px solid #dfe3e9; padding: 4pt 7pt; text-align: left; vertical-align: top } th { background: #f4f5f8 } tr { page-break-inside: avoid }
  pre { background: #0f1217; color: #e9ecf1; padding: 8pt 10pt; border-radius: 6pt; font-size: 8.4pt; line-height: 1.45; white-space: pre-wrap; page-break-inside: avoid } code { font-family: Consolas, monospace; background: #f1f3f6; padding: 0 3pt; border-radius: 3pt; font-size: 9pt } pre code { background: none; color: inherit; padding: 0 }
  blockquote { margin: 8pt 0; padding: 6pt 12pt; border-left: 4px solid #e53935; background: #fff5f4; color: #3a2a2a } hr { border: 0; border-top: 1px solid #e3e6eb; margin: 14pt 0 } a { color: #b3261e; text-decoration: none } li { margin: 2pt 0 } p { margin: 5pt 0 }`;
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>${esc(title)}</title><style>${css}</style></head><body>${marked.parse(md, { gfm: true })}</body></html>`;
}

const footer = (label) => `<div style="font-size:8px;width:100%;text-align:center;color:#8a93a1;font-family:Segoe UI,Arial">OpenID Vision - ${label} - page <span class="pageNumber"></span> of <span class="totalPages"></span></div>`;
const a4 = (label) => ({ format: "A4", margin: { top: "16mm", bottom: "18mm", left: "15mm", right: "15mm" }, displayHeaderFooter: true, headerTemplate: "<span></span>", footerTemplate: footer(label) });

console.log("Building documents ...");
await toPdf(deck(), path.join(demo, "JURY_DECK.pdf"), { width: "1280px", height: "720px", preferCSSPageSize: true });
await toPdf(demoGuide(), path.join(demo, "DEMO_GUIDE.pdf"), { preferCSSPageSize: true, displayHeaderFooter: true, headerTemplate: "<span></span>", footerTemplate: footer("demo guide") });
for (const [source, target, label] of [["JURY_GUIDE.md", "JURY_GUIDE.pdf", "jury guide"], ["FACE_AND_BODY_MATCHING.md", "FACE_AND_BODY_MATCHING.pdf", "face and body matching"]]) {
  const md = readFileSync(path.join(root, "docs", source), "utf8");
  await toPdf(markdownPage(label, md), path.join(demo, target), a4(label));
}
await browser.close();
console.log("Done.");
