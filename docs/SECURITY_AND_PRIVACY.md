# Security and privacy

This system handles images of people. It is a **research / demonstration prototype** with sensible defaults - it is **not** certified, audited, or approved for production, surveillance or identity verification, and
makes no claim of privacy-law compliance or demographic fairness.

## 1. Intended use and boundaries

- **Authorised, controlled test images only.** Enrolling a person needs an explicit "this person is authorised" confirmation (recorded with the entry), and identities are **pseudonymous reference IDs** (a pattern-checked label like `subject-017`) - never names or ID numbers.
- **Never**: scrape photos, connect to public or third-party cameras, identify real-world individuals from public images, or track people across unrelated places or sessions.
- **Face matching is part of the system (since 2026-10-13).** It compares a query face only with the faces of **enrolled, consenting** people in this local gallery - it never searches the public, never contacts a service, and never names a stranger (an unmatched face is just "UNKNOWN"). This changes the privacy picture: a face fingerprint is **biometric data**; see §4a. It can be switched off completely with `REID_FACE_MATCHING=false` (body-only system, face models never loaded).
- A rejected query is **"no supported match"** - a statement about the evidence, never about the person. Rejected people are not auto-enrolled, grouped as one "unknown person", or flagged as suspicious.
- The application makes no live-camera or video claim: only still images are processed.

## 2. Trust boundary and access control

| Role | Can |
|---|---|
| **viewer** | run queries, read gallery/history/evaluation results |
| **operator** | + enroll, add images, delete identities, rebuild embeddings |
| **admin** | + change decision thresholds, start/cancel evaluations and calibrations, reset the demo gallery, run cleanup, read the audit trail |

- **Access keys are OFF by default** (`REID_AUTH_REQUIRED=false`): nobody types a key, the interface opens straight into the app, and every caller acts as **admin**. This is deliberate for a single-user demo, and it is made safe only by *where the server listens*: `scripts/start.ps1` binds to `127.0.0.1`, so only programs on the same computer can reach it. It is logged as a warning at every start-up. **Do not** start the server on another address (`--host 0.0.0.0`) with keys off - anyone on the network could then enrol people, delete them or change the thresholds.
- **Switching keys on** (`REID_AUTH_REQUIRED=true` in `.env`, then restart) gives the three roles in the table above. Three shared secret keys live in `.env` (git-ignored; `scripts/init_env.py` fills in random ones) and are sent in the `X-API-Key` header. Keys are compared in constant time (`secrets.compare_digest`) and are never logged, put in URLs, or echoed in errors.
  The browser then shows a key screen and keeps the key in `sessionStorage` (until the tab closes) or, only if the person ticks *Remember*, in `localStorage`.
- **When keys are on, enforcement is on the server.** The interface greys out forbidden buttons, but every route checks the role itself (`tests/test_api_basics.py::test_roles_are_enforced_on_sensitive_routes`). When keys are off, `tests/test_api_basics.py::test_without_access_keys_everyone_is_admin_and_the_interface_is_told_so` documents that everything is open.
- **This is a local-demo trust boundary, not enterprise identity management** - and with keys off it is no access control at all, only network isolation. There are no per-user accounts, no TLS, and the gallery is a single shared collection. Before exposing the service beyond `localhost` put it behind SSO/OIDC and HTTPS (a reverse proxy) and/or switch the keys on.

## 3. Upload and file safety ([`cv/imaging.py`](../backend/app/cv/imaging.py), [`services/storage.py`](../backend/app/services/storage.py))

