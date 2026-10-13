/*
 * Build the 10-minute presentation script for a non-technical audience (company HR).
 *
 * In plain words: a step-by-step PDF - what to say, what to click, how long it takes, one clear everyday example, the answers to the
 * questions HR usually asks, and a backup plan. Numbers are read from docs/results/open_set_example.json, not typed by hand.
 *     node scripts/build_hr_presentation.mjs        ->  OpenID-Vision-HR-Presentation-10min.pdf
 * Needs puppeteer-core (cd .tools\shots; npm install puppeteer-core) and Microsoft Edge or Chrome.
 */
import { createRequire } from "node:module";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const require = createRequire(path.join(root, ".tools", "shots", "package.json"));
const puppeteer = require("puppeteer-core");

const ex = JSON.parse(readFileSync(path.join(root, "docs", "results", "open_set_example.json"), "utf8"));
const pick = (label, column) => { const s = ex.summary.find((r) => r.label === label && r.column === column); return `${s.right} of ${s.total}`; };
const total = ex.cases.length;
const sameSuit = ex.cases.filter((c) => c.group === "lookalike");
const acceptedByClothes = sameSuit.filter((c) => c.clothes_only.verdict === "false_accept").length;
const acceptedByFace = sameSuit.filter((c) => c.face_body.verdict === "false_accept").length;

const img = (name, width = "100%") => `<img class="shot" style="width:${width}" src="${pathToFileURL(path.join(root, "demo", "manual_images", name + ".jpg")).href}" alt="">`;
const out = path.join(root, "OpenID-Vision-HR-Presentation-10min.pdf");
const build = path.join(root, "demo", "_build");
mkdirSync(build, { recursive: true });

const say = (t) => `<div class="say"><b>Say:</b> ${t}</div>`;
const doit = (t) => `<div class="do"><b>Do:</b> ${t}</div>`;
const step = (time, title, body) => `<section class="page"><div class="stephead"><span class="time">${time}</span><h2>${title}</h2></div>${body}</section>`;

const pages = [];

pages.push(`<section class="cover"><p class="kicker">PRESENTATION SCRIPT - 10 MINUTES</p><h1>OpenID Vision</h1><p class="tag">Know when to match. Know when to reject.</p>
<p class="lead">A step-by-step guide for presenting to HR: what to say, what to show, with one everyday example.</p>
<div class="box dark"><b>The one sentence to remember</b><p class="big">"It recognises the people it knows, says <u>unknown</u> to everyone else - even a stranger in the same uniform - and asks a human when it is not sure."</p></div>
<div class="box dark"><b>Your 10 minutes at a glance</b>
<table class="plan"><tr><td>0:00</td><td>The problem, in a story</td></tr><tr><td>1:00</td><td>The everyday example (office door)</td></tr><tr><td>2:30</td><td>Live demo: press one button</td></tr><tr><td>5:30</td><td>Three answers - and the human in the loop</td></tr><tr><td>7:00</td><td>Responsible use: consent, privacy, limits</td></tr><tr><td>8:30</td><td>What was built, and what it shows about the work</td></tr><tr><td>9:30</td><td>Close</td></tr></table></div>
<p class="small">Independent technical prototype responding to the Zed Digital PS-1 assignment - not an official Zed Digital product. Research use with consenting people only.</p></section>`);

