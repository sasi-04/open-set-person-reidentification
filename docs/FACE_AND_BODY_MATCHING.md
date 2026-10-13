# Face + body matching

*Why it exists, how it decides, what was measured, and what it cannot do.*

> **In one sentence.** The first version of this system recognised people by their whole-body appearance, which mostly means
> clothing colour and build, so a stranger in similar clothes could be accepted. This version also compares **faces**: when a
> usable face is visible, the face decides, and similar clothing can no longer turn a failed face into a MATCH.

---

## 1. The problem this solves

PS-1 is about *open-set* identification under *low inter-class variance*: many different people look alike, and the system
must say **UNKNOWN** to a person it has never seen instead of picking the nearest enrolled name.

A whole-body fingerprint (OSNet) is built for pedestrians seen by different cameras. It is good at "same person, different
camera", but it leans heavily on **colour and clothing**. Two different people in the same uniform get similar fingerprints.
That is exactly the failure that was reported: *a different person was accepted because the clothes looked alike.*

A face carries information the body does not (the shape and arrangement of the face itself). So the system now measures both,
and gives the face the deciding vote whenever it can be trusted.

## 2. What the system looks at

| Evidence | What it captures | How it is measured | Role |
|---|---|---|---|
| **Face** | The face itself: eyes, nose, mouth geometry, jaw, face texture | YuNet finds the face; SFace turns it into **128 numbers**; similarity = cosine of two such vectors | **Decides** when a usable face is visible |
| **Body** | Clothing colour, pattern, build, posture | OSNet-AIN turns the person crop into **512 numbers** | Supports a face decision; **decides** only when there is no usable face (and then asks for review by default) |
| **Colour cues** | Hair colour, skin tone, upper and lower clothing colour | Plain image statistics (no neural network) on the face region and the torso/legs | **Display only** - lets a human see "same hair? same shirt?"; never changes a decision |

Colour cues are deliberately kept out of the decision. Lighting, white balance, shadows, make-up and a change of clothes all move
colours, and no data was available to calibrate them, so using them to accept or reject someone would be guesswork dressed up as
measurement. They are shown because they help a person judge a REVIEW case.

## 3. The decision rule (exactly what the code does)

Source: `backend/app/cv/open_set/multicue.py`. It is a pure function - scores in, decision out - covered by unit tests.

**A face is "usable"** when it is at least 40 px wide, the detector is at least 80 % sure, it is not turned away more than 45 % of
its width, and it is sharp enough. Otherwise the reason is reported (`face_small`, `face_blurry`, `face_turned`, `face_low_confidence`).

**Situation A - a usable face and at least one enrolled person with a face on file:**

1. best face similarity **≥ 0.465** → **MATCH** (if a minimum margin over the runner-up is configured and fails → REVIEW)
2. between **0.365 and 0.465** (the review band) → **REVIEW** ("too close to call automatically")
3. below that → **UNKNOWN** - and the explanation says so even when the clothes matched:
   *"Body/clothing similarity alone is NOT accepted when a face is available."*
4. special case: somebody enrolled **without** a face on file cannot be ruled out by a face; if their *body* matches strongly the
   result is **REVIEW**, not UNKNOWN.

**Situation B - no usable face** (back view, far away, blurred, turned) **or nobody enrolled has a face:**

* the original body-only rules apply (poor quality → REVIEW, below the body threshold → UNKNOWN), and
* a body pass is **not** accepted automatically: it becomes **REVIEW** ("clothing and build alone are not enough"), unless the
  operator sets *No usable face: accepted as a MATCH*, which restores the original behaviour.

So the three outcomes keep their meaning: **MATCH** = supported by evidence we trust; **UNKNOWN** = no enrolled person is supported;
**REVIEW** = a person should look.

## 4. Where 0.465 comes from (not a guess, not tuned on the demo)

The face model's authors publish 0.363 as a general-purpose cosine threshold. For this application that is too loose: a query is
compared with **every** enrolled person and the best score wins, so the chance of a stranger reaching the line multiplies with the
size of the gallery.

The threshold was therefore chosen by a rule fixed before looking at any result:

> *Automatic MATCH only where, among pairs of different people, a score that high occurs at most once in 100,000 comparisons.*

Measured on **4,498,500 pairs of different people** from the LFW face set (3,000 people compared with each other;
`scripts/evaluate_face_lfw.py`, results in `docs/results/face_lfw.json`):

