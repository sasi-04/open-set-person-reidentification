# How to explain OpenID Vision to the jury

*Written for someone who did not write the code. Everything here is true of the project as it stands today; where something has
**not** been done or measured, this guide says so, because **admitting limits calmly is what makes the rest believable.***

**How to use it.** Read §1 and §2 until you can say them without looking. Practise the demo in §5 twice. Skim §6 (numbers) and
§7 (limits) the night before. Keep §8 (questions) open while you present.

---

## 1. The 60-second version (say this first)

> "Imagine a security guard who only looks at **uniforms**. Anyone in the right uniform walks in - including a stranger in a
> look-alike jacket. That is how most 'person re-identification' systems fail: they match clothing and build, so a different
> person who dresses the same gets accepted.
>
> **OpenID Vision** is the same guard, retrained to behave properly. It looks at the **face first** and the **body and clothing
> second**. It only says **MATCH** when the evidence is strong, it says **UNKNOWN** to somebody it has never seen, and when it
> is not sure it says **REVIEW** - 'ask a human'.
>
> We measured it instead of just claiming it: on a standard public face benchmark the face part is **98.9 % accurate**; and in
> our end-to-end test the old clothing-only matcher let in **48 of 60 strangers**, the new one let in **none**. We are also open
> about what is *not* proven: it is not a phone's Face ID, it has not been tested on a pedestrian-camera benchmark yet, and it
> must only be used with people's consent."

That paragraph contains the problem, the idea, the proof, and the honesty. If you only get one minute, use it.

## 2. The same story in four pictures

**Picture 1 - the three answers (a door with a guard).**

| The screen says | Meaning in plain words | The door |
|---|---|---|
| **MATCH** | "This is enrolled person X" - the evidence is strong | opens |
| **UNKNOWN** | "I have never seen this person" - nobody enrolled is supported by the evidence | stays shut |
| **REVIEW** | "I'm not sure - a human should look" (blurry photo, face too small, borderline score, no face visible) | guard calls a supervisor |

*UNKNOWN is not an accusation.* It means "no enrolled person is supported", never "this person is suspicious". Unknown people are
never saved, grouped or tracked.

**Picture 2 - why clothing alone fails.** Two different people in the same blue uniform look almost identical to a clothing-based
model (similarity about 0.9). Their faces are clearly different (similarity about 0.1). So: *clothing says "same", the face says
"different" - and the face wins.* That is the whole point of the project, and the one screen that shows it best is the **Evidence**
card in Match Studio (face bar, body bar, side by side).

**Picture 3 - the pipeline, in the order the system works.**

```
  photo
    │
    ▼
  1 find the people ──► 2 check quality ──► 3 find the face ──► 4 make two fingerprints
    (detector)           (blurry? tiny?)       (is it usable?)     face: 128 numbers
                                                                   body: 512 numbers
                                                                         │
                                                                         ▼
  7 record what happened ◄── 6 decide: MATCH /          ◄──────── 5 compare with everyone
    (history, exportable)      UNKNOWN / REVIEW                     enrolled
                               (explicit, versioned rule)
```

1. **Find the people** - a neural network draws a box around each person.
2. **Check quality** - too blurry, too small or cut off by the frame? Then the system will not pretend to be sure.
3. **Find the face** - and judge it: big enough? sharp? facing the camera? If not, it is *not used* and the screen says why.
4. **Fingerprints** - each picture becomes a list of numbers. Two pictures of the same face give similar lists. (Technical name:
   *embedding*; the similarity is the *cosine* of the angle between the lists, from -1 to 1. It is **not** a percentage.)
5. **Compare** with every enrolled person.
6. **Decide** with a written rule (below). A *nearest neighbour is never accepted automatically*: being the closest is not enough.
7. **Record** the scores, the reason and the rule version, so any decision can be explained later.

**Picture 4 - the decision rule on one line.** *If a usable face is visible, the face decides. If not, the body is used, but clothing
alone is not trusted enough for an automatic MATCH, so a human is asked.* (Full rule: `docs/FACE_AND_BODY_MATCHING.md` §3.)

## 3. What is new compared with the original brief (and why you should say so)

