# The built-in open-set example

*The home page of the website has a button, **Run the example**. This page explains what it does, what its numbers mean, and - just as
important - what they do **not** prove.*

---

## 1. Why it exists

The project is about one hard situation: **the person in the new photo is a stranger, but looks like someone already enrolled** (same
uniform, similar build). A system that only asks "who is the nearest enrolled person?" will name the wrong person. A good system must
also be able to say **"nobody I know"**. That is *open-set* recognition, and the dressed-alike stranger is the *low inter-class variance*
problem in the assignment title.

Nobody should have to take that on trust or to prepare their own photos to see it. So the home page ships a small, ready-made test:
public-domain photographs whose right answers are known, run through the **same decision code the real screens use**, shown side by side
with what a clothes-only matcher would have done.

## 2. What you see on the home page

Top to bottom, so an interviewer sees the point without clicking around:

| Part | What it is |
|---|---|
| **The essentials in three steps** | 1 *Enroll people* · 2 *Match photos* · 3 *See the open-set analysis*. Each card shows a live status, ticks itself from real data and has one button. The three possible answers - MATCH, UNKNOWN, REVIEW - are explained underneath. |
| **Open-set example** | One button: **Run the example** (about 10 seconds on a laptop CPU). It fills in everything below. |
| ↳ What the example shows | A plain-language conclusion written *from the counts* (never typed in by hand). |
| ↳ Comparison table | Five questions, two columns: **Face + body** (this system) against **Clothes only** (a weaker matcher). Every cell is "n of m" with a tick or a cross. |
| ↳ Two plots | **Face similarity** and **Clothing similarity**: one dot per photo, a dashed line at the threshold. On the face plot the known people sit far right and every stranger far left; on the clothing plot the strangers in the same clothes sit on the *wrong* side of the known people. |
| ↳ "Try it: move the face line" | A slider. Lower the face line and watch strangers start to be accepted; raise it and known people start to be missed. It only *counts* the scores the server measured. |
| ↳ Who the system knows | The three example people and what the face analysis found in each of their photos ("Face on file" / "No face found"). |
| ↳ The 13 photos | Each photo, the right answer, and for **both** matchers: the answer, whether it was right, the similarity score drawn against the line it needed, and *why*. |
| **Live system status** | The previous Command Center, moved down: models, device, enrolled people, queries, latest benchmark, threshold and policy, recent decisions. |

## 3. What the example contains

* **Three enrolled "example people"** (their photos are public-domain portraits; the interface calls them *Example person 1 / 2 / 3* so no
  name is on screen - credits are in [demo/samples/SOURCES.md](../demo/samples/SOURCES.md)):
  two have a clear face on file; the third is a street photo with the head blurred, so **no face on file**.
* **13 photos the system has never seen**, in four groups:

| Group | Photos | The right answer |
|---|---|---|
| Known people, seen again (different clothes, years apart) | 5 | **MATCH** with the right person |
| Known person, but no usable face (blurred / out of focus) | 2 | **REVIEW** - clothes alone are weak evidence, so ask a person |
| Strangers, never enrolled | 3 | **UNKNOWN** |
| **Strangers in the same orange flight suit as an enrolled person** | 3 | **UNKNOWN** |

The last group is the heart of it: three different people, none enrolled, photographed in the same kind of suit as the enrolled ones.

## 4. What it measured (live run, real models)

Run on 2026-10-13 with `python demo\run_open_set_example.py` (saved in [docs/results/open_set_example.json](results/open_set_example.json);
rules in force: face line 0.465 with a 0.10 review band, clothes line 0.70, policy *unvalidated*).

| Question | Face + body (this system) | Clothes only |
|---|---|---|
| Known people recognised | **5 of 5** | 0 of 5 |
| Strangers refused | **6 of 6** | 3 of 6 |
| ... of those, strangers **in the same clothes** refused | **3 of 3** | **0 of 3** |
| Known people with no usable face sent to a person | **2 of 2** | 1 of 2 (the other was **accepted on clothes alone**) |
| All 13 photos decided exactly right | **13 of 13** | 4 of 13 |

The scores explain why:

* **Face:** every known person scored at least **0.57**; every stranger with a visible face scored at most **0.26** (the three in the same suit:
  0.14-0.19). The face line (0.465) sits in that gap.
* **Clothes:** the three strangers in the same suit scored **0.78-0.81** against an enrolled person - *higher* than the known people photographed
  in new clothes (**0.50-0.62**). With clothes alone the strangers are accepted and the real people are missed, in the same breath.

