# datasets/

Evaluation datasets live here. **Their contents are git-ignored and must never be committed or redistributed.**

| Folder | What |
|---|---|
| `market1501/` | the public benchmark - **you must obtain it from its authors** (non-commercial research use; cite Zheng et al., ICCV 2015) |
| `smoke_synthetic/` | cartoon mannequins made by `scripts/make_smoke_dataset.py` to check the pipeline runs. **Not a benchmark.** |

```powershell
# from the repository root
backend\.venv\Scripts\python.exe scripts\prepare_dataset.py unpack C:\Downloads\Market-1501-v15.09.15.zip --name market1501
backend\.venv\Scripts\python.exe scripts\prepare_dataset.py inspect market1501
```

Expected layout, other layouts, the optional `hard_subset.json` annotation file and `dataset.json` manifest: see the main [README, sections 9-10](../README.md#9-dataset-acquisition) and [docs/EVALUATION.md](../docs/EVALUATION.md).
