"""Download the official MediaPipe Face Landmarker model bundle."""

import argparse
import hashlib
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional, Sequence


MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
EXPECTED_SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(destination: Path, force: bool = False) -> None:
    destination = destination.expanduser().resolve()
    if destination.exists() and not force:
        print("Model already exists: {}".format(destination))
        print("SHA256: {}".format(sha256(destination)))
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix="face_landmarker_", suffix=".task", delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        print("Downloading official MediaPipe model...")
        urllib.request.urlretrieve(MODEL_URL, temporary_path)
        if temporary_path.stat().st_size < 1024 * 1024:
            raise RuntimeError("Downloaded model is unexpectedly small")
        actual_sha256 = sha256(temporary_path)
        if actual_sha256 != EXPECTED_SHA256:
            raise RuntimeError(
                "Model checksum mismatch: expected {}, got {}".format(
                    EXPECTED_SHA256, actual_sha256
                )
            )
        temporary_path.replace(destination)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    print("Saved: {}".format(destination))
    print("SHA256: {}".format(sha256(destination)))


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=Path("models/face_landmarker.task")
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    download(args.output, force=args.force)


if __name__ == "__main__":
    main()