The original assignment (PS-1) asks for *open-set re-identification under low inter-class variance*: strangers who look like
enrolled people. Version 1 of this project solved it with a whole-body model plus an explicit decision engine, an evaluation lab and a
"Lookalike Failure Lab" that hunts for exactly the mistakes that matter. When the first version was tested with real people it
accepted a stranger because of similar clothing. So **face matching was added** (this changes the privacy position, and the
documentation says so). Presenting that as *"we tested it, found the weakness, measured it, fixed it, and re-measured"* is a
strength - not an embarrassment.

## 4. The seven screens in one sentence each

| Screen | One sentence | Show it when asked about... |
|---|---|---|
| **Command Center** (the home page) | the three essentials - enroll, match, open-set analysis - and a one-click **example** with 13 public-domain photos (known people, strangers, strangers in the *same clothes*; face + body against clothes-only). Below: what is loaded and how far the threshold can be trusted ("Unvalidated" is shown in amber on purpose) | **the first thing to show - it needs no volunteers**; honesty / status |
| **Identity Gallery** | who is enrolled (with consent), how many have a usable face on file | privacy, consent |
| **Match Studio** | upload a photo: see the people found, the decision, the face and body scores, the colour cues | the core demo |
| **Video Explorer** | the same decision for each sampled frame of a clip - *frame by frame, not tracking* | video |
| **Lookalike Failure Lab** | finds the different people the model confuses and lists real mistakes with *possible* causes (hypotheses, never conclusions) | robustness, innovation |
| **Evaluation Lab** | measures false accepts vs. correct accepts; try thresholds safely in the sandbox | measurement, thresholds |
| **Model & System Settings** | the models (with checksums), the active rules (versioned), system health | audit, configuration |

## 5. The 10-minute live demo (with what to say)

**Before you start** (5 min): start the app (`powershell -ExecutionPolicy Bypass -File scripts\start.ps1`), open
`http://127.0.0.1:8000`. The top bar must say **Models ready · CPU**. Open **Model & System → Model & thresholds** and check
*Matching mode: Face + body*. Have ready, with their permission: **two different volunteers (A and B)**; **three photos of A**
(front-facing, different days or clothes; two for enrolling, one new), **one photo of B** - ideally wearing something *similar* to A's
clothes - and **one photo of A from behind or very small**. (No volunteers? The home page's **example** needs none, and the demo pack in `demo/` has public-domain photos. Never use photos of
people who have not agreed.)

| Min | You do | You say | What the screen shows |
|---|---|---|---|
| 0:00 | **Home page** (Command Center) → press **Run the example** (about 10 s) | "Three things matter here: enroll people, match photos, and prove the system refuses strangers - even strangers dressed like someone it knows. This example does the last one with 13 public-domain photos and no setup." | the three essentials cards, then a progress bar, then the results fill in |
| 1:00 | the **comparison table** and the **two plots** | "Same photos, two matchers. Clothes alone accepted **3 of the 3 strangers in the same orange suit** and missed **all 5** known people who changed clothes. With the face as well: none accepted, all 5 recognised. On the face plot every known person is far right of the line and every stranger far left; on the clothing plot the same-suit strangers score *higher* than the real people." | table: 5 of 5 / 0 of 5, 0 of 3 / 3 of 3; dots either side of the dashed line |
| 2:15 | the **slider** "move the face line" | "Where to put the line is a trade-off we can measure: lower it and strangers get in, raise it and real people are missed. And it says *unvalidated* - these 13 photos are a demonstration, not a benchmark." | live counts change; amber *Unvalidated* badge in the rules strip |
| 3:00 | Identity Gallery → *Enroll identity* → ID `subject-A`, tick the consent box, add A's two photos | "Enrolment is deliberate and needs consent. A fingerprint of the face **and** body is stored - that is biometric data, and the form says so." | result list: "usable face on file" for both |
| 4:00 | Match Studio → tick *Image is already a person crop* → upload A's **new** photo → *Run re-identification* | "A new photo of the same person." | **MATCH**, *Decided by the face*, face bar above the tick, body bar, the two faces side by side |
| 5:00 | Reset → upload **B** (wearing similar clothes to A) | "Now somebody who was never enrolled, dressed like A - the live version of what the example just showed." | **UNKNOWN**; point at the sentence *"Body/clothing similarity alone is NOT accepted when a face is available"* and at the high body bar next to the low face bar |
| 6:00 | Upload the photo of A **from behind / tiny** | "No usable face. The system does **not** pretend: it falls back to clothing and build, which is weak evidence, so it asks a person." | **REVIEW** ("No face was found... clothing and build are not enough for an automatic MATCH") |
| 6:45 | Settings → Model & thresholds | "Every rule is a numbered version with who changed it, when and why; nothing is edited in place." | version history, *Face threshold 0.465* |
| 7:30 | Lookalike Failure Lab (open an existing run) | "This lab goes looking for the people our system confuses. It prints the *realistic* error rate next to the *worst-case* one, and labels every cause as an unproven hypothesis." | pairs of different people; mistake cards: *observed* vs *possible* |
| 9:00 | Evaluation Lab → Threshold sandbox | "Stricter or looser? Move the slider and see the real counts change - it can never change the live system." | live counts, "writes nothing" banner |
| 9:45 | close | say the last paragraph of §1 again | |