1. The upload is size-limited (default 10 MB), refused early from `Content-Length` if the whole request is absurd, and read in a bounded way.
2. File **extension, MIME type and real content** are all checked; the content is decoded with Pillow, so a script renamed `evil.png` is rejected (`test_text_renamed_to_png_is_still_rejected`). Only JPEG/PNG/WebP/BMP are accepted.
3. Decoded dimensions are limited (min 32 px, max 6000 px) **before** pixels are decoded - protection against decompression bombs; truncated or corrupt files are rejected.
4. User-supplied file names and paths are **never** used on disk. We store our own re-encoded **JPEG of the person crop** under a random 32-hex-character name; every read, write and delete validates the name against that exact pattern first, so `../../secret` cannot match (tested, including URL-encoded variants).
5. Original upload bytes - and any metadata inside them (EXIF/GPS) - are never written to disk. Uploads live outside the public frontend folder (`backend/data/`, git-ignored).
6. Database access is through the SQLAlchemy ORM with bound parameters only - no SQL is built from strings. Reference IDs must match a strict pattern; deletes need the ID typed back (server-side too); resetting needs an exact phrase and the admin role.
7. Model weights are loaded with `torch.load(weights_only=True)` (cannot run pickled code), architecture-checked, and official files are verified by SHA-256 before use; the app **never downloads anything at run time**.

## 3a. Video uploads ([`services/video_service.py`](../backend/app/services/video_service.py))

A video is a bigger and more complex input than a photo, so it gets its own checks, all tested in `tests/test_api_lab_and_video.py`:

1. **Real type, not the name.** The first bytes must be an MP4/MOV (`ftyp`), AVI (`RIFF…AVI `) or Matroska/WebM header; the extension must also be on the allow-list, but a text file or executable renamed `clip.mp4` is refused (`415`).
2. **Bounded reading.** The body is read in 1 MB chunks and refused once it passes the limit (default 100 MB); an absurd `Content-Length` is refused before anything is read. A half-written file is removed.
3. **Random name, private folder.** The upload is stored under a random 32-hex name in `backend/data/video_uploads/` (git-ignored), never under the client's file name.
4. **Probed before accepted.** OpenCV must be able to open it and decode the first frame; frame size (≥ 32 px, ≤ 3840 px), length (default ≤ 180 s) and the number of sampled frames (default ≤ 120) are checked. A corrupted or unsupported file is deleted at once.
5. **Deleted after use.** The uploaded video is removed when the job ends, whether it succeeded, failed or was cancelled; leftovers from a crash are swept after an hour.
6. **One job at a time.** Video, evaluation and look-alike jobs share one worker, so a flood of uploads cannot start many CPU-heavy jobs at once (`409` for the second).

Frame previews (small JPEGs of the sampled frames) follow the query-crop retention (default 24 h, `0` = none stored) and can be deleted immediately with the job.

## 3b. Web protections

CORS is limited to the configured origins and to the headers/methods actually used. Responses carry `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` and `Cache-Control: no-store` for API calls. Errors never include stack traces or internals;
each carries a request ID for support. `--limit-concurrency 32` (set by `start.ps1`) stops unbounded queueing on a small CPU, and the browser client gives up on a request after 2 minutes. There is **no server-side per-request kill**: a single very slow inference runs to completion.

## 4. What is stored, and for how long

