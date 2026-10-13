"""
Application settings.

In plain words: every knob the app can be configured with lives here, in ONE
place. Values come from environment variables prefixed with ``REID_`` (or from
the ``.env`` file in the repository root). Nothing else in the code base reads
environment variables directly, so if you want to know "what can I configure?"
this file is the answer.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# backend/app/core/config.py  ->  parents[3] is the repository root.
REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_prefix="REID_",
        extra="ignore",
    )

    # ------------------------------------------------------------------ paths
    data_dir: Path = BACKEND_DIR / "data"
    weights_dir: Path = BACKEND_DIR / "weights"
    datasets_dir: Path = REPO_ROOT / "datasets"
    # The public-domain sample photos and demo_manifest.json used by the built-in "Example demo" screen.
    demo_dir: Path = REPO_ROOT / "demo" / "samples"
    # Leave empty for the built-in SQLite file. To use PostgreSQL install a driver (pip install "psycopg[binary]")
    # and set e.g. postgresql+psycopg://user:password@host/dbname. Tables are created on start-up (no migrations yet).
    database_url: str | None = None

    # ------------------------------------------------------------ access control
    # OFF by default: the server listens on 127.0.0.1 only, so on a single-user demo machine nobody has to type a key.
    # Set REID_AUTH_REQUIRED=true (and the three keys below) before sharing the server with anyone else.
    auth_required: bool = False
    viewer_key: SecretStr | None = None
    operator_key: SecretStr | None = None
    admin_key: SecretStr | None = None

    # ---------------------------------------------------------------- web server
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # ------------------------------------------------------------------- models
    embedding_model: str = "osnet_ain_x1_0"
    embedding_checkpoint: Path | None = None
    use_flip_tta: bool = False
    # Merge batch-norm layers into the convolutions. The output is identical (checked by a test) but, measured
    # fairly on the development laptop, the speed-up was only ~4% and not consistent (docs/PERFORMANCE.md),
    # so it is OFF by default. It may help more on other hardware.
    fold_batch_norm: bool = False
    device: Literal["auto", "cpu", "cuda"] = "auto"
    embedding_batch_size: int = Field(default=32, ge=1, le=256)

    # Face evidence (YuNet + SFace, see cv/face). On by default: faces are far more discriminative than clothing.
    # Set REID_FACE_MATCHING=false to run the original body-only system (the PS-1 baseline) and never load the face models.
    face_matching: bool = True

    detector_model: str = "fasterrcnn_mobilenet_v3_large_fpn"
    detector_min_size: int = Field(default=480, ge=160, le=1600)
    detector_score_threshold: float = Field(default=0.5, ge=0.05, le=0.99)
    detector_max_people: int = Field(default=20, ge=1, le=100)

    # ------------------------------------------------------------ upload limits
    max_upload_mb: int = Field(default=10, ge=1, le=100)
    max_image_side: int = Field(default=6000, ge=256, le=20000)
    min_image_side: int = Field(default=32, ge=8)
    max_enroll_files: int = Field(default=20, ge=1, le=100)
    allowed_extensions: tuple[str, ...] = (".jpg", ".jpeg", ".png", ".webp", ".bmp")

    # ------------------------------------------------------------- video limits
    # Video Explorer processes a prerecorded clip by sampling frames. These caps keep one upload from
    # monopolising a small CPU: file size, clip length, frames actually processed, and frame dimensions.
    max_video_mb: int = Field(default=100, ge=1, le=1000)
    max_video_seconds: int = Field(default=180, ge=1, le=3600)
    max_video_frames: int = Field(default=120, ge=1, le=1000)
    max_video_side: int = Field(default=3840, ge=256, le=8000)

    # ------------------------------------------------------ privacy / retention
    query_retention_hours: int = Field(default=24, ge=0)
    history_retention_days: int = Field(default=30, ge=1)

    # ------------------------------------------------------ starting policy
    default_accept_threshold: float = Field(default=0.70, ge=-1.0, le=1.0)

    # ------------------------------------------------------------- evaluation
    evaluation_bootstrap_samples: int = Field(default=300, ge=0, le=5000)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_comma_separated(cls, value: object) -> object:
        # Lets .env contain "http://a,http://b" instead of a JSON list.
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    # Convenience paths derived from data_dir (kept as properties so they can
    # never get out of sync with data_dir).
    @property
    def effective_database_url(self) -> str:
        """The configured REID_DATABASE_URL, or a SQLite file in the data folder when none is set."""
        return self.database_url or f"sqlite:///{(self.data_dir / 'reid.sqlite').as_posix()}"

    @property
    def reference_dir(self) -> Path:
        return self.data_dir / "references"

    @property
    def query_dir(self) -> Path:
        return self.data_dir / "queries"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def report_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def video_upload_dir(self) -> Path:
        """Uploaded videos wait here only while they are processed; they are deleted straight afterwards."""
        return self.data_dir / "video_uploads"

    @property
    def video_frame_dir(self) -> Path:
        """Small thumbnails of the sampled frames, one folder per video job, kept for ``query_retention_hours``."""
        return self.data_dir / "video_frames"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def max_video_bytes(self) -> int:
        return self.max_video_mb * 1024 * 1024

    def ensure_directories(self) -> None:
        for folder in (
            self.data_dir,
            self.weights_dir,
            self.reference_dir,
            self.query_dir,
            self.cache_dir,
            self.report_dir,
            self.video_upload_dir,
            self.video_frame_dir,
        ):
            folder.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Settings are read once and shared (tests override this via dependency overrides)."""
    return Settings()
