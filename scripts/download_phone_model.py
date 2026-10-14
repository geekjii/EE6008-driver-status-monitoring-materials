"""Download and verify the official Ultralytics YOLO26n detection weights."""

import argparse
import hashlib
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional, Sequence


MODEL_URL = (
    "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26n.pt"
)
EXPECTED_SHA256 = "9b09cc8bf347f0fc8a5f7657480587f25db09b34bf33b0652110fb03a8ad4fef"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(destination: Path, force: bool = False) -> None:
    destination = destination.expanduser().resolve()
    if destination.exists() and not force:
        actual_sha256 = sha256(destination)
        if actual_sha256 != EXPECTED_SHA256:
            raise RuntimeError(
                "Existing model checksum mismatch: expected {}, got {}".format(
                    EXPECTED_SHA256, actual_sha256
                )
            )
        print("Model already exists and checksum is valid: {}".format(destination))
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix="yolo26n_", suffix=".pt", delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        print("Downloading official Ultralytics YOLO26n model...")
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
    parser.add_argument("--output", type=Path, default=Path("models/yolo26n.pt"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    download(args.output, force=args.force)


if __name__ == "__main__":
    main()