| Data | Stored? | Retention |
|---|---|---|
| Raw uploads | **No** | - |
| Reference crops (our own JPEG) + their body fingerprints (512 numbers) **and face fingerprints (128 numbers, plus the face's position and colour cues)** | yes, for enrolled identities | until the identity is deleted (deletion removes the files **and the face records**; *Reset demo gallery* removes everything) |
| Query crops (for the history screen) | optional | `REID_QUERY_RETENTION_HOURS` (default **24**; `0` = never stored) |
| History rows: outcome, scores, thresholds, timings, candidate IDs | yes | `REID_HISTORY_RETENTION_DAYS` (default **30**) |
| Video uploads | **No** - deleted when the job ends | immediately (crash leftovers: 1 hour) |
| Video frame previews and per-frame decisions | previews: small JPEGs; decisions: scores and outcomes | previews `REID_QUERY_RETENTION_HOURS` (24 h) or until the job is deleted; decisions until the job is deleted |
| Look-alike experiments | scores, pair/mistake records and image *references* (paths inside the dataset) - dataset images are never copied; photos are served on request, re-encoded, only for paths the experiment recorded | kept until the database is wiped |
| Evaluation runs and reports | yes (scores and metrics only; dataset images are never copied) | kept; there is no automatic deletion and no delete button yet (remove `backend/data/` to wipe everything) |
| Audit trail: who (role) did what, when | yes | kept; never contains images or embeddings |
| Logs | route, status, timing, request ID | never images, embeddings or keys |

Cleanup runs at start-up and on demand (**Settings → Run cleanup now**, admin). Expired query crops are deleted from disk and their database references cleared; history rows past retention are removed; orphaned crop files older than the window are swept.

## 4a. Face data is biometric data

Adding face matching means this prototype now creates a **biometric template** (a 128-number face fingerprint) for every enrolled reference photo. What that implies:

- **Consent is explicit.** The enrolment dialog states that a fingerprint of the face and body is stored until the person is deleted. Enrolment is refused without the confirmation.
- **Minimisation.** Only enrolled people have face fingerprints. A *query* face is compared and then discarded: its fingerprint is **not** stored (the history keeps only scores, the decision and, for 24 hours at most, the query crop). A face found in a query is never added to the gallery automatically.
- **Deletion is complete.** Deleting an identity removes its reference photos, body fingerprints and face records, and rebuilds the search index (`tests/test_face_matching.py`, `test_deleting_an_identity_removes_its_faces`).
- **No surveillance features.** There is no camera input, no tracking between frames, no watch-list, no "who is this?" search of unenrolled people.
- **Law.** Biometric data is special-category data under the GDPR and is regulated by India's DPDP Act, Illinois' BIPA and similar laws. A real deployment needs a lawful basis, a stated purpose, a retention rule, security for `backend/data/` (disk encryption) and normally a data-protection impact assessment. This prototype makes **no** claim of compliance and is for authorised test images only.
- **Accuracy and bias.** Face recognition accuracy is known to vary across demographic groups, lighting and cameras. The only face measurement here is on LFW (`FACE_AND_BODY_MATCHING.md`), which does not measure that; do not use the system for decisions that affect people.
- **Spoofing.** There is no liveness check: a photograph or a screen showing an enrolled person's face can be matched like the real face.

## 5. Data sources and licences

Only **authorised** images and **appropriately licensed** datasets. Market-1501 is for non-commercial research (do not redistribute; cite Zheng et al.). Dataset folders, model weights, databases, logs, keys and private images are all git-ignored.
The pretrained OSNet weights are MIT-licensed but were trained on research datasets (MSMT17, DukeMTMC-reID, CUHK03); DukeMTMC-reID was withdrawn by its authors in 2019 over privacy concerns. Review those terms before any use beyond research.
The face models (YuNet, MIT; SFace, Apache-2.0) come from the OpenCV model zoo and were trained by their authors on public face datasets whose terms this project has not audited. The LFW pictures used for the face measurements are a research dataset: they are downloaded by the person who runs the evaluation, kept out of the repository and never redistributed.

## 6. Residual risks and honest gaps

- **Shared keys, no TLS, one tenant** (see §2). - **No rate limiting** beyond connection concurrency; a determined caller with a valid key could still tie up the CPU.
- **Embeddings are biometric data** (body fingerprints, and now face fingerprints). They are stored in the database unencrypted; protect the `backend/data/` folder (disk encryption) and the host.
- **Accuracy and fairness across demographics, lighting and cameras have not been studied.** Errors are not distributed evenly across people; do not rely on this system for decisions affecting individuals.
- The model can be fooled by look-alikes by design of the problem; the whole point of the evaluation is to *measure* how often - see [EVALUATION.md](EVALUATION.md).
- SQLite has no migrations; a production deployment needs PostgreSQL + a migration tool and backups.