**If something goes wrong:** (1) *"Models not ready"* → wait 20 s and refresh, or restart `start.ps1`. (2) *A result is not what you
expected* → **do not hide it**: open the *Evidence* card and explain it; a REVIEW or an UNKNOWN on a poor photo is the system working
correctly. (3) *The face is not found* → use a larger, front-facing photo; say "this is exactly the case the REVIEW path is for".
(4) *Total failure* → show `demo/DEMO_GUIDE.pdf` (screenshots of a real run) and the measured results in `docs/results/`.

## 6. Numbers - what you may quote, and what you must not

**You may quote (each is measured, with its source):**

| Statement | Number | Where it comes from |
|---|---|---|
| Face-model accuracy on the standard LFW test (6,000 face pairs, 10 folds) | **98.9 %** (± 0.35) | `docs/results/face_lfw.json`, `scripts/evaluate_face_lfw.py` |
| Stranger pairs that reach the automatic-MATCH score | about **1 in 100,000** | 4.5 million different-people pairs, same file |
| Same-person pairs that reach it | **93 %** (the rest go to review) | same file |
| End-to-end test, 10 enrolled people, 60 strangers: strangers accepted | clothing-only **48 / 60** → face + body **0 / 60** | `docs/results/face_vs_body_lfw.json`, `scripts/verify_face_vs_body.py` |
| ...same-person queries matched to the right person | clothing-only 8 / 20 → face + body **20 / 20** | same |
| Time for one photo on a 2-core laptop CPU | about **0.5 - 1.2 s** including finding the person (**0.2 - 0.4 s** if the photo is already a tight crop); the face step adds about 0.06 s per person on a small picture and 0.1 - 0.25 s on a 1-megapixel portrait | `docs/PERFORMANCE.md` |
| The built-in example (13 public-domain photos): same-suit strangers accepted | clothes-only **3 of 3** → face + body **0 of 3**; known people recognised 0 of 5 → **5 of 5**; all 13 photos right 4 → **13** | `docs/results/open_set_example.json`, `demo/run_open_set_example.py`, [OPEN_SET_EXAMPLE.md](OPEN_SET_EXAMPLE.md) |
| Automated tests | **427 backend + 157 interface**, all passing | `pytest`, `vitest` |
| Network sizes | body model 2.2 M parameters; face model about 37 MB | `docs/ARCHITECTURE.md` |

**You must NOT say:**

* "It is 99 % accurate" about the whole system. The 98.9 % is the *face stage* on an *easy public benchmark*.
* Any accuracy on the **pedestrian re-identification benchmark (Market-1501)**: it has not been run (it must be supplied under its
  research licence). The Evaluation Lab is built and tested, but shows "Not evaluated" until then.
* That the 48 / 60 → 0 / 60 comparison is a fair test of the clothing model: those were head-and-shoulders photos, outside what the
  clothing model was designed for. Say "it shows what the face adds".
