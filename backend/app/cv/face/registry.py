"""
The two face models and where their weight files come from.

In plain words: face matching uses two small pretrained networks from the OpenCV model zoo,

    YuNet   finds faces in a picture and marks five landmark points (eyes, nose, mouth corners)
    SFace   turns an aligned 112x112 face into 128 numbers; two faces of the same person give
            similar numbers (cosine similarity), faces of different people do not

Like every other model here, the files are fetched ONLY by ``scripts/download_weights.py`` and are
checked against the SHA-256 that the OpenCV zoo itself publishes in its Git-LFS pointer files
(https://github.com/opencv/opencv_zoo, folders ``models/face_detection_yunet`` and
``models/face_recognition_sface``). The app refuses a file whose hash differs.

Licences: YuNet is MIT (libfacedetection.train), SFace is Apache-2.0 (opencv_zoo / zhongyy/SFace).
Caveat, also stated in THIRD_PARTY_NOTICES.md: the networks were trained by their authors on public
face datasets that have their own research terms; this project has not audited them. Research
prototype only.
"""

from __future__ import annotations

from dataclasses import dataclass

_ZOO = "https://github.com/opencv/opencv_zoo/raw/main/models"


@dataclass(frozen=True)
class FaceModelFile:
    role: str
    filename: str
    url: str
    sha256: str
    size_bytes: int
    licence: str
    source: str


FACE_DETECTOR_FILE = FaceModelFile(
    role="detector",
    filename="face_detection_yunet_2023mar.onnx",
    url=f"{_ZOO}/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    sha256="8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    size_bytes=232_589,
    licence="MIT",
    source="https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet",
)

FACE_RECOGNIZER_FILE = FaceModelFile(
    role="recognizer",
    filename="face_recognition_sface_2021dec.onnx",
    url=f"{_ZOO}/face_recognition_sface/face_recognition_sface_2021dec.onnx",
    sha256="0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
    size_bytes=38_696_353,
    licence="Apache-2.0",
    source="https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface",
)

FACE_MODEL_FILES = (FACE_DETECTOR_FILE, FACE_RECOGNIZER_FILE)

FACE_DIM = 128
# The OpenCV model card quotes 99.40 % accuracy for SFace on the standard LFW verification protocol.
# This project re-measured it itself - see docs/FACE_AND_BODY_MATCHING.md (scripts/evaluate_face_lfw.py).
