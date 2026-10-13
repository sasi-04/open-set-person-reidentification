# Third-party notices

This project includes or depends on the following third-party work. This file is not legal advice; check each licence before redistributing.

## OSNet-AIN architecture (source code, ported) - MIT

`backend/app/cv/embedding/osnet_ain.py` is a compact re-write of the OSNet-AIN network from the **Torchreid** project
(<https://github.com/KaiyangZhou/deep-person-reid>), with the identity-classifier head and the weight downloader removed. Layer names are kept identical so the published weights fit.

> MIT License
>
> Copyright (c) 2018 Kaiyang Zhou
>
> Permission is hereby granted, free of charge, to any person obtaining a copy
> of this software and associated documentation files (the "Software"), to deal
> in the Software without restriction, including without limitation the rights
> to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
> copies of the Software, and to permit persons to whom the Software is
> furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all
> copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
> IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
> FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
> AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
> LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
> OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
> SOFTWARE.

Papers: Zhou et al., *Omni-Scale Feature Learning for Person Re-Identification*, ICCV 2019; Zhou et al., *Learning Generalisable Omni-Scale Representations for Person Re-Identification*, TPAMI 2021.

## Model weights (downloaded by `scripts/download_weights.py`, not stored in the repository)

| Weights | Licence | Notes |
|---|---|---|
| OSNet-AIN `osnet_ain_x1_0.pt` etc., mirror `LibreYOLO/LibreReID-osnet` on Hugging Face | MIT (Torchreid) | converted unchanged from Torchreid's multi-source domain-generalisation release; **trained on MSMT17, DukeMTMC-reID and CUHK03**, which are research datasets with their own terms (DukeMTMC-reID was withdrawn by its authors in 2019) |
| torchvision `fasterrcnn_mobilenet_v3_large_fpn` COCO weights | BSD-3-Clause | trained on COCO (CC BY 4.0 annotations) |
| YuNet `face_detection_yunet_2023mar.onnx` (OpenCV model zoo; from ShiqiYu/libfacedetection.train) | MIT | face detector with five landmarks; trained by its authors on WIDER Face. Verified against the SHA-256 in the zoo's Git-LFS pointer |
| SFace `face_recognition_sface_2021dec.onnx` (OpenCV model zoo; from zhongyy/SFace) | Apache-2.0 | face recogniser (128-number fingerprint), a MobileFaceNet trained with the SFace loss; **trained by its authors on public face datasets whose terms this project has not audited** (see the SFace paper). Verified against the SHA-256 in the zoo's Git-LFS pointer |

## Datasets (never committed; supplied by the user)

- **Market-1501** - Zheng, Shen, Tian, Wang, Wang, Tian, *Scalable Person Re-identification: A Benchmark*, ICCV 2015. Released for **non-commercial research use only**; do not redistribute; cite the paper.
- **LFW (Labeled Faces in the Wild)** - Huang, Ramesh, Berg, Learned-Miller, *Labeled Faces in the Wild*, UMass Amherst TR 07-49 (2007). Used **only** by `scripts/evaluate_face_lfw.py` and `scripts/verify_face_vs_body.py` to measure the face stage; downloaded by whoever runs them, never committed, never redistributed. The photographs are news pictures of public figures and carry their own copyrights.

## Methods

Batch-hard triplet loss - Hermans, Beyer, Leibe (2017). Open-set classification rate (OSCR) - Dhamija, Günther, Boult, *The Overlooked Elephant of Object Detection: Open Set* / *Reducing Network Agnostophobia*, NeurIPS 2018.
Platt-style probability calibration - Platt (1999).

## Runtime libraries (all permissively licensed; versions in `backend/requirements.txt` and `frontend/package-lock.json`)

PyTorch & torchvision (BSD-3), NumPy (BSD-3), Pillow (HPND), OpenCV (Apache-2.0), FastAPI & Starlette (MIT/BSD), Pydantic (MIT), SQLAlchemy (MIT), Uvicorn (BSD-3), psutil (BSD-3),
React, React Router, TanStack Query, Radix UI, Recharts, Lucide, clsx, Tailwind CSS, Vite, Vitest, Testing Library (MIT), TypeScript (Apache-2.0).
Fonts: **Inter** and **Poppins** via `@fontsource` packages (SIL Open Font License 1.1).

## Brand reference

Visual cues (accent colour, type pairing, pill buttons) were read from the public website of Zed Digital (<https://zed.digital/>) for inspiration. No Zed Digital logo, imagery or other assets are used, and this project is **not** an official Zed Digital product.
