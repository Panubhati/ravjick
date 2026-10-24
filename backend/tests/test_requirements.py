"""The root requirements.txt (used by Vercel) must match the back end's."""

from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent


def pins(path: Path) -> list[str]:
    lines = path.read_text().splitlines()
    return sorted(
        line.strip() for line in lines if line.strip() and not line.startswith("#")
    )


def test_root_requirements_mirror_backend():
    assert pins(BACKEND.parent / "requirements.txt") == pins(
        BACKEND / "requirements.txt"
    )
