#!/usr/bin/env python3
"""Concatenate numbered mp4 clips into one file."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("videos", nargs="+", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args()

    existing = [p for p in args.videos if p.exists()]
    if not existing:
        print("No videos found", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        for p in existing:
            f.write(f"file '{p.resolve().as_posix()}'\n")
        list_path = f.name

    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_path, "-c", "copy", str(args.output),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
