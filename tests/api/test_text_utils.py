from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "common"))

from tts_shared.text_utils import chunk_text, normalize_text


def test_normalize_text_collapses_spacing() -> None:
    text = "One\r\n\r\nTwo   three\x07\n\n\nFour"
    assert normalize_text(text) == "One\n\nTwo three\n\nFour"


def test_chunk_text_splits_long_paragraphs() -> None:
    text = " ".join(["sentence."] * 400)
    chunks = chunk_text(text, target_min=100, target_max=200)
    assert len(chunks) > 1
    assert all(len(chunk) <= 200 for chunk in chunks)
