#!/usr/bin/env python3
"""Extract the last frame from a video file."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract last frame from video")
    parser.add_argument("video", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args()

    if not args.video.exists():
        print(f"Video not found: {args.video}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-sseof",
        "-0.1",
        "-i",
        str(args.video),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(args.output),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