| Face score at least | Stranger pairs reaching it | Same-person pairs (LFW's 3,000) accepted |
|---|---|---|
| 0.363 (model card) | 3,648 of 4.5 M (**0.081 %**, about 1 in 1,230) | 97.7 % |
| 0.400 | 835 (0.019 %) | 96.8 % |
| **0.465 (default)** | **about 1 in 100,000** (≤ 0.001 %) | **93.4 %** |
| 0.500 | 18 | 90.5 % |

The same-person pairs that fall between 0.365 and 0.465 are not lost - they go to a person for review.

**What this means for a gallery of N people with about R photos each:** the chance that *one stranger query* is wrongly accepted is
roughly N × R × 0.00001. For 100 people with 3 photos each that is about **0.3 %** - small, not zero, and it grows with the
gallery. Add a minimum margin (Settings → Model & thresholds) to trade a little recall for fewer ambiguous accepts.

Honest limit: the score distribution of *your* cameras, lighting and population will differ from LFW. The default is evidence-based
but **unvalidated for your data**; the policy status says so on every screen until someone calibrates it.

## 5. What was measured

### 5.1 The face stage alone - standard LFW verification protocol

6,000 pairs, 10 folds, threshold chosen on 9 folds and tested on the 10th:

* **accuracy 98.93 % ± 0.35 %** (the OpenCV model card quotes 99.40 % under its own protocol)
* a face was found in **all 7,701** pictures
* speed on this laptop CPU: about 57 ms per picture for detection + fingerprint

Reproduce: `python scripts/evaluate_face_lfw.py --folder <folder with pairs.txt and lfw/>`.

### 5.2 The whole system - does the face stop strangers being accepted?

`scripts/verify_face_vs_body.py` enrols 10 people (2 photos each) through the normal API, then shows the system 20 new photos of
those people and 60 photos of 60 other people, once under the **body-only** policy and once under **face + body**
(`docs/results/face_vs_body_lfw.json`):

| | Body only | **Face + body** |
|---|---|---|
| Same-person queries matched to the right person | 8 of 20 | **20 of 20** |
| ... matched to the **wrong** person | 9 | **0** |
| Strangers wrongly **accepted** | **48 of 60** | **0 of 60** |
| Strangers sent to a person / rejected | 0 / 12 | 4 / 56 |

Read this carefully: the LFW photos are head-and-shoulders news pictures, which the body model was **not designed for** (it expects
full-body pedestrian crops), so the body-only column is its *worst case*, not a fair benchmark of the body model. The table shows
what the face adds, not how good the body model is on its home ground (that needs Market-1501, which has not been run). The
threshold used was fixed beforehand from §4, not tuned on these 60 strangers - an earlier run with the model-card threshold 0.363
had accepted 3 of the 60, which is what motivated looking at the stranger-score tail properly.

## 6. What it cannot do (say this before you are asked)

* **It is not a phone's Face ID.** Face ID uses an infrared depth sensor and a secure enclave; this is 2-D face matching from
  photographs. A printed photo or a screen can fool any 2-D matcher (no liveness check here).
* **Look-alikes can still be accepted**: twins, close relatives, and people who happen to resemble each other. That is why the
  default asks a person to review the borderline band.
* Accuracy drops with **masks, sunglasses, strong angles, low light, tiny faces and motion blur** - those faces are reported as
  "not usable" or land in REVIEW, they are not silently trusted.
* LFW is **easy** (frontal, well-lit public figures, mostly adults). It says nothing about phone-camera selfies in poor light,
  CCTV distance, children, or demographic differences in accuracy - which are known to exist in face recognition generally and
  were **not measured** here.
* The face models were trained by their authors on public face datasets whose terms this project has not audited
  (see `THIRD_PARTY_NOTICES.md`). Research prototype only.
* The Evaluation Lab and Lookalike Failure Lab still measure the **body** model (their datasets are body crops without readable
  faces). They are labelled that way on screen.

## 7. Privacy: a face fingerprint is biometric data

Adding faces changes the privacy picture, and the earlier statement "this system does not use faces" is no longer true.

* Only **enrolled, consenting people** are matched. Enrolment requires an explicit confirmation, which now states that a fingerprint of
  the face and body is stored.
* What is stored for a reference photo: the cropped JPEG, a 512-number body fingerprint, and a 128-number face fingerprint with the
  face's position and the colour cues. Deleting an identity deletes all of it (tested). Query pictures are kept for 24 hours at most.
* Nothing leaves the machine; no cloud service, no scraping, no camera connection.
* Laws such as the GDPR (special-category biometric data), India's DPDP Act and Illinois' BIPA regulate exactly this. A real
  deployment needs a lawful basis, a purpose limit, retention rules and probably a data-protection impact assessment. This
  prototype is for authorised test images only (`docs/SECURITY_AND_PRIVACY.md`).

## 8. Where things are in the code

| What | File |
|---|---|
| Face detector + recogniser, "is this face usable?" | `backend/app/cv/face/engine.py` |
| Hair / skin / clothing colour cues | `backend/app/cv/face/appearance.py` |
| The decision rules | `backend/app/cv/open_set/multicue.py` (+ `policy.py` for the settings) |
| Reference-photo analysis, query face analysis, upgrading old galleries | `backend/app/services/face_service.py` |
| One person's decision (shared by photos and video) | `backend/app/services/matching.py` |
| Evidence panel on screen | `frontend/src/features/reid/EvidencePanel.tsx` |
| Tests | `backend/tests/test_face_matching.py`, `frontend/src/pages/face.test.tsx` |

## 9. Switching it on and off

* `REID_FACE_MATCHING=false` in `.env` → the original body-only system; the face models are never loaded.
* Settings → *Model & thresholds* → **Matching mode** → *Body only* → the same, per policy version (audited, reversible).
* Without the face model files the system keeps working on the body and **says so** on every result and on the Settings screen.
* Existing galleries upgrade in place: at start-up the stored reference photos are analysed once (`Analyse faces` repeats it).
