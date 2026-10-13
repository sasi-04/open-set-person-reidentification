/*
 * Build the step-by-step USER MANUAL (PDF) from the pictures made by scripts/make_manual_images.mjs.
 *
 * In plain words: a person who has never seen the website should be able to follow this document from "how do I open it" to
 * "how do I read the answer" without help. Every step has a real picture of the real screen with red numbered boxes, and a
 * legend that says what each number is.
 *
 * The "practice photos" table at the end is NOT typed by hand: this script sends those photos to the running test server and prints
 * what the system actually answered, so the manual cannot promise a result the system does not give.
 *
 *     node scripts/make_manual_images.mjs http://127.0.0.1:8765      (once, or whenever the website changes)
 *     node scripts/build_user_manual.mjs  http://127.0.0.1:8765      -> OpenID-Vision-User-Manual.pdf
 */
import { createRequire } from "node:module";
import { existsSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const require = createRequire(path.join(root, ".tools", "shots", "package.json"));
const puppeteer = require("puppeteer-core");

const base = (process.argv[2] ?? "http://127.0.0.1:8765").replace(/\/$/, "");
const images = path.join(root, "demo", "manual_images");
const samples = path.join(root, "demo", "samples");
const build = path.join(root, "demo", "_build");
mkdirSync(build, { recursive: true });
const target = path.join(root, "OpenID-Vision-User-Manual.pdf");

const url = (name) => pathToFileURL(path.join(images, name + ".jpg")).href;
for (const needed of ["01_first_screen", "09_result_decision", "ans_match", "ans_unknown", "ans_review"]) {
  if (!existsSync(path.join(images, needed + ".jpg"))) throw new Error(`Missing picture ${needed}.jpg - run scripts/make_manual_images.mjs first.`);
}

// ------------------------------------------------------------------------------- practice results (measured live)
const LABEL = { accepted: "MATCH", unknown: "UNKNOWN", review_required: "REVIEW", processing_error: "ERROR" };
async function ask(file, mode = "crop") {
  const form = new FormData();
  form.append("image", new Blob([readFileSync(file)], { type: "image/jpeg" }), path.basename(file));
  form.append("mode", mode);
  form.append("top_k", "3");
  const response = await fetch(`${base}/api/reid/predict`, { method: "POST", body: form });
  if (!response.ok) throw new Error(`predict failed for ${file}: ${response.status}`);
  return response.json();
}
const gallery = await (await fetch(`${base}/api/gallery?limit=20`)).json();
const enrolled = gallery.items.map((i) => i.reference_id);
if (!enrolled.includes("subject-001") || !enrolled.includes("subject-002")) {
  throw new Error(`The test server must hold subject-001 and subject-002 (it has: ${enrolled.join(", ") || "nobody"}). Run make_manual_images.mjs first.`);
}
const F = (p) => path.join(samples, "faces", "test", p);
const practice = [
  ["faces/test/collins/collins_test_1_nasa_jacket_1999.jpg", "Example person 1 in a NASA jacket (1999)", F("collins/collins_test_1_nasa_jacket_1999.jpg"), "crop"],
  ["faces/test/collins/collins_test_2_suit_jacket_2010.jpg", "Example person 1 in a suit jacket (2010)", F("collins/collins_test_2_suit_jacket_2010.jpg"), "crop"],
  ["faces/test/collins/collins_test_3_hard_hat_2004.jpg", "Example person 1 in a hard hat (2004)", F("collins/collins_test_3_hard_hat_2004.jpg"), "crop"],
  ["faces/test/ride/ride_stranger_1_cockpit_1983.jpg", "A stranger (never added), in a cockpit", F("ride/ride_stranger_1_cockpit_1983.jpg"), "crop"],
  ["faces/test/ride/ride_stranger_2_blue_shirt_1983.jpg", "The same stranger, blue shirt", F("ride/ride_stranger_2_blue_shirt_1983.jpg"), "crop"],
  ["faces/test/jemison/jemison_test_1_in_flight_1992.jpg", "Another person who was never added", F("jemison/jemison_test_1_in_flight_1992.jpg"), "crop"],
  ["query_1_same_person.jpg", "Example person 2 again - but the head is blurred, so no face", path.join(samples, "query_1_same_person.jpg"), "crop"],
  ["query_2_stranger.jpg", "A stranger, head blurred", path.join(samples, "query_2_stranger.jpg"), "crop"],
  ["query_3_blurry.jpg", "Example person 2, heavily out of focus", path.join(samples, "query_3_blurry.jpg"), "crop"],
];
const practiceRows = [];
for (const [shortName, what, file, mode] of practice) {
  const answer = await ask(file, mode);
  const d = answer.people[0].decision;
  const who = d.accepted_reference_id ? ` ${d.accepted_reference_id}` : "";
  const score = d.basis === "face" ? `face ${d.top1_face_score?.toFixed(2)}` : `body ${d.top1_score?.toFixed(2)}`;
  practiceRows.push({ shortName, what, outcome: d.outcome, label: LABEL[d.outcome] + who, score });
  console.log("  practice", shortName, "->", LABEL[d.outcome] + who, score);
}
{
  const scene = await ask(path.join(samples, "scene_B_station_square.jpg"), "all");
  const counts = {};
  scene.people.forEach((p) => (counts[p.decision.outcome] = (counts[p.decision.outcome] || 0) + 1));
  const text = Object.entries(counts).map(([o, n]) => `${n} x ${LABEL[o]}`).join(", ");
  practiceRows.push({ shortName: "scene_B_station_square.jpg", what: `A busy square with ${scene.people.length} people (tick “Match everyone found in the image”, not the crop box)`, outcome: "unknown", label: text, score: "-" });
  console.log("  practice scene ->", text);
}

// ------------------------------------------------------------------------------------------ small building blocks
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const img = (name, { width = "100%", cls = "" } = {}) => `<img class="shot ${cls}" src="${url(name)}" style="width:${width}" alt="">`;
const legend = (items, two = false) => `<ol class="legend${two ? " cols2" : ""}">${items.map(([n, html]) => `<li><span class="n">${n}</span><div>${html}</div></li>`).join("")}</ol>`;
const steps = (items) => `<ol class="todo">${items.map((t) => `<li>${t}</li>`).join("")}</ol>`;
const tip = (html, kind = "tip") => `<div class="box ${kind}"><b>${{ tip: "Tip", warn: "Careful", note: "Good to know", ok: "You should see" }[kind]}.</b> ${html}</div>`;
const badge = (o) => `<span class="badge ${o}">${{ accepted: "MATCH", unknown: "UNKNOWN", review_required: "REVIEW" }[o]}</span>`;
const head = (n, title, sub) => `<header class="stephead"><span class="bignum">${n}</span><div><h2>${title}</h2><p>${sub}</p></div></header>`;
const page = (html, cls = "") => `<section class="page ${cls}">${html}</section>`;
const btn = (t) => `<span class="btn">${esc(t)}</span>`;

const terminal = `<div class="term"><div class="termbar"><i></i><i></i><i></i> OpenID Vision - KEEP THIS WINDOW OPEN</div><pre>============================================================
 OpenID Vision is starting.
 KEEP THIS WINDOW OPEN while you use the website.
 When it says "Application startup complete" the website is
 ready at:   http://127.0.0.1:8000
 Your browser will open by itself in a few seconds.
 To STOP the website: close this window.
============================================================

Backend starting: http://127.0.0.1:8000
INFO  Embedding model osnet_ain_x1_0 ready on cpu
INFO  Detector fasterrcnn_mobilenet_v3_large_fpn ready on cpu
INFO  Face models ready
INFO  Gallery index: 0 identities, 0 images, 0 usable faces
INFO  OpenID Vision 1.0.0 ready
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000</pre></div>`;
const addressBar = `<div class="addr"><span class="dots"></span><span class="field">http://127.0.0.1:8000</span></div>`;

// ================================================================================================================ pages
const pages = [];

pages.push(`<section class="cover"><p class="kicker">USER MANUAL</p><h1>OpenID Vision</h1><p class="tag">Know when to match. Know when to reject.</p>
  <p class="lead">How to use the website, step by step - with pictures of the real screens.</p>
  <div class="coverbox"><b>This manual is for you if</b><ul><li>you have never used the website before,</li><li>you want to add a person, check a photo, and understand the answer,</li><li>you do not need to know anything about computers or artificial intelligence.</li></ul></div>
  <div class="coverbox"><b>The website address</b><div class="bigaddr">http://127.0.0.1:8000</div><p>It only works on this computer. To start it, double-click <b>Start OpenID Vision.bat</b> (in the folder <b>D:\\ps1</b>).</p></div>
  <p class="small">Independent technical prototype responding to the Zed Digital PS-1 assignment - not an official Zed Digital product. Research use with consenting people only. October 2026.</p></section>`);

pages.push(page(`<h1 class="ph">Before you begin</h1>
  <h3>What does this website do?</h3>
  <p class="big">You give it a <b>photo of a person</b>. It tells you whether that person is <b>someone you added earlier</b> - and it explains why. It compares the <b>face</b> first, and the <b>body and clothes</b> second.</p>
  <p class="big"><b>Short on time?</b> Open the website and press <b>Run the example</b> on the home page. It tests the system on 13 ready-made photos in about 10 seconds - no photos of your own needed.</p>
  <h3>Every photo gets one of three answers</h3>
  <div class="three">
    <div class="ans">${img("ans_match", { width: "100%" })}<p>${badge("accepted")}<br><b>"This is someone you added."</b> The evidence is strong. Nothing more to do.</p></div>
    <div class="ans">${img("ans_unknown", { width: "100%" })}<p>${badge("unknown")}<br><b>"I do not know this person."</b> Nobody you added matches. It is <u>not</u> an accusation.</p></div>
    <div class="ans">${img("ans_review", { width: "100%" })}<p>${badge("review_required")}<br><b>"I am not sure - you decide."</b> The photo is poor, or no face is visible. Look yourself.</p></div>
  </div>
  <h3>Three rules</h3>
  <ol class="rules"><li><b>Only use photos of people who agreed.</b> A face fingerprint is stored on this computer (it is called biometric data). Delete people when you no longer need them.</li>
  <li><b>Add people with clear photos of the face</b> (looking at the camera, not tiny, not blurry). That is what makes the answer reliable.</li>
  <li><b>MATCH is not proof.</b> It is a strong hint from a research prototype. Never use it alone for an important decision about a person.</li></ol>`));

pages.push(page(`<h1 class="ph">The whole process in 5 steps</h1>
  <div class="flow">
    <div><span class="fn">1</span><b>Open the website</b><small>double-click the start file</small></div><i>→</i>
    <div><span class="fn">2</span><b>Add people</b><small>once, with consent</small></div><i>→</i>
    <div><span class="fn">3</span><b>Check a photo</b><small>Match Studio</small></div><i>→</i>
    <div><span class="fn">4</span><b>Read the answer</b><small>MATCH · UNKNOWN · REVIEW</small></div><i>→</i>
    <div><span class="fn">5</span><b>Tidy up</b><small>history, delete, stop</small></div></div>
  <table class="plain"><thead><tr><th>Step</th><th>What you do</th><th>Where</th><th>Section of this manual</th></tr></thead><tbody>
    <tr><td><b>1</b></td><td>Start the website and open it in your browser</td><td>Start file + browser</td><td>Open the website</td></tr>
    <tr><td><b>2</b></td><td>Add each person you want to recognise (2-5 clear photos each)</td><td>Identity Gallery</td><td>Add a person</td></tr>
    <tr><td><b>3</b></td><td>Choose the photo to check and press the red button</td><td>Match Studio</td><td>Check a photo</td></tr>
    <tr><td><b>4</b></td><td>Read MATCH / UNKNOWN / REVIEW and the reason</td><td>Match Studio (right side)</td><td>Read the answer</td></tr>
    <tr><td>&#9733;</td><td>Try the ready-made example (no photos of your own)</td><td>Home page</td><td>Try the example first</td></tr>
    <tr><td>+</td><td>Photos with several people · video clips</td><td>Match Studio · Video Explorer</td><td>A photo with several people · Check a video clip</td></tr>
    <tr><td>+</td><td>Look back at past answers · save them · remove people · stop the website</td><td>Decision history · Identity Gallery</td><td>Look back · Manage people · Stop, restart</td></tr></tbody></table>
  ${tip("The very first time, do the <b>Practice exercise at the end of this manual</b>: it uses photos that come with the website and tells you the answer you should get. If you get the same answers, everything works.", "tip")}
  <h3>Words you will see</h3>
  <table class="plain"><tbody>
    <tr><td><b>Add / enroll a person</b></td><td>Save a person's photos so the system can recognise them later.</td></tr>
    <tr><td><b>Reference ID</b></td><td>A code name for a person, like <code>subject-001</code>. Not a real name.</td></tr>
    <tr><td><b>Similarity</b></td><td>How alike two faces (or two bodies) look, from -1 to 1. It is a score, <u>not</u> a percentage: 0.9 does not mean "90% sure".</td></tr>
    <tr><td><b>Threshold</b></td><td>The score a face must reach to count as a match. The black tick on every bar shows it.</td></tr>
    <tr><td><b>Face + body</b></td><td>The way the system works now: the face decides when it is clearly visible; clothes and build only support it.</td></tr></tbody></table>`));

pages.push(page(`${head(1, "Open the website", "About 30 seconds. You do this each time you sit down to work.")}
  ${steps([
    `Open the folder <b>D:\\ps1</b> and <b>double-click</b> the file <b>Start OpenID Vision.bat</b>.`,
    `A <b>black window</b> opens. <b>Keep it open</b> - it is the engine. Wait until you see <code>Application startup complete</code> (15-30 seconds the first time).`,
    `Your <b>web browser opens by itself</b> at the website. If it does not, open Edge or Chrome yourself and type the address below into the bar at the top.`,
    `You should see the screen on the next page. The status at the top right must say <b>Models ready</b>.`,
  ])}
  <div class="side2"><div><h4>What the black window looks like</h4>${terminal}</div>
  <div><h4>The address to type (only if the browser did not open)</h4>${addressBar}
    ${tip("If the browser shows <b>“This site can't be reached”</b>, the black window is not running. Close any error, then double-click <b>Start OpenID Vision.bat</b> again and wait for “Application startup complete”.", "warn")}
    ${tip("If you double-click the start file while the website is <b>already running</b>, it simply opens the browser for you. Nothing breaks.", "note")}
    ${tip("<b>To stop the website</b> at the end of the day: close the black window.", "tip")}</div></div>`));

pages.push(page(`${head(1, "The first screen", "This is the home page (the Command Center). It shows the three things that matter, and whether everything is ready.")}
  ${img("01_first_screen")}
  ${legend([
    [1, "<b>The menu</b> (always on the left). Click a name to go to that screen. The next page explains each one."],
    [2, "<b>Status.</b> <b>Models ready</b> = everything is loaded and working. If it says <i>Backend offline</i> or <i>Model not loaded</i>, see “If something goes wrong” near the end."],
    [3, "<b>How it works</b> - a short plain-language tour of the system, inside the website. Open it any time."],
    [4, "<b>The essentials in three steps</b> - <b>1 Enroll people</b> (add someone the system should know), <b>2 Match photos</b> (ask who is in a photo), <b>3 See the open-set analysis</b> (the ready-made example). Each card ticks itself when it is done."],
    [5, "<b>The open-set example</b> - one button that tests the system on 13 ready-made photos. The next pages show how to read it."],
  ])}
  ${tip("The moon button at the top right switches between light and dark colours. It changes nothing else.", "note")}`));

pages.push(page(`${head(1, "The seven screens", "You will mostly use only two of them: Identity Gallery and Match Studio.")}
  ${img("02_screen_map")}
  <table class="plain screens"><thead><tr><th></th><th>Screen</th><th>Use it to...</th><th>How often</th></tr></thead><tbody>
    <tr><td><span class="n">1</span></td><td><b>Command Center</b> (home page)</td><td>Start here: the three essentials, the one-click example, and a check that everything works</td><td>Each time</td></tr>
    <tr><td><span class="n">2</span></td><td><b>Identity Gallery</b></td><td><b>Add</b> people, see their photos, delete them</td><td class="often">Often</td></tr>
    <tr><td><span class="n">3</span></td><td><b>Match Studio</b></td><td><b>Check a photo</b> and read the answer</td><td class="often">Often</td></tr>
    <tr><td><span class="n">4</span></td><td><b>Video Explorer</b></td><td>Check a short video clip, one frame every second or so</td><td>Sometimes</td></tr>
    <tr><td><span class="n">5</span></td><td><b>Lookalike Failure Lab</b></td><td>For specialists: finds pairs of different people the system confuses</td><td>Rarely</td></tr>
    <tr><td><span class="n">6</span></td><td><b>Evaluation Lab</b></td><td>For specialists: measures mistakes on a research data set</td><td>Rarely</td></tr>
    <tr><td><span class="n">7</span></td><td><b>Model &amp; System</b></td><td>See the settings and the health of the system (look, do not change)</td><td>Rarely</td></tr></tbody></table>`));

pages.push(page(`${head("&#9733;", "Try the example first", "The home page has a ready-made test. No photos of your own and no set-up: about 10 seconds.")}
  ${img("01a_example_before")}
  ${legend([
    [1, "<b>Run the example</b> - press this red button and wait about 10 seconds. A bar shows how far it has got."],
    [2, "<b>Who the system knows</b> - three example people it is given for the test. The small words under each photo say whether a face was found."],
    [3, "<b>The 13 photos</b> - what it will be tested on: people it knows, people it has never seen, and strangers dressed in the <u>same clothes</u> as someone it knows. The right answer is written next to every photo."],
    [4, "<b>Rules</b> - the two lines it will use: how alike two faces must be, and how alike two sets of clothes must be. They are starting values, not proven for your cameras."],
  ], true)}
  ${tip("<b>Nothing is saved and your own people are not touched.</b> The example uses a private, temporary list that disappears when the website stops. The photos are public-domain portraits that come with the project.", "note")}`));

pages.push(page(`${head("&#9733;", "Reading the example's result", "The same 13 photos, judged two ways: by the system (face + body) and by a weaker matcher that looks only at clothes.")}
  ${img("01b_example_result")}
  ${legend([
    [1, "<b>What the example shows</b> - one plain sentence, written from the counts below it."],
    [2, "<b>The table</b> - left column: this system. Right column: clothes only. “5 of 5” means five out of five. A <b>green tick</b> is good, a <b>red cross</b> is not. Look at the third row: the strangers who wore the same clothes."],
    [3, "<b>Face plot</b> - each dot is one photo; its place shows how alike the face is to the closest known face. Right of the dashed line = passes. Known people (green) are on the right, strangers on the left."],
    [4, "<b>Clothes plot</b> - the same idea for clothes. The strangers in the same clothes (red) sit <u>to the right</u> of the line, as high as the real people: clothes alone cannot tell them apart."],
    [5, "<b>Try it: move the face line</b> - drag the slider. Lower it and strangers start to get in; raise it and real people start to be missed."],
  ])}`));

pages.push(page(`${head("&#9733;", "Every photo, both matchers", "Scroll down the home page to the list of photos. Each row is one photo.")}
  ${img("01c_example_rows")}
  ${legend([
    [1, "<b>The photo</b>, what it shows, and the <b>right answer</b>. Here: a stranger in the same orange suit, so the right answer is UNKNOWN."],
    [2, "<b>Face + body (this system)</b> - its answer, whether it was right, and the score drawn against the line it needed. <b>Why this answer</b> (opened here) gives the reason in words."],
    [3, "<b>Clothes only</b> - what a weaker matcher would have said. Here it accepted the stranger (red <b>Stranger accepted</b>): the clothes looked just like an enrolled person's."],
    [4, "<b>Why this answer</b> - click to open or close the reason."],
  ])}
  <div class="box warn"><b>What the example does not prove.</b> It is 13 photos: a demonstration of how the system thinks, <u>not</u> a measurement of how accurate it is. The photos are head-and-shoulders portraits, the lines are unproven starting values, and other cameras and lighting have not been tested.</div>
  <div class="rulebox"><b>In one sentence:</b> in this small test, clothing pointed at the wrong people and the face did not.</div>`));

pages.push(page(`${head(2, "Add a person", "Do this once for each person you want the system to recognise. Start in the Identity Gallery.")}
  ${steps([
    `Click <b>Identity Gallery</b> in the left menu.`,
    `Click the red button ${btn("Enroll identity")} (number 1 below). A form opens.`,
  ])}
  ${img("03_gallery_empty")}
  ${legend([[1, `The red <b>Enroll identity</b> button. (“Enroll” just means “add and save this person”.) The gallery is empty the first time - that is normal.`]])}
  ${tip("Add people <b>only if they agreed</b>. The form asks you to confirm this.", "warn")}`));

pages.push(page(`${head(2, "Fill in the form", "Seven things, top to bottom.")}
  ${img("04_enroll_dialog", { width: "72%" })}
  ${legend([
    [1, "<b>Reference ID</b> - a code name, for example <code>subject-001</code>. Use letters, numbers, dot, dash. <b>Not</b> a real name or ID number."],
    [2, "<b>Description</b> (optional) - a short, harmless note, for example “Example person 1”."],
    [3, `<b>Photos.</b> Drag photos into the dashed box, <b>or</b> click ${btn("Browse files")}: a normal Windows window opens - click a photo, hold <b>Ctrl</b> to pick several, press <b>Open</b>.`],
    [4, "Check the small pictures. Wrong one? Click the <b>×</b> on it."],
    [5, "<b>Leave ticked</b> if each photo shows just that one person. Untick only for a wider photo (the system then finds the person itself, and refuses photos with several people)."],
    [6, "<b>Tick this</b> to confirm the person agreed. The Enroll button stays pale until the ID, at least one photo and this tick are all there."],
    [7, `Click ${btn("Enroll identity")}.`],
  ], true)}
  ${tip("<b>Good photos</b> make the answers reliable: 2 to 5 photos, the <b>face clearly visible</b> and looking towards the camera, not tiny, not blurry, no sunglasses or mask. Different clothes or days are a bonus.", "tip")}`));

pages.push(page(`${head(2, "Check the result of adding", "The system tells you, photo by photo, whether it found a usable face.")}
  <div class="cols"><div class="c1">${img("05_enroll_result")}</div><div class="c2">${legend([
    [1, "A confirmation: the person now has this many photos saved."],
    [2, "One line per photo. <b>“usable face on file”</b> is what you want. If a line says <i>no usable face</i> or <i>too small / blurry / turned</i>, that photo will not help face matching - add a clearer one later."],
    [3, `Click ${btn("Done")}.`],
  ])}</div></div>
  <h3>Then look at the gallery</h3>
  ${img("06_gallery_people")}
  ${legend([
    [1, "A card for each person you added."],
    [2, "<b>Green: “2 of 2 with a face”</b> - both photos have a usable face. This person can be recognised reliably."],
    [3, "<b>Amber: “No face on file”</b> - no photo of this person shows a usable face (for example a photo from behind, or a blurred head). This person can only be compared by clothes and build, which is weaker, so answers for them will often be <b>REVIEW</b>. Add a clear face photo (see “Manage people”)."],
    [4, "Counters: how many people, how many photos, and how many photos have a usable face."],
  ])}`));

pages.push(page(`${head(3, "Check a photo", "Open Match Studio, choose the photo, press the red button.")}
  ${steps([`Click <b>Match Studio</b> in the left menu.`, `Add the photo you want to check (number 1).`, `Tick the box <b>“Image is already a person crop”</b> (number 2) if the photo shows <b>just one person</b>, like a portrait. (For a photo with several people see “A photo with several people”.)`, `Click ${btn("Run re-identification")} (number 4).`])}
  ${img("07_match_empty")}
  ${legend([
    [1, "<b>The photo box.</b> Drag a photo in, or click <b>Browse files</b> and choose it."],
    [2, "<b>Image is already a person crop</b> - tick for a photo of one person."],
    [3, "<b>Detect people</b> - only for photos with several people (see “A photo with several people”). Not needed for a portrait."],
    [4, "<b>Run re-identification</b> - the red button that starts the check. It stays pale until a photo is chosen."],
  ])}`));

pages.push(page(`${head(3, "Ready to run", "After choosing a photo the left card looks like this.")}
  <div class="cols"><div class="c1 narrow">${img("08_match_ready")}</div><div class="c2">${legend([
    [1, `Your photo with its file name. ${btn("Replace")} swaps it, ${btn("Remove")} clears it.`],
    [2, "The crop box is ticked."],
    [3, "Press <b>Run re-identification</b>. The text under it says what will happen."],
  ])}
  ${tip("Waiting: usually <b>1 to 5 seconds</b>. A photo with many people, or a slow/busy computer, can take up to <b>half a minute</b>. Wait - do not click again.", "note")}
  ${tip("Wrong photo? Click <b>Reset</b> and start again. Nothing is saved about the photo itself.", "tip")}</div></div>
  <h3>The screen then fills with results, in three columns</h3>
  <table class="plain"><tbody><tr><td><b>Left</b></td><td>your photo and the buttons</td></tr><tr><td><b>Middle</b></td><td>your photo with a box drawn on the face, and your photo next to the closest person you added</td></tr><tr><td><b>Right</b></td><td><b>the answer</b>, the evidence behind it, the list of candidates, and buttons to save the result</td></tr></tbody></table>`));

pages.push(page(`${head(4, "Read the answer", "The <b>Decision</b> card at the top right is the answer.")}
  <div class="cols"><div class="c1 narrow2">${img("09_result_decision")}</div><div class="c2">${legend([
    [1, "<b>The answer:</b> MATCH, UNKNOWN or REVIEW (next page explains each)."],
    [2, "<b>The reason</b> in plain words. It is built from the real numbers - read it, it tells you exactly what happened."],
    [3, "<b>Only for MATCH:</b> the code name of the person it found. “View gallery entry” opens that person."],
    [4, "<b>The score bar.</b> The bar is the face similarity. The <b>black tick</b> is the threshold. <b>Bar reaches the tick = passes.</b> It is a score, not a percentage."],
    [5, "The threshold used. “Unvalidated” means it has not yet been fine-tuned for your own cameras - an honest label, not an error."],
  ])}
  ${tip("In this example the system found the <b>same person 12 years later in different clothes</b>. Clothes are different, the face is the same, so the face decides: MATCH.", "ok")}</div></div>`));

pages.push(page(`${head(4, "The three answers - and what to do", "")}
  <table class="plain answers"><thead><tr><th>Answer</th><th>It means</th><th>What you do</th></tr></thead><tbody>
    <tr><td>${badge("accepted")}</td><td>A person you added matches the face (and the system is confident).</td><td>Nothing. You may check the two faces side by side (next page). Save the result if you need a record (see “Look back: Decision history”).</td></tr>
    <tr><td>${badge("unknown")}</td><td>Nobody you added matches well enough. The person may simply never have been added. This says <b>nothing bad</b> about the person.</td><td>Nothing - unless you <i>expected</i> a match: then check the photo (clear face? big enough?) or add more photos of that person.</td></tr>
    <tr><td>${badge("review_required")}</td><td>The system is <b>not sure</b>: the photo is poor, no face is visible, the score is borderline, or two people are very close.</td><td><b>You decide.</b> Click <b>Review candidates</b> and compare with your own eyes (see “When the answer is REVIEW”).</td></tr></tbody></table>
  ${tip("Seeing UNKNOWN for someone you expected to be added? Check that they <b>were</b> added, and that the photo shows the face clearly.", "tip")}
  <h3>Same table, in one line each</h3>
  <ul class="plain-list"><li>${badge("accepted")} the system is confident - you do nothing.</li><li>${badge("unknown")} no match - you do nothing (it is not an accusation).</li><li>${badge("review_required")} the system is unsure - <b>you</b> look.</li></ul>`));

pages.push(page(`${head(4, "Why a stranger in the same clothes is still UNKNOWN", "This is the main idea of the system.")}
  <p>Older systems compared <b>clothes</b>. Two different people in the same jacket looked alike, so a stranger could get in. This system compares the <b>face first</b>. In the picture the two faces are clearly different, so the answer is UNKNOWN - even if the clothes were similar.</p>
  <div class="cols"><div class="c1 narrow2">${img("13_unknown_evidence")}</div><div class="c2">${legend([
    [1, "The <b>face bar stays short</b>: it does not reach the black tick. That is what decides."],
    [2, "The two faces: <b>query</b> (your photo) on the left, <b>closest person you added</b> on the right. You can see for yourself that they are different people."],
  ])}${tip("The body/clothes bar is shown too, as <b>supporting evidence only</b>. It can never turn a failing face into a MATCH.", "note")}${tip("The opposite also works: the <b>same person in different clothes</b> is still a MATCH, because their face matches (see “Read the answer”).", "ok")}</div></div>`));

pages.push(page(`${head(4, "The evidence card", "Why the system decided what it decided - side by side.")}
  <div class="cols"><div class="c1 narrow2">${img("10_result_evidence")}</div><div class="c2">${legend([
    [1, "<b>Who decided</b>: “Decided by the face” (a usable face was visible) or “Decided by the body” (no usable face). Also whether a usable face was found."],
    [2, "<b>Face bar</b> with its threshold tick - this is what decides when a face is usable."],
    [3, "<b>Body and clothing bar.</b> Supporting evidence. It can be low when the person changed clothes - that is normal."],
    [4, "<b>The two faces</b> the score was computed from: yours on the left, the enrolled one on the right. Look at them yourself."],
    [5, "<b>Supporting cues</b>: skin tone, hair and clothing colours, compared in plain words. <b>They never change the answer</b> - light and clothes change colours too much. They are only there to help you look."],
  ])}</div></div>`));

pages.push(page(`${head(4, "Pictures, candidates and saving", "The rest of the right-hand side.")}
  <div class="cols two"><div class="c1 narrow3">${img("12_result_pictures")}${legend([
    [1, "A box on the face the system found."],
    [2, "Your photo."],
    [3, "The photo of the closest person you added."],
  ])}</div><div class="c1 narrow3">${img("11_result_candidates")}${legend([
    [1, "<b>Best candidate</b> with its face and body score. A green <b>MATCH</b> tag only appears if it passed."],
    [2, "Other people, closest first. <b>Below threshold</b> = not a match. A person with no face on file is scored by body only."],
    [3, "<b>Save the result:</b> JSON (for programs) or CSV (opens in Excel)."],
    [4, "<b>Upload another query</b> - start the next photo."],
    [5, "<b>Decision history</b> - the list of all past answers."],
  ])}</div></div>`));

pages.push(page(`${head(4, "When the answer is REVIEW", "The system asks you to look. This is normal for poor photos.")}
  ${steps([`Click ${btn("Review candidates")} (number 2).`, `A window opens with your photo on the left and the candidates next to it. <b>Compare them yourself.</b> Opening this window changes nothing.`, `Decide for yourself. Close the window with <b>Esc</b> or the × at the top right.`])}
  <div class="cols"><div class="c1 narrow3">${img("14_review_candidates")}${legend([[1, "The yellow notice: a person must look."], [2, "The button that opens the comparison."]])}</div>
  <div class="c1 narrow3">${img("15_review_dialog")}${legend([[1, "The reason (here: no face visible, only clothes matched)."], [2, "Your photo."], [3, "The candidates, closest first."]])}</div></div>
  <h3>Common reasons for REVIEW</h3>
  <ul class="plain-list"><li><b>No face visible</b> (seen from behind, far away, head covered or blurred). Clothes alone are not enough for an automatic MATCH.</li><li><b>The photo is blurry, tiny or cut off.</b> Try a sharper, larger photo.</li><li><b>The face score is just below the line</b> (a borderline case).</li><li><b>Two people look about equally close.</b></li></ul>`));

pages.push(page(`${head("+", "A photo with several people", "Two ways. Both start with a normal photo.")}
  <h3>Way A - choose one person (Detect people)</h3>
  ${steps([`Choose the photo. Leave “Image is already a person crop” <b>unticked</b>.`, `Click ${btn("Detect people")} (1). The system draws a box around everyone it finds (2).`, `Click a name chip, <b>Person 1 ... Person 7</b> (3), or a box in the picture, to choose who to check.`, `Click ${btn("Run re-identification")} (4). Only the chosen person is checked.`])}
  ${img("16_detect_people", { width: "92%" })}
  ${legend([[1, "Detect people."], [2, "The picture with boxes. The number on a box is how sure the detector is that it is a <b>person</b> - not who it is."], [3, "Chips to choose a person."], [4, "Run re-identification."], [5, "Alternative: tick this box and <b>everyone</b> is checked at once (Way B)."]])}`));

pages.push(page(`${head("+", "Way B - check everyone at once", "Tick “Match everyone found in the image”, then Run.")}
  ${img("17_everyone_result", { width: "92%" })}
  ${legend([
    [1, "<b>Match everyone found in the image</b> is ticked."],
    [2, "Every box is coloured by its answer and numbered. <b>Click a box</b> to see that person's answer on the right."],
    [3, "The answer for the selected person (“Person 1 of 7”)."],
    [4, "A reminder that you can click another box."],
  ])}
  ${tip("In this busy street photo the heads are blurred and nobody was added, so the answers are UNKNOWN or REVIEW. That is correct. With many people the check takes longer - <b>be patient</b>.", "note")}`));

pages.push(page(`${head("+", "Check a video clip", "Video Explorer looks at one frame every second (or every N seconds) and judges each frame by itself.")}
  ${steps([`Click <b>Video Explorer</b> in the menu.`, `Drag a video into the box or click ${btn("Browse files")} (1). Accepted: <code>.mp4 .mov .avi .mkv .webm</code>, up to 100 MB and 3 minutes.`, `Choose how often to take a frame (3) and the maximum number of frames (4). The defaults (every 1 second, up to 30 frames) are fine.`, `Click ${btn("Analyse video")} (5) and wait. It takes longer than a photo: roughly <b>1-5 seconds per frame</b>.`])}
  <div class="cols"><div class="c1 narrow3">${img("18_video_upload")}</div>
  <div class="c2">${legend([[1, "Drop area."], [2, "Preview. (Some video types, like .avi, may show a black picture here; this is not a problem.)"], [3, "How often to take a frame."], [4, "Maximum frames."], [5, "Start."]])}${tip("<b>It does not follow people.</b> Every frame is judged on its own. The same person in two frames is not “tracked”.", "warn")}${tip("Your video is <b>deleted from the server</b> as soon as it has been processed. Small preview pictures are kept 24 hours so you can look at them.", "note")}${tip("Only use footage of people who agreed.", "warn")}</div></div>`));

pages.push(page(`${head("+", "Reading the video result", "")}
  ${img("19_video_result", { width: "72%" })}
  ${legend([
    [1, "<b>Summary:</b> how many frames, how many people, how many MATCH / UNKNOWN / REVIEW. Buttons to save as JSON or CSV, or delete this result."],
    [2, "<b>Timeline:</b> one square per frame. <b>M</b> = match, <b>U</b> = unknown, <b>R</b> = review, <b>–</b> = nobody found. Click a square to look at that frame."],
    [3, "The chosen frame, with the people found."],
    [4, "The answer for that frame, with its reason and scores."],
  ])}`));

pages.push(page(`${head("+", "Look back: Decision history", "Every check you ran is listed - scores and answers only. Your photos are not kept here.")}
  ${img("20_history", { width: "80%" })}
  ${legend([[1, "One row per check: when, how many people, the answers, the best score, how long it took. Click <b>Details</b> to open one. Use the <b>Outcome</b> filter above to show only MATCH, UNKNOWN or REVIEW."]])}
  <h3>Saving a result</h3>
  <p>After any check, the card <b>Export and next steps</b> (see “Pictures, candidates and saving”) has <b>Decision record (JSON)</b> and <b>(CSV)</b>. CSV opens in Excel. Each record states which rules were active, so the answer can be explained later.</p>
  <h3>The summary screen</h3>
  ${img("25_command_center_used", { width: "60%" })}
  ${legend([[1, "How many MATCH answers so far."], [2, "How many UNKNOWN."], [3, "How many REVIEW."]])}`));

pages.push(page(`${head("+", "Manage people", "Add more photos, delete someone, or start over - all in the Identity Gallery.")}
  ${img("21_gallery_buttons", { width: "100%" })}
  ${legend([
    [1, "<b>Enroll identity</b> - add a new person (see “Add a person”)."],
    [2, "<b>Rebuild embeddings</b> - only needed after a technician changes the model. You can ignore it."],
    [3, "<b>Analyse faces</b> - looks for faces in photos added before face matching existed. Press it if the screen says photos “have not had their face analysed”."],
    [4, "<b>Reset demo gallery</b> - deletes <b>everyone</b> (asks you to type <code>RESET DEMO GALLERY</code>)."],
  ])}
  <p><b>Click a person's card</b> to open this window:</p>
  ${img("22_person_dialog", { width: "58%" })}
  ${legend([
    [1, "<b>Faces on file</b> - “2 of 2 with a face” is good."],
    [2, "The saved photos. The small label under each says <b>Face on file</b> (good) or the reason there is none."],
    [3, `${btn("Add images")} - add more photos of this person (clear faces help).`],
    [4, `${btn("Delete identity")} - removes the person, their photos and their face data for good. You must type their Reference ID to confirm.`],
  ], true)}
  ${tip("When you finish a project, <b>delete the people you added</b>. Their face fingerprints stay on this computer until you do.", "warn")}`));

pages.push(page(`${head("+", "Settings: look, but do not change", "Model &amp; System shows how the system is set up. You normally never need to change anything.")}
  <div class="cols two"><div class="c1 narrow3">${img("23_settings_policy")}${legend([
    [1, "<b>Matching mode: Face + body</b> (the recommended way)."],
    [2, "The face score a match must reach (<b>0.465</b>), and the “borderline” zone just below it that goes to REVIEW."],
    [3, "<b>Unvalidated</b>: the numbers are sensible starting values that have not yet been tested on <i>your</i> cameras. Honest, not an error."],
    [4, "A reminder of what that means."],
  ])}</div><div class="c1 narrow3">${img("24_settings_rules")}${legend([
    [1, "<b>Matching mode</b>: <i>Face + body</i> (recommended) or <i>Body only</i> (the original clothes-and-build behaviour)."],
    [2, "<b>Face threshold</b>: higher = stricter (fewer wrong matches, more REVIEW)."],
    [3, "<b>Save settings</b> - asks you to confirm first. It creates a <b>new numbered version</b>; the old one is kept."],
  ])}</div></div>
  ${tip("<b>Do not change these unless someone who understands them asks you to.</b> Every change affects all later answers. Nothing is lost - old versions stay in the “Policy version history” at the bottom of the page - but results before and after a change are not comparable.", "warn")}`));

pages.push(page(`<h1 class="ph">Stop, restart, and your data</h1>
  <h3>Stopping the website</h3>
  <p>Close the <b>black window</b>. The website stops. Closing only the browser tab does <b>not</b> stop it.</p>
  <h3>Starting it again later</h3>
  <p>Double-click <b>Start OpenID Vision.bat</b> again. The people you added are still there - they are stored on this computer in <code>D:\\ps1\\backend\\data</code>.</p>
  <h3>Privacy checklist</h3>
  <ul class="plain-list"><li>Only people who agreed are added or checked.</li><li>Nothing is sent over the internet. The website only answers on this computer.</li><li>The original photo you check is never saved. A small picture of the person is kept for <b>24 hours</b> (so the history can show it), then deleted; the scores stay in the history.</li><li>Photos of people you <b>add</b>, and their face data, are kept until you delete the person.</li><li>Delete people you no longer need; <b>Reset demo gallery</b> removes everyone.</li></ul>
  <h1 class="ph" style="margin-top:14px">If something goes wrong</h1>
  <table class="plain trouble"><thead><tr><th>You see</th><th>What to do</th></tr></thead><tbody>
    <tr><td>Browser says <b>“This site can't be reached”</b></td><td>The black window is not running. Double-click <b>Start OpenID Vision.bat</b>, wait for “Application startup complete”, then refresh the page (F5).</td></tr>
    <tr><td>Top bar says <b>Backend offline</b></td><td>Same as above - the engine stopped. Start it again.</td></tr>
    <tr><td>Top bar says <b>Model not loaded</b></td><td>A model file is missing or damaged. Ask the person who installed the system to run <code>scripts\\download_weights.py</code>, then restart.</td></tr>
    <tr><td><b>“No person was detected”</b></td><td>The photo has no clear person. Try a clearer photo, or tick “Image is already a person crop” if it is a portrait.</td></tr>
    <tr><td>The answer is always <b>REVIEW</b> for one person</td><td>That person has <b>No face on file</b>. Add a clear front-facing photo (see “Manage people”).</td></tr>
    <tr><td>A photo is refused</td><td>Use JPG, PNG, WEBP or BMP, under 10 MB, at least 32 pixels wide. The message tells you which rule it broke.</td></tr>
    <tr><td>It is very slow</td><td>Close other heavy programs. A photo normally takes a few seconds; many people or a video take longer.</td></tr>
    <tr><td>“Port 8000 is already in use”</td><td>The website is already running (just open the browser), or another program uses that port - ask for help.</td></tr></tbody></table>`));

const answerCell = (r) => {
  if (r.shortName.startsWith("scene")) return `<span class="wrapok"><b>${esc(r.label)}</b> <small>(nobody matched)</small></span>`;
  const who = r.outcome === "accepted" ? ` <b class="nw">${esc(r.label.split(" ").slice(1).join(" "))}</b>` : "";
  return `${badge(r.outcome)}${who}`;
};
const rows = practiceRows.map((r) => `<tr><td class="mono">${esc(r.shortName.split("/").pop())}</td><td>${esc(r.what)}</td><td class="nw">${answerCell(r)}</td><td class="nw">${esc(r.score)}</td></tr>`).join("");
pages.push(page(`<h1 class="ph">Practice exercise</h1>
  <p>Photos that come with the website, and the answers it gives. If you get the same answers, everything works.</p>
  <h3>Part 1 - add two people (see “Add a person”)</h3>
  <table class="plain p1"><colgroup><col style="width:17%"><col style="width:29%"><col style="width:41%"><col style="width:13%"></colgroup><thead><tr><th>Reference ID</th><th>Description</th><th>Photos to add (in <code>D:\\ps1\\demo\\samples\\</code>)</th><th>“Tight crop” tick</th></tr></thead><tbody>
    <tr><td><code>subject-001</code></td><td>Example person 1</td><td><code>faces\\enroll\\collins\\</code> - both photos</td><td>yes</td></tr>
    <tr><td><code>subject-002</code></td><td>Example person 2 (street photo, head blurred)</td><td><code>person_A_reference_1.jpg</code> and <code>person_A_reference_2.jpg</code></td><td>yes</td></tr></tbody></table>
  <p class="small">Remember the consent tick. After adding, <code>subject-001</code> should say <b>2 of 2 with a face</b>, and <code>subject-002</code> <b>No face on file</b>.</p>
  <h3>Part 2 - check these photos in Match Studio (tick “Image is already a person crop”)</h3>
  <p class="small">Find them in <code>D:\\ps1\\demo\\samples\\faces\\test\\collins</code>, <code>…\\ride</code> and <code>…\\jemison</code>, and directly in <code>D:\\ps1\\demo\\samples\\</code> for the last four.</p>
  <table class="plain practice"><colgroup><col style="width:31%"><col style="width:33%"><col style="width:26%"><col style="width:10%"></colgroup><thead><tr><th>Photo</th><th>What it shows</th><th>The answer you should get</th><th>Score</th></tr></thead><tbody>${rows}</tbody></table>
  <p class="small">The answers and scores in this table were produced by the running system when this manual was built. Scores can differ slightly on another computer; the <b>answers</b> should be the same. Photo licences: <code>demo\\samples\\SOURCES.md</code>.</p>
  <p class="small"><b>Tidy up afterwards:</b> Identity Gallery → <b>Reset demo gallery</b> (type the phrase) removes both example people.</p>`));

pages.push(page(`<h1 class="ph">Quick reference card</h1>
  <p class="small">Print this page and keep it next to the computer.</p>
  <div class="quick">
  <div><h3>Start</h3><p>Double-click <b>Start OpenID Vision.bat</b>.<br>Keep the black window open.<br>Browser address: <code>http://127.0.0.1:8000</code><br>Top right must say <b>Models ready</b>.<br>No photos? Press <b>Run the example</b> on the home page.</p></div>
  <div><h3>Add a person (once)</h3><p><b>Identity Gallery → Enroll identity</b><br>1. code name (not a real name)<br>2. add 2-5 clear face photos<br>3. tick “tight crop” and the <b>consent</b> box<br>4. click <b>Enroll identity</b> → <b>Done</b><br>Check: “<b>… with a face</b>” (green).</p></div>
  <div><h3>Check a photo</h3><p><b>Match Studio</b><br>1. add the photo<br>2. tick “already a person crop” (one person) <i>or</i> <b>Detect people</b> / “Match everyone” (several)<br>3. <b>Run re-identification</b><br>4. read the <b>Decision</b> card (top right)</p></div>
  <div><h3>The three answers</h3><p>${badge("accepted")} someone you added - nothing to do<br>${badge("unknown")} nobody matches - nothing to do<br>${badge("review_required")} the system is unsure - <b>you look</b>: <b>Review candidates</b></p></div>
  <div><h3>Reading the bar</h3><p>Bar reaches the <b>black tick</b> = passes.<br>A <b>score</b>, not a percentage.<br>Face decides when clearly visible; clothes only support.</p></div>
  <div><h3>Finish</h3><p>Delete people you no longer need (<b>click the card → Delete identity</b>).<br>Close the <b>black window</b> to stop.</p></div></div>
  <div class="rulebox"><b>Remember:</b> only photos of people who agreed · a MATCH is a strong hint, not proof · UNKNOWN is not an accusation · never decide something important about a person from this alone.</div>`));

// ================================================================================================================ CSS + PDF
const css = `
@page { size: A4; margin: 15mm 14mm 17mm } @page :first { margin: 0 }
* { box-sizing: border-box } html { -webkit-print-color-adjust: exact; print-color-adjust: exact }
body { font-family: "Segoe UI", Arial, sans-serif; color: #1a1d23; font-size: 11pt; line-height: 1.45; margin: 0 }
.cover { background: #0f1217; color: #e9ecf1; height: 296mm; padding: 64pt 50pt; break-after: page }
.cover h1 { font-size: 50pt; margin: 4pt 0 2pt } .kicker { color: #ff5a52; font-weight: 700; letter-spacing: .16em; font-size: 12pt; margin: 0 }
.tag { color: #ff8f8a; font-size: 19pt; margin: 0 0 18pt } .lead { font-size: 15pt; color: #c5ccd8; max-width: 400pt }
.coverbox { background: #151a22; border: 1px solid #2a303b; border-radius: 8pt; padding: 12pt 16pt; margin-top: 16pt; font-size: 12pt } .coverbox ul { margin: 6pt 0 0; padding-left: 16pt } .coverbox li { margin: 3pt 0 }
.bigaddr { font: 700 24pt Consolas, monospace; color: #ffb4af; margin: 6pt 0 } .small { font-size: 9.5pt; color: #5b6472 } .cover .small { color: #7c8594; margin-top: 30pt }
.page { break-before: page } .ph { font-size: 22pt; margin: 0 0 8pt; padding-bottom: 5pt; border-bottom: 3px solid #e53935 }
h2 { font-size: 17pt; margin: 0 } h3 { font-size: 12.5pt; margin: 14pt 0 5pt; break-after: avoid } h4 { margin: 0 0 4pt; font-size: 10.5pt; color: #4b5361 } p { margin: 4pt 0 } .big { font-size: 12.5pt }
.stephead { display: flex; align-items: center; gap: 12pt; margin-bottom: 9pt; padding-bottom: 7pt; border-bottom: 3px solid #e53935 } .stephead p { margin: 1pt 0 0; color: #4b5361; font-size: 10.5pt }
.bignum { flex: none; width: 34pt; height: 34pt; border-radius: 50%; background: #e53935; color: #fff; font: 800 20pt/34pt "Segoe UI"; text-align: center }
.todo { padding-left: 18pt; margin: 4pt 0 8pt } .todo li { margin: 3pt 0; padding-left: 3pt } .todo li::marker { font-weight: 800; color: #e53935 }
.shot { display: block; border: 1px solid #cfd5dd; border-radius: 6pt; margin: 4pt auto 6pt; box-shadow: 0 1px 4px rgba(0,0,0,.12); break-inside: avoid }
.legend { list-style: none; margin: 3pt 0 6pt; padding: 0 } .legend li { display: flex; gap: 8pt; align-items: flex-start; margin: 4pt 0; break-inside: avoid; font-size: 10.3pt } .legend li > div { flex: 1 }
.n { flex: none; display: inline-block; width: 18pt; height: 18pt; border-radius: 50%; background: #e53935; color: #fff; font: 700 10pt/18pt "Segoe UI"; text-align: center }
.cols { display: grid; grid-template-columns: 1.12fr 1fr; gap: 14pt; align-items: start; break-inside: avoid } .cols .c1 { min-width: 0 } .cols .c2 { min-width: 0 }
.cols.two { grid-template-columns: 1fr 1fr } .narrow { max-width: 200pt } .narrow2 { max-width: 100% } .narrow3 { max-width: 100% }
.box { border-radius: 6pt; padding: 6pt 10pt; margin: 8pt 0; font-size: 10.3pt; break-inside: avoid; border: 1px solid } .tip { background: #eaf5ff; border-color: #a9d0f5 } .warn { background: #fff3d6; border-color: #f0c978 } .note { background: #f1f3f6; border-color: #d3d8e0 } .ok { background: #e6f6ec; border-color: #9bd3b1 }
.badge { display: inline-block; font-weight: 800; font-size: 9.5pt; letter-spacing: .05em; padding: 1.5pt 9pt; border-radius: 99pt; border: 1px solid } .accepted { background: #e4f5ea; color: #17673a; border-color: #8fcfa8 } .unknown { background: #eceff3; color: #3b4452; border-color: #c4ccd7 } .review_required { background: #fff1d6; color: #7a4a00; border-color: #efc783 }
.btn { display: inline-block; background: #fff; border: 1px solid #b9c0cb; border-radius: 99pt; padding: 0 8pt; font-weight: 600; font-size: 9.8pt; white-space: nowrap }
table.plain { border-collapse: collapse; width: 100%; margin: 6pt 0; font-size: 10.2pt } .plain th, .plain td { border: 1px solid #dfe3e9; padding: 4pt 7pt; text-align: left; vertical-align: top } .plain th { background: #f4f5f8; font-size: 9pt; text-transform: uppercase; letter-spacing: .04em } .plain tr { break-inside: avoid }
.screens td:first-child { width: 28pt; text-align: center } .often { color: #17673a; font-weight: 700 } .mono, code { font-family: Consolas, monospace; font-size: 9pt } code { background: #f1f3f6; padding: 0 3pt; border-radius: 3pt }
.three { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10pt } .ans p { font-size: 9.6pt; margin-top: 5pt } .ans .shot { margin: 0 auto }
.rules li { margin: 5pt 0 } .plain-list li { margin: 4pt 0 }
.flow { display: flex; align-items: stretch; gap: 3pt; margin: 8pt 0 12pt } .flow > div { flex: 1; background: #fff4f3; border: 1px solid #f2b8b4; border-radius: 8pt; padding: 7pt 5pt; text-align: center; display: flex; flex-direction: column; gap: 2pt; font-size: 9.5pt } .flow small { color: #5b6472; font-size: 8.3pt } .flow i { align-self: center; font-style: normal; color: #e53935; font-weight: 800 } .fn { display: inline-block; align-self: center; width: 20pt; height: 20pt; border-radius: 50%; background: #e53935; color: #fff; font: 800 11pt/20pt "Segoe UI" }
.side2 { display: grid; grid-template-columns: 1.15fr 1fr; gap: 14pt; align-items: start } .term { background: #0c0c0c; border-radius: 6pt; overflow: hidden; border: 1px solid #333 } .termbar { background: #2b2b2b; color: #ddd; font-size: 8.5pt; padding: 3pt 8pt } .termbar i { display: inline-block; width: 7pt; height: 7pt; border-radius: 50%; background: #666; margin-right: 4pt } .term pre { color: #cfcfcf; font: 7.1pt/1.35 Consolas, monospace; padding: 7pt 9pt; margin: 0; white-space: pre-wrap }
.addr { display: flex; align-items: center; gap: 8pt; background: #eef1f5; border: 1px solid #c9d0da; border-radius: 99pt; padding: 7pt 12pt; margin: 4pt 0 6pt } .addr .dots { width: 10pt; height: 10pt; border-radius: 50%; background: #9aa3b2 } .addr .field { font: 600 12pt Consolas, monospace; background: #fff; border-radius: 99pt; padding: 2pt 12pt; flex: 1 }
.answers td:first-child { width: 80pt }
.practice { font-size: 9pt; table-layout: fixed; margin: 3pt 0 } .practice td, .practice th { padding: 1.5pt 6pt } .practice td:nth-child(1) { font-size: 7.6pt; word-break: break-all } .nw { white-space: nowrap } .wrapok { white-space: normal; display: inline-block } .p1 code { white-space: nowrap }
.legend.cols2 { columns: 2; column-gap: 16pt } .legend.cols2 li { break-inside: avoid }
.quick { display: grid; grid-template-columns: 1fr 1fr; gap: 10pt } .quick > div { border: 2px solid #e53935; border-radius: 8pt; padding: 6pt 11pt } .quick h3 { margin: 0 0 3pt; color: #e53935 } .quick p { font-size: 10.6pt }
.rulebox { margin-top: 12pt; padding: 8pt 12pt; border-radius: 8pt; background: #1a1d23; color: #fff; font-size: 11pt }
.trouble td:first-child { width: 150pt }
`;
const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>OpenID Vision - User Manual</title><style>${css}</style></head><body>${pages.join("\n")}</body></html>`;
const htmlPath = path.join(build, "USER_MANUAL.html");
writeFileSync(htmlPath, html, "utf8");

const executablePath = [
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe", "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
].find(existsSync);
const profile = path.join(root, ".tools", "tmp", "edge-profile-docs");
mkdirSync(profile, { recursive: true });
const browser = await puppeteer.launch({ executablePath, headless: true, userDataDir: profile, args: ["--no-sandbox", "--allow-file-access-from-files"] });
const tab = await browser.newPage();
await tab.goto(pathToFileURL(htmlPath).href, { waitUntil: "networkidle0" });
await tab.evaluate(() => document.fonts?.ready);
const footer = `<div style="font-size:8px;width:100%;text-align:center;color:#8a93a1;font-family:Segoe UI,Arial">OpenID Vision - User Manual - page <span class="pageNumber"></span> of <span class="totalPages"></span></div>`;
await tab.pdf({ path: target, preferCSSPageSize: true, printBackground: true, displayHeaderFooter: true, headerTemplate: "<span></span>", footerTemplate: footer });
await browser.close();
console.log("wrote", target);