pages.push(`<section class="page"><h1 class="ph">Before you start (5 minutes, once)</h1>
<ol class="todo"><li>Double-click <b>Start OpenID Vision.bat</b> (folder <code>D:\\ps1</code>). Keep the black window open. The browser opens by itself.</li>
<li>Check the top right says <b>Models ready</b>. If not, wait 30 seconds and press F5.</li>
<li>You will land on the <b>home page (Command Center)</b>. Do <u>not</u> press "Run the example" yet - you will do it live, it takes about 10 seconds.</li>
<li>Have this PDF open on a second screen or printed. Read the grey <b>Say</b> boxes aloud in your own words; the blue <b>Do</b> boxes are the clicks.</li></ol>
<div class="box warn"><b>Rules for the room.</b> Use only people who agreed to be shown. The example uses public-domain photographs, so nobody in the audience is ever used without consent.</div>
<h3>Who you are talking to - and what they care about</h3>
<table class="plain"><thead><tr><th>HR cares about</th><th>So you show</th></tr></thead><tbody>
<tr><td>Is the decision fair and explainable?</td><td>Every answer comes with its score and its reason in words.</td></tr>
<tr><td>Is a human still in charge?</td><td>The third answer, <b>REVIEW</b>, means "a person decides".</td></tr>
<tr><td>Is it legal and respectful of privacy?</td><td>Consent, deletion, local-only storage, and the honest limits.</td></tr>
<tr><td>What does this say about the person who built it?</td><td>It was measured, tested (427 + 157 automated tests) and documented - and it admits what it cannot do.</td></tr></tbody></table>
<div class="box note"><b>Golden rule.</b> Only say what the screen can show. If you are asked something you do not know, say: <i>"I don't know - here is how I would find out."</i> That answer builds trust.</div></section>`);

pages.push(step("0:00 - 2:30", "Steps 1 and 2: the problem and the everyday example",
`<h3>Step 1 (0:00 - 1:00) The problem, as a story</h3>
${say(`"Imagine a guard at an office door who only looks at <b>uniforms</b>. Anyone in the right uniform walks in - including a stranger wearing a look-alike jacket. Many computer systems that recognise people work exactly like that guard: they compare clothes and build. This project is the same guard, trained to behave properly."`)}
<h3>Step 2 (1:00 - 2:30) The example: Priya and the office door</h3>
<table class="plain story"><thead><tr><th></th><th>Who</th><th>What happens</th></tr></thead><tbody>
<tr><td>1</td><td><b>Priya</b> joins the company and <b>agrees</b> to be enrolled: the system keeps her face and body fingerprint (a list of numbers, not a photo gallery).</td><td>She is now "known".</td></tr>
<tr><td>2</td><td>Next week <b>Priya returns</b> in a different jacket.</td><td>Right answer: <span class="b match">MATCH</span> - it is her.</td></tr>
<tr><td>3</td><td><b>A visitor</b> nobody has seen, wearing the <b>same jacket</b> Priya wore when she enrolled.</td><td>Right answer: <span class="b unknown">UNKNOWN</span> - not enrolled.</td></tr>
<tr><td>4</td><td>Priya walks past with her back to the camera, face not visible.</td><td>Right answer: <span class="b review">REVIEW</span> - ask a person.</td></tr></tbody></table>
${say(`"A clothes-only system gets row 2 wrong - it does not recognise Priya in a new jacket - and row 3 wrong - it lets the visitor in. Our system uses the <b>face first</b> and the clothes only as support. Let me show you with real photos, not a drawing."`)}
<div class="box note"><b>Why HR should care.</b> The same question appears in access control, attendance and any automated decision about people: <i>"is this really who the system thinks it is - and what happens when it is not sure?"</i></div>`));

