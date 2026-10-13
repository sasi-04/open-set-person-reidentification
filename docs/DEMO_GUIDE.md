# Presenting OpenID Vision - a 10-minute guide

> **Start with [JURY_GUIDE.md](JURY_GUIDE.md)**: the 60-second story, a click-by-click demo with what to say, the numbers you may and may not quote, and 32 likely questions with honest answers. This page is the shorter, technical running order.

*Know when to match. Know when to reject.* A suggested running order for showing the system to a technical audience, followed by the questions they are most likely to ask, with honest answers.
The golden rule: **only say what the screens and reports can show.** The strongest part of this project is that it does not over-claim.

## Before the session (5 minutes)

1. `powershell -ExecutionPolicy Bypass -File scripts\start.ps1` and open **http://127.0.0.1:8000**. There is no sign-in: access keys are off by default, and you act as an administrator.
2. The top bar should say **"Models ready"** and **CPU**. If not, see README §22.
3. Start from a known state: **Model & System → Access, appearance & privacy → Run cleanup now**; **Identity Gallery → Reset demo gallery** if old test data is present.
4. For the video part, prepare one short *authorised* clip (a few seconds is plenty; the default sampling takes a frame per second). For the lab, have a dataset installed (Market-1501 if you have it; otherwise `python scripts\make_smoke_dataset.py` and say plainly that its numbers are not accuracy).
5. Prepare *authorised* test photos of **two volunteers, A and B**: two clear front-facing photos of A (to enrol), a third new photo of A, one photo of B - ideally in clothes *similar* to A's - and one photo of A from behind or very small. The stranger in similar clothes is your best demonstration: the old clothing-only matcher accepted such people, the face-first matcher does not. Face matching must be on (**Model & System → Model & thresholds → Matching mode: Face + body**).
6. **No volunteers needed for the first minutes:** the home page's example runs by itself (about 10 s). `python demo\run_open_set_example.py` prints the same table in the terminal and saves `docs/results/open_set_example.json` ([what it shows and does not prove](OPEN_SET_EXAMPLE.md)).
7. If you have run the benchmark, have the HTML report open in another tab (**Evaluation Lab → run → HTML**). If you have **not**, say so up front; do not show the synthetic-set numbers as accuracy.

## The running order

| Min | Screen | What to show | The point to make |
|---|---|---|---|
| 0-1 | slide / README §1 | the false-accept problem: a stranger in a similar uniform | *"Retrieval always returns a nearest neighbour. The question is whether to believe it."* |
| 1-2.5 | **Command Center (home page)** | the three essentials (enroll · match · open-set analysis, ticking from real data), then press **Run the example**: the comparison table (clothes-only accepts 3 of 3 strangers in the same suit, face + body 0 of 3), the two score plots and the face-line slider; scroll down for the live counts, "Not evaluated" and the policy badge **Unvalidated** | *"Same photos, two matchers. Every number is computed by the server, and the page says it is a 13-photo demonstration, not a benchmark."* |
| 2-3 | **Identity Gallery** | enroll a volunteer: pseudonymous ID, authorisation tick, several images; duplicate-person warning | *"Enrollment is a deliberate, audited act. Photos with several people are refused."* |
| 3-5 | **Match Studio** | detect (boxes show *detector* confidence), run: enrolled person → **MATCH**, *decided by the face*, with the **Evidence** card (face bar vs its threshold, body bar, the two faces side by side, colour cues); the stranger in similar clothes → **UNKNOWN** ("clothing alone is NOT accepted when a face is available"); a back view or blurry crop → **REVIEW**; download the decision record | *"Three decisions. The explanation is built from the real scores. The nearest neighbour is never accepted automatically - and 'unknown' is a verdict on the evidence, not a label for a person."* |
| 5-6 | **Video Explorer** | upload the clip, show real progress, then the timeline (M / U / R), the frame with its boxes, and the per-frame timings | *"Same detector, same model, same rules - per sampled frame. It is frame-by-frame, not tracking, and the screen says so."* |
| 6-8.5 | **Lookalike Failure Lab** | run (or open) an experiment: the most alike pairs of *different* people as photo pairs; the challenge set with **both** stranger rates side by side; open a mistake card: *observed* numbers vs *possible causes - hypotheses, not proven*; the baseline-vs-improved tab (or its honest "no comparison, because...") | *"This is where the model is stressed. The hard-pair rate is high by construction, so we print the realistic all-pairs rate next to it - and we never present a guess as a cause."* |
| 8.5-9.5 | **Evaluation Lab** → **Threshold sandbox** | move the threshold and watch real counts and the decisions that change; point out there is no apply button and the test-split warning; then **Model & System** to show where a calibrated threshold is actually applied | *"The threshold is chosen on people the test never sees. The sandbox lets you understand the trade-off without ever changing production."* |
| 9.5-10 | code | open `decision_engine.py` (60 lines) and the test file next to it | *"The core logic is a pure function with tests that read like the requirements."* |

## What you can truthfully say

