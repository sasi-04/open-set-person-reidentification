# Lookalike Failure Lab - experiment 87b73e0b

*OpenID Vision - Know when to match. Know when to reject.* Independent technical prototype responding to the Zed Digital PS-1 assignment; not an official Zed Digital product. A similarity score is not a probability and a match is not proof of identity.

* Dataset: **smoke_synthetic** (smoke test; benchmark: NO)
* Searched for look-alikes in the **test** people, seed 0
* Operating target (chosen on calibration people only): DIR@1 (accepted and correct) >= 90.0%, minimise FAR
* Started 2026-10-12T20:25:30.990369+00:00, took 51.7 s

## Warnings

* 'smoke_synthetic' is a smoke test dataset: these results only show that the lab runs end to end. They are NOT benchmark results and must not be quoted as performance.
* The baseline model could not reach the requested operating point on the calibration people (DIR@1 (accepted and correct) >= 90.0%, minimise FAR). Its threshold is a best-effort fallback, not a calibrated one.

## The challenge set

* different-person photo pairs. For each of the 12 most alike pairs of people (ranked by their single most similar pair of photos, using the baseline model) the 2 most similar photo pairs are taken.
* same-person photo pairs from different cameras (all of them, or a seeded sample of 4000 when there are more).
* The impostor side is selected BY the baseline model's similarity, so it is hard for that model by construction. Another model is compared on the very same pairs, which is a fair stress test but not a random sample.
* 'Similar' for mining means similar EMBEDDINGS. Clothing similarity is measured separately (colour histograms, label-free proxy) and reported per pair; the two are not assumed to coincide.

Counts: 12 identity pairs, 24 impostor comparisons, 720 genuine comparisons (27840 different-person pairs compared for the reference rate).

## Results at each model's own calibrated threshold

| Model | Threshold | Test FAR (strangers accepted) | Test recall | Challenge FAR | All-pairs FAR | Challenge recall |
|---|---|---|---|---|---|---|
| Baseline (official pretrained weights) | 0.8344 | 100.00% | 48.00% | 100.00% | 38.3082% | 87.36% |
| improved | - | not available: No fine-tuned checkpoint was selected. None is shipped with this project; scripts/finetune_triplet.py trains one on the development people. | | | | |

The challenge-set false-accept rate is measured on pairs chosen because they are hard; compare it with the all-pairs rate, not with a target FAR.

## Most alike pairs of different people

| # | Person A | Person B | Similarity | Clothing colour similarity | Decision (baseline) |
|---|---|---|---|---|---|
| 1 | P0061 | P0064 | 0.971 | 0.97 (alike) | false_accept |
| 2 | P0077 | P0078 | 0.969 | 0.97 (alike) | false_accept |
| 3 | P0027 | P0061 | 0.967 | 0.64 (alike) | false_accept |
| 4 | P0061 | P0062 | 0.964 | 0.99 (alike) | false_accept |
| 5 | P0013 | P0064 | 0.964 | 0.67 (alike) | false_accept |
| 6 | P0027 | P0064 | 0.962 | 0.59 (alike) | false_accept |
| 7 | P0089 | P0092 | 0.959 | 0.92 (alike) | false_accept |
| 8 | P0097 | P0100 | 0.958 | 0.97 (alike) | false_accept |
| 9 | P0039 | P0077 | 0.957 | 0.56 (alike) | false_accept |
| 10 | P0050 | P0052 | 0.956 | 0.96 (alike) | false_accept |
| 11 | P0013 | P0015 | 0.956 | 0.98 (alike) | false_accept |
| 12 | P0052 | P0061 | 0.956 | 0.69 (alike) | false_accept |

## Mistakes on the test people (baseline)

* Strangers accepted as an enrolled person: **120**
* Enrolled people accepted as a different enrolled person: **39**
* Enrolled people not accepted: **0** (of which 0 sent to review)

'observed' holds recorded measurements. 'possible_causes' are hypotheses worded from those measurements; they have not been tested and must not be read as the proven reason.

## Limitations

* Results are measurements on one sample of people. A threshold chosen on one calibration set does not guarantee the same false-accept rate on new people.
* The challenge set is selected by the baseline model, so its false-accept rate is not comparable with a normal FAR; use the all-pairs reference for that.
* Clothing similarity is a colour-histogram proxy. The datasets carry no clothing labels, so 'similar clothing' is not ground truth.
* Possible causes listed for each mistake are hypotheses derived from recorded numbers; none has been tested by changing the input.
* The dataset 'smoke_synthetic' is a smoke test set, not a public benchmark; its numbers verify the software only.
* No improved model was compared, so this run makes no claim that any training method improves results.
* The test split was searched for look-alikes after the threshold was fixed on calibration people. Do not adjust the model or threshold in response and then reuse the same test split for a final number.

## Reproducibility

Same dataset files, same seed and the same settings give the same splits, pairs and numbers. The fingerprint of each model is recorded under 'models'.