* "Like Face ID", "unspoofable", "bias-free", "GDPR-compliant", "real-time", "production-ready" - none is true.
* That the synthetic-data lab results (cartoon mannequins) are performance. They only prove the lab runs.
* That the home-page example is a benchmark or an error rate. It is **13 portraits** that show the mechanism; say "in this small demonstration". The photos are head-and-shoulders portraits, outside what the body model was built for, and the thresholds are unvalidated.

## 7. Limits - say these before you are asked

1. **Not Face ID.** Phones use infrared depth sensing; this is ordinary 2-D photo matching. A printed photo or a screen can fool it
   (no liveness check).
2. **Look-alikes and twins can still be accepted.** The system reduces that and sends the borderline band to a human, but cannot
   eliminate it. The chance grows with the number of enrolled people.
3. **Hard images:** masks, sunglasses, strong angles, tiny faces, low light, blur. These are reported as "face not usable" or REVIEW.
4. **Accuracy was measured on LFW**, which is easy (frontal, well-lit public figures). Performance across ages, skin tones, cameras and
   lighting has **not** been measured; face recognition is known to vary across groups.
5. **Thresholds are unvalidated** for any specific camera. They are evidence-based defaults, labelled as such.
6. **Pretrained models.** We did not train the neural networks; we integrated, evaluated and wrapped them (see Q22).
7. **Biometric data.** Needs consent, a purpose, retention rules, security and probably a legal assessment before any real deployment.
8. **Prototype scope:** no live cameras, no tracking, no cloud, one user, no login by default (it only listens on the local computer).

## 8. Questions the jury may ask - and honest answers

**Q1. What problem does it solve?** Telling the difference between "this is somebody we know" and "this is somebody who just *looks*
like someone we know". Most systems always return the nearest known person; ours decides whether to believe that person.

**Q2. What does "open-set" mean?** The set of people the camera might see is *open*: it includes people never enrolled. A
"closed-set" system assumes everyone is already known and so always answers with a name. Ours can answer UNKNOWN.

**Q3. Why not simply use a face recogniser?** Faces are often not usable: people seen from behind, far away or blurred, and faces
are only visible at some cameras. So the system uses the face when it can and the body when it must - and it is honest that body-only
evidence is weaker, so it asks a human.

**Q4. Then why keep the body model at all?** The assignment (PS-1) is about re-identification across cameras, where faces are often
unreadable; the body model is the fallback, and it supports (never overrides) the face when both are visible.

**Q5. How accurate is it?** Face stage: 98.9 % on the standard LFW test. Whole system: in a small end-to-end test, 20 of 20
same-person photos matched and 0 of 60 strangers accepted. Not yet measured: the pedestrian benchmark and anything on our own
cameras. We say that on screen ("Unvalidated").

**Q6. What is a "false accept" and why is it the main number?** A stranger wrongly accepted as an enrolled person. In access or
security settings it is the costly mistake. We therefore tune for *few false accepts* and accept that some real matches go to review.

**Q7. How did you choose the thresholds?** The face threshold (0.465) comes from a rule fixed in advance: "automatic MATCH only where
strangers reach that score at most once in 100,000 comparisons", measured on 4.5 million stranger pairs. The model authors' own value
(0.363) let through about 1 in 1,200 - too loose for a search over many people. The body threshold (0.70) is an unvalidated starting
value; the Evaluation Lab can calibrate it on held-out people once a benchmark is supplied.

**Q8. Can it be fooled by a photograph?** Yes - there is no liveness check. Real deployments add depth/infrared sensing or
challenge-response. We list this as a known limit.

**Q9. Twins and look-alikes?** They can still score high. That is what the review band, the margin rule and the Lookalike Failure
Lab are for: *measuring* it rather than assuming it away.

**Q10. Is this like unlocking a phone with Face ID?** No. Same family of idea, very different security level and sensors.

**Q11. What about masks, glasses, beards, ageing?** Masks and sunglasses degrade accuracy; those faces are flagged and sent to review.
Ageing and appearance change were not tested.

**Q12. Is it biased?** We have not measured demographic differences. Face recognition in general is known to perform unevenly across
groups, so no claim of fairness is made, and the system should not be used for decisions that affect people without such testing.