In one sentence for a jury: **in this small test, clothing pointed at the wrong people and the face did not.**

## 5. How the two columns are produced

Both columns come from the **same photo and the same enrolled gallery**. The server computes the body fingerprint and the face once, then
decides twice with the real decision function (`decide_person`, the one Match Studio uses):

1. **Face + body** - the active policy. A usable face decides; clothing can support it but can never rescue a failed face; with no usable
   face the body decides and a pass is sent to REVIEW. ([Exact rule](FACE_AND_BODY_MATCHING.md).)
2. **Clothes only** - the same policy with the face stage switched off, i.e. what the project's first version did.

"Right" is defined in one place (`verdict()` in `backend/app/services/demo_service.py`): a known person must be named correctly; a stranger
must not be accepted; a known person with no usable face must go to a human. Anything else is shown in colour *and* words (never colour alone):
*Stranger accepted*, *Wrong person named*, *Known person missed*, *Accepted on clothes alone*.

## 6. Safe by design

* The example people live in a **private, temporary gallery held in memory**. Your real gallery, decision history, audit trail and stored
  images are never read or written ([tests prove it](../backend/tests/test_demo.py): row counts before and after are identical).
* **Nothing is saved** - not the photos, not the answers. Leaving the page keeps the results for your visit only.
* Only the files named in `demo/samples/demo_manifest.json` can be served (a whitelist; `..` and absolute paths are refused).
* It never changes the live policy; it reads the active one. If the face models are not loaded the example says so and switches itself off - the rest of the application is unaffected.
* Anyone who may view the application (the *viewer* role) can run it, because it changes nothing.

## 7. What it does NOT prove (say this out loud)

* **Thirteen photos is a demonstration, not a benchmark.** It shows the mechanism and that the code does what the documents say. It gives no
  error rate for any real deployment. The pedestrian benchmark (Market-1501) has **not** been run.
* **These are head-and-shoulder portraits, not full-body camera frames.** The body model was built for the latter. The comparison is fair
  as an illustration of *what clothing similarity does to open-set decisions*, but the clothes-only numbers here are not "the accuracy of
  re-identification".
* **The photos are professional portraits** (good light, frontal faces). Faces in a hallway camera are smaller, blurrier and turned; more
  of them will fall into the "no usable face" path, which asks a person. Face accuracy has been measured only on LFW and on small
  end-to-end tests ([FACE_AND_BODY_MATCHING.md](FACE_AND_BODY_MATCHING.md)).
* **Thresholds are unvalidated starting values** for your cameras. The slider shows the *shape* of the trade-off, not the right setting.
* **The slider counts only photos with a usable face** and ignores the review band and clothes-based checks; it is a teaching aid.
* **Face data is biometric data.** The example uses public-domain photographs; for real people use only authorised, consenting
  individuals ([SECURITY_AND_PRIVACY.md](SECURITY_AND_PRIVACY.md) §4a).

## 8. Running it and changing it

| Want to... | Do this |
|---|---|
| See it | Open the home page and press **Run the example**. |
| Run it without a browser | `python demo\run_open_set_example.py` (add `--base-url http://127.0.0.1:8765` for another server). Exit code 0 = face + body was right on every photo. |
| Use your own photos | Edit [demo/samples/demo_manifest.json](../demo/samples/demo_manifest.json): list each person's enrolment photos, then each test photo with its group and the right answer (`match` + person, `unknown`, or `review` + person). Use only photos you are allowed to use. The page picks the change up on reload. |
| Re-download the public-domain portraits | `python demo\prepare_faces.py` (checks every licence; refuses anything that is not public domain / CC0), then `python demo\write_sources.py`. |

**API** (all read-only for your data): `GET /api/demo` (people, photos, rules), `POST /api/demo/prepare` (build the private gallery),
`POST /api/demo/cases/{id}` (analyse one photo), `DELETE /api/demo/sandbox` (forget it), `GET /api/demo/files/{path}` (a manifest photo).

**Tests:** 34 backend tests (`backend/tests/test_demo.py`: description, manifest errors, analysis, the stranger-in-the-same-clothes case,
"never touches the real data", file whitelist, the verdict table) and 27 interface tests (counting rules, the comparison table, the plots,
the slider, errors, "unavailable", keeping results while you visit another screen, the link from the How it works tour).