pages.push(step("2:30 - 5:30", "Step 3: the live demo (one button)",
`${doit(`On the home page point at the three cards: <b>1 Enroll people, 2 Match photos, 3 See the open-set analysis</b>. Then click <b>Run the example</b>. A progress bar runs for about 10 seconds.`)}
${say(`"The system now has three example people enrolled and is shown 13 photos it has never seen: known people in new clothes, strangers, and - the hard part - three strangers wearing the <b>same orange flight suit</b> as the people enrolled. Public-domain photographs, nothing is saved."`)}
${img("01b_example_result")}
<h3>Read it in 30 seconds (point with the mouse)</h3>
<table class="plain"><thead><tr><th>Question (left column)</th><th>Face + body (our system)</th><th>Clothes only</th></tr></thead><tbody>
<tr><td>Known people recognised</td><td class="ok">${pick("Known people recognised", "face_body")}</td><td class="bad">${pick("Known people recognised", "clothes_only")}</td></tr>
<tr><td>Strangers in the <b>same clothes</b> refused</td><td class="ok">${pick("Strangers in the same clothes refused", "face_body")}</td><td class="bad">${pick("Strangers in the same clothes refused", "clothes_only")}</td></tr>
<tr><td>All ${total} photos right</td><td class="ok">${pick("All photos", "face_body")}</td><td class="bad">${pick("All photos", "clothes_only")}</td></tr></tbody></table>
${say(`"Green tick is good, red cross is not. With clothes alone, <b>${acceptedByClothes} of ${sameSuit.length}</b> strangers in the same suit were let in, and none of the five real people was recognised. With the face as well: <b>${acceptedByFace} strangers let in</b>, and all five recognised."`)}</section>`.replace("</section>", "") ));