**Q13. What about privacy and the law?** Only enrolled, consenting people are matched; nothing leaves the computer; deleting a person
deletes their photos and fingerprints; query photos expire in 24 h. A face fingerprint is biometric data (GDPR / India's DPDP Act /
Illinois BIPA treat it specially) and a real deployment needs a legal basis and an impact assessment. See `docs/SECURITY_AND_PRIVACY.md`.

**Q14. Where is the data stored? Can I erase it?** In a local database and folder on this computer (`backend/data/`). Deleting a
person in the gallery erases it all; "Reset demo gallery" erases everyone.

**Q15. Does it need the internet?** Only once, to download the model files (each is checksum-verified). Afterwards it runs offline.

**Q16. What hardware does it need? How fast?** An ordinary laptop CPU: about 0.5 - 1.2 s per photo including finding the person (0.2 - 0.4 s for a ready-made crop); the face step adds roughly 0.06 s per person on a small picture and 0.1 - 0.25 s on a 1-megapixel portrait. A GPU is optional and untested here.

**Q17. Could it handle 10,000 people?** Searching is milliseconds, so speed is no problem. Accuracy is: the more people enrolled, the
more chances for a look-alike - false-accept risk grows roughly with the gallery size, which is why thresholds should be re-checked
as the gallery grows.

**Q18. Is it real-time video?** No. Video Explorer samples frames (e.g. one per second) and judges each frame on its own. It does
not track people. The screen says so.

**Q19. Why these models?** OSNet-AIN is a small, purpose-built re-identification network (2.2 M parameters). YuNet (detector) and
SFace (recogniser) are small, CPU-friendly and openly licensed (MIT / Apache-2.0) with hash-verifiable downloads. Larger models would
be more accurate but slower and, for some, restrictively licensed.

**Q20. What did *you* build, and what did you reuse?** Reused: the pretrained neural networks and standard libraries. Built: the
whole application - the decision rules, face + body fusion, quality checks, the evaluation protocol (leak-free splits, calibration,
ROC/FAR metrics), the Lookalike Failure Lab, video processing, the web interface, safety checks, exports, and 523 automated tests.

**Q21. UNKNOWN versus REVIEW?** UNKNOWN = the evidence says nobody enrolled matches. REVIEW = the evidence is *not good enough to say*
(poor photo, no usable face, borderline score), so a person decides.

**Q22. Did you train a model?** No. Fine-tuning code exists and is tested, but no model was trained, so we claim no improvement from
training. The measured gain comes from adding the face evidence and the decision rules.

**Q23. How do you know it works as described?** Automated tests check each rule (e.g. "same clothes, different face → UNKNOWN"), the
face stage was measured on a public benchmark, and an end-to-end script reproduces the comparison in this guide. All reproducible.

**Q24. Why did the first version accept a stranger?** Because a clothing-based model confuses people in similar clothes - the very
low-variance problem the assignment describes. We reproduced it, measured it (48 of 60 strangers accepted), and fixed it.

**Q25. What if the face model files are missing?** The system keeps working on the body only, and says so on every result and on the
Settings screen. Nothing fails silently.

**Q26. Can decisions be audited?** Yes: each decision records the rule version, scores and reason; rule changes are versioned with who,
when and why; results export as JSON / CSV.

**Q27. What are the biggest risks?** Misuse (matching people without consent), over-trust of the scores, spoofing, and unmeasured bias.
The design counters the first two with consent gates, explicit REVIEW and honest labels; the last two are stated limits.

**Q28. What would you do next?** (1) Run the pedestrian benchmark (Market-1501) and publish the report. (2) Calibrate both thresholds on
the real camera data. (3) Add liveness/anti-spoofing. (4) Measure accuracy by lighting, age and demographic group. (5) Train and
*evaluate* a fine-tuned body model on the look-alike hard cases.

**Q29. If you only had a minute to convince us it is trustworthy?** "It says UNKNOWN to people it has not seen, it asks a human when
it is unsure, it shows its scores and its reasons, and every claim we make has a script that reproduces it."

