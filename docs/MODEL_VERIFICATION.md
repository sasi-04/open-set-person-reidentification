# Embedding-model verification (2026-10-25)

*Why this page exists: the embedding network is the heart of the system, and the first version assumed - without measuring - that the
OSNet-AIN weight file it shipped was a good person-re-identification model. Checking that assumption found it was not. This page records
the check, the evidence and the fix, so nobody has to take any of it on trust.*

## 1. What was checked

A closed-set sanity test with the simplest possible protocol, run through the project's own preprocessing (`cv/embedding/extractor.py`):

* **Data:** Market-1501 (`bounding_box_test`, junk and distractor files dropped), 100 identities drawn at random (seed 0), each with at least two cameras and six images.
* **Queries:** one image per identity. **Gallery:** up to five images of the same identity from *other* cameras (499 images in total).
* **Score:** cosine similarity of L2-normalised embeddings; Rank-1 (is the nearest gallery image the same person?) and mean average precision.
* **Script:** the test used is reproduced by `scripts/verify_embedding.py`.

## 2. Result

| Network | Weights | Rank-1 | mAP |
|---|---|---|---|
| OSNet-AIN x1.0 (the first version's default) | `osnet_ain_x1_0.pt` from the Hugging Face mirror `LibreYOLO/LibreReID-osnet` | **20.0 %** | **12.7 %** |
| The same weights inside **Torchreid's own** `osnet_ain.py` | same file | **20.0 %** | **12.7 %** |
| Pooled features before the last layer, or mean-centred | same file | 20 - 23 % | 13 - 15 % |
| Colour channels swapped (BGR instead of RGB) | same file | 19.0 % | 12.2 % |
| **OSNet x1.0, Torchreid's official multi-source checkpoint** (`osnet_ms_d_c.pth.tar`) in Torchreid's own `osnet.py` | official | **81.0 %** | **68.8 %** |

(Chance for 100 identities is 1 %. The checkpoint itself records a Market-1501 Rank-1 of 72.5 % on the full benchmark at epoch 50; our 100-identity subset is easier, so 81 % is consistent.)

## 3. What this proves, and what it does not

* **Our network code and preprocessing are correct.** The project's re-written OSNet-AIN gave *exactly* the same 20.0 % / 12.7 % as Torchreid's own reference implementation when loaded with the same file, and the same protocol and preprocessing gave 81 % with a trustworthy checkpoint.
* **The shipped OSNet-AIN weight file is the defect.** Its classifier-free layout and trained batch-norm statistics (150,240 tracked batches) show it was trained, but it does not separate people across cameras on Market-1501. Why (a different training objective, a conversion error, a different input convention) is **not established**; we only know that, as shipped, it is unfit for this task. The three smaller `osnet_ain_x*` files come from the same source and were **not** measured; they are flagged unverified.
* **It does not prove** anything about the pedestrian-camera accuracy of the replacement beyond what `docs/EXPERIMENT_RESULTS.md` measures.

## 4. The fix

| Item | Before | After |
|---|---|---|
| Default embedding model | `osnet_ain_x1_0` | **`osnet_x1_0`** (plain OSNet x1.0, Torchreid multi-source weights: MSMT17 + DukeMTMC-reID + CUHK03; **Market-1501 is not in the training data**) |
| Architecture code | `cv/embedding/osnet_ain.py` | + `cv/embedding/osnet.py` (inference-only port of Torchreid `osnet_x1_0`, MIT); `network.py` picks the class named in the registry |
| Weight provenance | file SHA-256 | the official checkpoint is downloaded, **its SHA-256 is checked** (`53cb9f42...8515`), it is converted **once** to a tensors-only file (`cv/embedding/convert.py`), and the converted file is pinned by a **content digest of its tensors** (`c552472f...3164`) because `torch.save` output is not byte-reproducible; the application only ever reads the converted file with the safe loader (`weights_only=True`) |
| Failed files | silently trusted | flagged `verified=False` with the measured evidence in the registry; `scripts/download_weights.py` prints a warning if you fetch one |
| Embedding size | 512 | 512 (unchanged) - existing galleries are marked *stale* and rebuilt, never silently mixed |

Licence notes: Torchreid code is MIT (Kaiyang Zhou). The checkpoint was trained on research datasets that carry their own terms (DukeMTMC-reID was withdrawn by its authors in 2019); it is used here for research demonstration only. The checkpoint is fetched from a third-party mirror (no licence declared there) and pinned by hash; the upstream is the Torchreid model zoo.

## 5. Consequences you should know about

* **Every threshold that was tuned for the old file is void.** The body threshold 0.70 was an unvalidated starting value for the old network; it is re-measured on Market-1501 in `docs/EXPERIMENT_RESULTS.md`.
* **The home-page example's *clothes-only* numbers changed** (they are produced by the same network) - see `docs/OPEN_SET_EXAMPLE.md` for the re-measured values. The *face* path (YuNet + SFace) was never affected.
* **Honest status of the earlier claims:** statements in older documents that the OSNet-AIN embeddings were "validated by real-model tests" meant *shape, normalisation and determinism* - never discriminative power. That gap is what this page closes.
