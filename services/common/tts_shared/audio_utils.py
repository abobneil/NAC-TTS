from __future__ import annotations

from pathlib import Path
import subprocess

import numpy as np
import soundfile as sf


def write_silence(path: Path, sample_rate: int, silence_ms: int) -> None:
    frames = int(sample_rate * (silence_ms / 1000))
    sf.write(path, np.zeros(frames, dtype=np.float32), sample_rate)


def combine_wavs(chunk_paths: list[Path], silence_path: Path, output_path: Path) -> None:
    lines: list[str] = []
    for index, chunk in enumerate(chunk_paths):
        lines.append(f"file '{chunk.as_posix()}'")
        if index < len(chunk_paths) - 1:
            lines.append(f"file '{silence_path.as_posix()}'")
    concat_file = output_path.with_suffix(".txt")
    concat_file.write_text("\n".join(lines), encoding="utf-8")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(output_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    concat_file.unlink(missing_ok=True)


def wav_to_mp3(input_path: Path, output_path: Path, sample_rate: int) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-ar",
            str(sample_rate),
            "-ac",
            "1",
            "-codec:a",
            "libmp3lame",
            "-b:a",
            "96k",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