pages.push(`<section class="page"><div class="stephead"><span class="time">2:30 - 5:30</span><h2>Step 3 (continued): one photo, both answers</h2></div>
${doit(`Scroll to the group <b>"Strangers in the SAME clothes as an enrolled person"</b>. Click <b>Why this answer</b> on the first row.`)}
${img("01c_example_rows")}
<ul class="plainlist"><li><b>Left:</b> a stranger in the same orange suit. The right answer is UNKNOWN.</li>
<li><b>Middle (our system):</b> UNKNOWN, right answer. The face looked nothing like the enrolled people (similarity <b>0.19</b>, it needed <b>0.465</b>).</li>
<li><b>Right (clothes only):</b> MATCH - <b>"Stranger accepted"</b> in red. Clothes similarity <b>0.81</b> against a line of <b>0.70</b> (a score, not a percentage).</li></ul>
${say(`"This is the whole project in one row. The clothes said 'yes, I know this person'. The face said 'no, this is someone else'. The system trusts the face."`)}
<h3>Optional (30 seconds): the slider</h3>
${doit(`Drag <b>"Try it: move the face line"</b> to the far left, then back with the <b>Back to the system's 0.465</b> button.`)}
${say(`"Lower the bar and strangers start getting in; raise it and real people are missed. Where to put the bar is a trade-off between convenience and safety - a decision for people, which is why the system is built to be adjustable and measured, not fixed."`)}
<div class="box warn"><b>Say this before anyone asks:</b> "This is 13 photographs - a demonstration of <u>how it thinks</u>, not a measurement of how accurate it is in your building."</div></section>`);

pages.push(`<section class="page"><div class="stephead"><span class="time">5:30 - 7:00</span><h2>Step 4: three answers, and the human in the loop</h2></div>
<div class="three"><div class="ans">${img("ans_match")}<p><span class="b match">MATCH</span><br>"This is someone enrolled." Strong evidence: nothing more to do.</p></div>
<div class="ans">${img("ans_unknown")}<p><span class="b unknown">UNKNOWN</span><br>"Nobody enrolled matches." Not an accusation about the person.</p></div>
<div class="ans">${img("ans_review")}<p><span class="b review">REVIEW</span><br>"Not sure - a person decides." Poor photo or no visible face.</p></div></div>
${say(`"Notice there are <b>three</b> answers, not two. The system is allowed to say 'I am not sure'. When the face is hidden, it does <u>not</u> guess from clothes - it hands the decision to a human. In the example, both blurred-face photos went to REVIEW."`)}
<h3>Why this matters for HR</h3>
<table class="plain"><tbody>
<tr><td><b>Explainable</b></td><td>Every answer shows the score, the line it had to reach, and a sentence explaining why (the <b>Why this answer</b> link).</td></tr>
<tr><td><b>Human oversight</b></td><td>Uncertain cases are routed to a person by design, not by afterthought.</td></tr>
<tr><td><b>Auditable</b></td><td>Every decision is recorded with the rule version that produced it, and can be exported.</td></tr>
<tr><td><b>Honest about uncertainty</b></td><td>The threshold is labelled <b>Unvalidated</b> on screen until it is calibrated on real data.</td></tr></tbody></table>
${doit(`Optional: click <b>Match Studio</b> in the menu and show the empty page - "this is where you would upload a photo of a real, consenting volunteer."`)}</section>`);

pages.push(`<section class="page"><div class="stephead"><span class="time">7:00 - 8:30</span><h2>Step 5: responsible use - say this calmly</h2></div>
${say(`"A face fingerprint is <b>biometric data</b>, so the rules around it matter as much as the technology."`)}
<table class="plain"><thead><tr><th>Topic</th><th>What the system does</th></tr></thead><tbody>
<tr><td><b>Consent</b></td><td>Enrolling a person requires an explicit consent tick. Only enrolled, consenting people are ever matched.</td></tr>
<tr><td><b>Storage</b></td><td>Everything stays on this computer. No cloud, no internet, no camera feed.</td></tr>
<tr><td><b>Deletion</b></td><td>Deleting a person erases their photos and their face and body fingerprints. Uploaded query photos expire after 24 hours.</td></tr>
<tr><td><b>Unknown people</b></td><td>Never saved, grouped or tracked. UNKNOWN only means "not enrolled".</td></tr>
<tr><td><b>Switch-off</b></td><td>One setting returns to the clothes-and-body-only mode; every rule change is versioned and logged.</td></tr></tbody></table>
<h3>Limits - state them before you are asked</h3>
<ul class="plainlist"><li><b>Not a phone's Face ID.</b> It is ordinary 2-D photo matching: no depth sensor, no check that a real person (not a photograph) is present.</li>
<li><b>Fairness across groups is not measured.</b> Accuracy by age, skin tone or gender has not been tested.</li>
<li><b>Tested on easy data.</b> The face part scored 98.9% on a standard public benchmark (LFW); the pedestrian-camera benchmark has <b>not</b> been run.</li>
<li><b>The example is a demonstration</b> of 13 photos, not an error rate for any real building.</li>
<li><b>Legal basis needed.</b> Biometric data is regulated (GDPR, India's DPDP Act, Illinois BIPA): a real deployment needs a legal basis and an impact assessment.</li></ul>
${say(`"I would rather tell you what it cannot do today than have you discover it later."`)}</section>`);

pages.push(`<section class="page"><div class="stephead"><span class="time">8:30 - 10:00</span><h2>Steps 6 and 7: what was built, and the close</h2></div>
<h3>Step 6 (8:30 - 9:30) What was built - in plain words</h3>
<table class="plain"><tbody>
<tr><td><b>A working web application</b></td><td>seven screens: add people, check a photo, check a video clip, find look-alike failures, measure accuracy, view settings, and a home page with the example.</td></tr>
<tr><td><b>A written decision rule</b></td><td>"Face first, clothes second, a human when unsure" - a small, tested piece of logic, not a black box.</td></tr>
<tr><td><b>Measured, not claimed</b></td><td>Every number on screen is computed by the system; every claim in the documents has a script that reproduces it.</td></tr>
<tr><td><b>Tested and documented</b></td><td>427 automated backend tests and 157 interface tests pass; a 30-page user manual, a jury guide and a privacy document are included.</td></tr></tbody></table>
${say(`"What I want you to take from this about how I work: I tested it, found a real weakness - clothes alone let strangers in - fixed it, measured the improvement, and wrote down honestly what is still unproven."`)}
<h3>Step 7 (9:30 - 10:00) Close</h3>
${say(`"To summarise: it recognises people it knows, refuses strangers even in the same clothes, and asks a human when unsure. It is a prototype, built responsibly, with limits I have told you about. Thank you - I am happy to take questions."`)}
<div class="box note"><b>Next steps if asked:</b> run the pedestrian benchmark, calibrate the thresholds on real camera footage, add a check that a real person (not a photo) is present, and measure accuracy across different groups of people.</div></section>`);

pages.push(`<section class="page"><h1 class="ph">Questions HR may ask - and honest answers</h1>
<table class="plain qa"><tbody>
<tr><td><b>Is it accurate?</b></td><td>The face part scored 98.9% on a standard public test; in our small end-to-end test 20 of 20 same-person photos matched and 0 of 60 strangers were accepted. In the home-page example, 13 of 13 photos were right. Accuracy on your own cameras has <b>not</b> been measured - that is the next step.</td></tr>
<tr><td><b>Could it discriminate against some people?</b></td><td>Possibly - face systems can perform differently across groups, and we have <b>not</b> measured it. That is why uncertain cases go to a person, and why it should not decide anything important on its own.</td></tr>
<tr><td><b>Is it legal to use on employees?</b></td><td>Only with a legal basis, informed consent and an impact assessment. The prototype enforces consent at enrolment; the legal decision belongs to the company and its lawyers.</td></tr>
<tr><td><b>Where does the data go?</b></td><td>Nowhere. It stays on the one computer running it. Deleting a person erases their data.</td></tr>
<tr><td><b>Can it be fooled by a photograph?</b></td><td>Yes. There is no liveness check. Real deployments add depth or infrared sensing.</td></tr>
<tr><td><b>Why not just use the face?</b></td><td>Faces are often not visible (back view, distance, blur). Then the system falls back to the body - and, because that is weaker, asks a human.</td></tr>
<tr><td><b>Does it track people around the building?</b></td><td>No. Video is checked frame by frame; nothing follows a person from frame to frame.</td></tr>
<tr><td><b>What would it take to use it for real?</b></td><td>Run the benchmark, calibrate on your cameras, add liveness checks, measure fairness, get legal approval - then a pilot with consenting volunteers.</td></tr>
<tr><td><b>What was your part?</b></td><td>Describe your own contribution truthfully (design, building, testing, documenting). Do not claim anything you did not do.</td></tr>
<tr><td><b>Something you do not know</b></td><td>"I don't know - here is how I would find out." Always acceptable.</td></tr></tbody></table>
<h3>If the demo does not work</h3>
<ol class="todo"><li>Models not ready: wait 30 seconds, press F5.</li><li>Example button greyed out: say so, and show the screenshots in this PDF (pages 4 and 5) - they are from a real run.</li><li>Total failure: open <code>demo\\JURY_DECK.pdf</code> (15 slides) - the same story with the measurements.</li></ol></section>`);

const css = `
@page { size: A4; margin: 14mm 14mm 16mm } @page :first { margin: 0 }
* { box-sizing: border-box } body { font-family: "Segoe UI", Arial, sans-serif; color: #1a1d23; font-size: 10.6pt; line-height: 1.42; margin: 0 }
.cover { background: #0f1217; color: #e9ecf1; height: 296mm; padding: 54pt 46pt; break-after: page } .cover h1 { font-size: 46pt; margin: 4pt 0 2pt } .kicker { color: #ff5a52; font-weight: 700; letter-spacing: .14em; font-size: 11pt; margin: 0 }
.tag { color: #ff8f8a; font-size: 18pt; margin: 0 0 12pt } .lead { font-size: 13.5pt; color: #c5ccd8; max-width: 420pt } .big { font-size: 13pt; margin: 6pt 0 0 }
.box { border-radius: 7pt; padding: 7pt 11pt; margin: 9pt 0; font-size: 10.2pt; border: 1px solid; break-inside: avoid } .dark { background: #151a22; border-color: #2a303b; margin-top: 14pt } .warn { background: #fff3d6; border-color: #f0c978 } .note { background: #eaf5ff; border-color: #a9d0f5 }
.plan { border-collapse: collapse; margin-top: 6pt; width: 100% } .plan td { padding: 3pt 8pt; border-bottom: 1px solid #2a303b; font-size: 11.5pt } .plan td:first-child { color: #ff8f8a; font-weight: 700; width: 50pt }
.small { font-size: 9pt; color: #7c8594; margin-top: 18pt } .page { break-before: page } .ph { font-size: 21pt; margin: 0 0 8pt; padding-bottom: 5pt; border-bottom: 3px solid #e53935 }
.stephead { display: flex; align-items: center; gap: 12pt; border-bottom: 3px solid #e53935; padding-bottom: 6pt; margin-bottom: 8pt } .stephead h2 { font-size: 16pt; margin: 0 } .time { background: #e53935; color: #fff; font-weight: 700; padding: 4pt 10pt; border-radius: 99pt; font-size: 11pt; white-space: nowrap }
h3 { font-size: 12pt; margin: 11pt 0 4pt } p { margin: 4pt 0 } code { background: #f1f3f6; padding: 0 3pt; border-radius: 3pt; font-size: 9.5pt }
.say, .do { border-radius: 6pt; padding: 6pt 11pt; margin: 6pt 0; break-inside: avoid } .say { background: #f1f3f6; border-left: 5px solid #5b6472 } .do { background: #e8f1ff; border-left: 5px solid #2f6fe0 }
.todo { padding-left: 18pt } .todo li { margin: 5pt 0 } .plainlist { padding-left: 16pt; margin: 4pt 0 } .plainlist li { margin: 4pt 0 }
table.plain { border-collapse: collapse; width: 100%; margin: 5pt 0; font-size: 10pt } .plain th, .plain td { border: 1px solid #dfe3e9; padding: 4pt 7pt; text-align: left; vertical-align: top } .plain th { background: #f4f5f8; font-size: 8.8pt; text-transform: uppercase; letter-spacing: .04em } .plain tr { break-inside: avoid }
.ok { color: #17673a; font-weight: 700; font-size: 12pt } .bad { color: #b3261e; font-weight: 700; font-size: 12pt }
.b { display: inline-block; font-weight: 800; font-size: 8.5pt; letter-spacing: .05em; padding: 1pt 8pt; border-radius: 99pt; border: 1px solid } .match { background: #e4f5ea; color: #17673a; border-color: #9ad4b0 } .unknown { background: #eceff3; color: #3b4452; border-color: #c9d0da } .review { background: #fff1d6; color: #7a4a00; border-color: #f0cc85 }
.shot { display: block; border: 1px solid #cfd5dd; border-radius: 6pt; margin: 6pt auto; box-shadow: 0 1px 4px rgba(0,0,0,.12) }
.three { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10pt } .ans p { font-size: 9.6pt }
.qa td:first-child { width: 28% } .qa td { font-size: 9.6pt }`;
const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>OpenID Vision - 10-minute presentation script</title><style>${css}</style></head><body>${pages.join("\n")}</body></html>`;
const htmlPath = path.join(build, "HR_PRESENTATION.html");
writeFileSync(htmlPath, html, "utf8");

const executablePath = ["C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe", "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe", "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"].find(existsSync);
if (!executablePath) throw new Error("Neither Edge nor Chrome was found.");
const profile = path.join(root, ".tools", "tmp", "edge-profile-docs");
mkdirSync(profile, { recursive: true });
const browser = await puppeteer.launch({ executablePath, headless: true, userDataDir: profile, args: ["--no-sandbox", "--allow-file-access-from-files"] });
const tab = await browser.newPage();
await tab.goto(pathToFileURL(htmlPath).href, { waitUntil: "networkidle0" });
const footer = `<div style="font-size:8px;width:100%;text-align:center;color:#8a93a1;font-family:Segoe UI,Arial">OpenID Vision - 10-minute presentation script - page <span class="pageNumber"></span> of <span class="totalPages"></span></div>`;
await tab.pdf({ path: out, printBackground: true, preferCSSPageSize: true, displayHeaderFooter: true, headerTemplate: "<span></span>", footerTemplate: footer });
await browser.close();
console.log("wrote", path.relative(root, out));