**Q30. Is the example on the home page a benchmark?** No, and the page says so. It is 13 public-domain photographs with known right
answers - five known people in new clothes, two without a usable face, three strangers, and three strangers in the *same* suit as an
enrolled person - run through the real decision code in a private, temporary gallery (nothing saved, your gallery untouched). It
shows *why* clothing-only matching fails and the face does not; it gives no error rate for any real camera.

**Q31. Why does the clothes-only column miss the known people?** Because they changed clothes: the body fingerprint mostly encodes
clothing colour and build, so the same person in a new jacket scores low (0.50-0.62 here, below the 0.70 line) while a *different*
person in the same suit scores high (0.78-0.81). That is exactly the low inter-class variance the assignment describes.

**Q32. Something you do not know.** Say: *"I don't know. Here is how I would find out"* - and name the measurement. This is always the
right answer.

## 9. Glossary (plain words)

| Term | Plain meaning |
|---|---|
| **Re-identification** | recognising that a person seen now is the same person seen before |
| **Open-set** | the person might be someone we have never seen |
| **Embedding / fingerprint** | a short list of numbers a neural network makes from a picture; similar pictures give similar lists |
| **Cosine similarity** | how alike two fingerprints are, from -1 to 1 (not a percentage) |
| **Threshold** | the score a match must reach; higher = stricter |
| **Margin** | how far the best candidate is ahead of the runner-up; a small margin means "could be either" |
| **False accept (FAR)** | a stranger wrongly accepted; FAR = such mistakes ÷ all strangers |
| **True accept / recall** | an enrolled person correctly accepted |
| **Calibration** | choosing the threshold on data kept separate from the data used to report results |
| **Policy** | the numbered, versioned set of rules that turns scores into MATCH / UNKNOWN / REVIEW |
| **LFW** | a standard public set of face photo pairs for testing face matchers |
| **Liveness** | a check that a real person (not a photo) is in front of the camera |
| **CPU / GPU** | ordinary processor / graphics processor; this runs on a CPU |

## 10. For a technical juror: where to look

| Question | File |
|---|---|
| "Show me the decision rule" | `backend/app/cv/open_set/multicue.py` (about 140 lines) and its tests `backend/tests/test_face_matching.py` |
| "How is a face judged usable?" | `backend/app/cv/face/engine.py` |
| "How do you avoid test leakage?" | `backend/app/evaluation/protocol.py` + `docs/EVALUATION.md` |
| "Where do the numbers on screen come from?" | `backend/app/services/reid_service.py` (every number is computed there, not in the browser) |
| "How is it secured?" | `docs/SECURITY_AND_PRIVACY.md` |
| "Where is the full explanation?" | `docs/FACE_AND_BODY_MATCHING.md`, `docs/CODE_WALKTHROUGH.md` |
| "How does the example on the home page work?" | `backend/app/services/demo_service.py` (the verdict rules and the private gallery), `demo/samples/demo_manifest.json` (the photos and right answers), `frontend/src/features/demo/`, and [OPEN_SET_EXAMPLE.md](OPEN_SET_EXAMPLE.md) |

## 11. After the session

*Identity Gallery → Reset demo gallery* (type the phrase) removes the volunteers. Do not leave real people's photos in the gallery.

---

## One-page cheat sheet (print this)

* **Problem:** clothing-only matching accepts strangers who dress alike.
* **Idea:** face first, body second, human when unsure. Three answers: **MATCH / UNKNOWN / REVIEW**.
* **Proof:** face stage 98.9 % on LFW; strangers accepted 48/60 → 0/60 in our end-to-end test; same-person 20/20.
* **Home-page example (13 photos, not a benchmark):** strangers in the *same suit* accepted 3/3 by clothes alone, 0/3 with the face; known people recognised 0/5 → 5/5.
* **Threshold 0.465:** chosen by a rule (≤ 1 stranger in 100,000) on 4.5 M pairs - not tuned on the demo.
* **Honest limits:** not Face ID; no liveness; LFW is easy; bias not measured; pedestrian benchmark not run; thresholds unvalidated.
* **Privacy:** consent, local only, delete = erase, query photos expire in 24 h; face = biometric data.
* **If asked something unknown:** "I don't know - here is how I would measure it."