- *"This is a working end-to-end system: real detector, real pretrained ReID network, real decision engine, a real evaluation pipeline."*
- *"The decision rule, calibration and evaluation protocol are implemented to keep test data out of every choice - and the tests prove it."*
- *"Speed on a 2-core laptop CPU is roughly 0.5 s per query when idle and up to about 1.2 s when the machine is busy; Video Explorer processed 0.7-3.4 s per sampled frame in our checks (idle versus busy machine). Interactive, not real-time video."* (measured; PERFORMANCE.md) - close other programs before demonstrating.
- *"Video Explorer is frame-by-frame re-identification of a prerecorded clip. It is not a tracker."* The same sentence is on the screen.
- *"The look-alike lab found these pairs and listed these mistakes; the possible causes are hypotheses we have not tested."*
- If you ran Market-1501: quote **only** numbers from your generated report, with the seeds and the calibration sample size.

## What not to say

- Any accuracy, FAR or recall figure if the benchmark has not been run on the real dataset. (The system's *behaviour* on the synthetic set is fine to describe - "it correctly reported that the target was unreachable" - but not as performance.)
- "Real-time", "production-ready", "privacy-compliant", "fair" or "secure against attackers". None of these have been shown.
- That a threshold "guarantees" a false-accept rate. It *measures* one on a sample, with an uncertainty bound.
- That fine-tuning improved anything. The pipeline and the comparison screen exist; no checkpoint has been trained or evaluated, so the comparison tab honestly says there is none.
- That Video Explorer tracks people, follows them through occlusion, or runs in real time.
- That a "possible cause" is the reason a mistake happened, or that the challenge-set false-accept rate is the system's false-accept rate.

## Questions you may get

**How do you handle strangers who look like an enrolled person?** We cannot make it impossible; we make it *measurable and controllable*: a threshold plus an optional top-1/top-2 margin, chosen on held-out people for a stated FAR/recall target,
and a same-clothing subset that reports the FAR specifically on look-alikes. Ambiguous cases go to human review instead of being auto-accepted.

**Why not just raise the threshold?** Because recall falls. The ROC shows the trade-off; the calibration screen shows the exact recall you give up for each FAR.

**Is the test set contaminated by tuning?** No. Split by *person* into development / calibration / test; thresholds, margins, the confidence model and even the "selected variant" use only calibration people; the calibration job never opens a test image
(there is a test for that); a fine-tuned checkpoint that saw any test person is refused automatically.

**Which dataset, and is it public?** Market-1501 (public, research-licensed) is the intended benchmark; the loader, validator and protocol are ready. [State plainly whether you have run it.] A curated same-clothing subset is derived with a colour proxy, or from a manual annotation file.

**Why OSNet and not something bigger / a transformer?** PS-1 asks for one compact backbone: OSNet-AIN has 2.2 M parameters, is built for ReID and is MIT-licensed. The backbone is behind a registry so another can be added.

**Where does "confidence" come from?** Two separate things: the *similarity* (a cosine, not a probability) and an optional *calibrated confidence*, a logistic model fitted on calibration people from similarity and margin. If no calibration was applied the interface says "Not available".

**What happens if the gallery grows to 10 000 people?** Search is one matrix product - about 12 ms at 10 000 people (measured); the practical limit becomes accuracy, not speed. There is no per-person classifier, so adding/removing people needs no retraining.

**Why not just a face recogniser?** Faces are often not usable (back views, distance, blur), so the system uses the face when it can be trusted and falls back to the body - asking a person instead of auto-matching on clothing. It is honest that this is 2-D photo matching, not a phone's Face ID.

**How accurate is the face part?** 98.9 % (± 0.35) on the standard LFW test, 6,000 pairs; at the default threshold about 1 stranger pair in 100,000 reaches an automatic MATCH while 93 % of same-person pairs do. Whole-system check (10 enrolled, 60 strangers): clothing-only accepted 48 strangers, face + body accepted 0 (`docs/results/`). LFW is easy and these photos are outside the body model's design - say so.

**What about privacy?** Authorised images only; pseudonymous IDs; no raw uploads stored; query crops expire after 24 h; scores-only history with its own retention; audit trail; face matching is limited to enrolled, consenting people and is switchable (see SECURITY_AND_PRIVACY.md section 4a). SECURITY_AND_PRIVACY.md lists the gaps too (no login by default, no TLS).

**Why is there no login?** On a single-user demo machine the server listens on `127.0.0.1` only, so only that computer can reach it; a login would only slow the demo. Role-based access keys (viewer / operator / admin) are implemented and tested and switch on with one setting (`REID_AUTH_REQUIRED=true`). Without them everyone is an admin, which is why the server must not be exposed on a network as it is.

**Can it run on a GPU / on video / live cameras?** GPU selection is implemented but untested here. Video and live cameras are **not** implemented.

**How was the interface verified?** 130 UI tests, plus a scripted real-browser audit of all 7 screens at 360, 390, 768, 1024 and 1440 px (no horizontal overflow), plus a computed colour-contrast check in both themes.

**What would you do next?** Run the benchmark with three seeds, publish the report, train and *evaluate* a triplet checkpoint on the development people, then annotate a genuine same-clothing subset.

## Resetting after the demo

**Identity Gallery → Reset demo gallery** (type the phrase), **Settings → Run cleanup now**. To wipe everything including history and policy versions: stop the server and delete `backend/data/`.
