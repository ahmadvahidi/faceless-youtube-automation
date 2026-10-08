#!/usr/bin/env python3
"""
Housekeeping: keep the faceless-youtube workspace lean and self-managed.

Rules (all automatic, no human needed):
  * work/  -> intermediate scene/caption files are deleted after each video is
              sent (they are only needed during assembly).
  * out/   -> keep the newest K videos (default 6); delete older ones.
  * assets/ -> keep the newest K narration mp3s + images; delete older ones.
  * Guard  -> abort the run if free disk under a threshold (default 2 GiB).

Usage:
  python housekeeping.py          # clean + report
  python housekeeping.py --dry    # report only, delete nothing
"""

import argparse
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
WORK = ROOT / "work"
ASSETS = ROOT / "assets"

KEEP_VIDEOS = 6
KEEP_ASSETS = 20
MIN_FREE_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB


def free_disk_bytes(path: Path) -> int:
    st = os.statvfs(path)
    return st.f_bavail * st.f_frsize


def by_mtime(paths):
    return sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True)


def clean_work():
    """Delete ALL work/ intermediates — they are rebuilt each run."""
    removed = 0
    if WORK.exists():
        for p in WORK.iterdir():
            if p.is_file():
                p.unlink(missing_ok=True)
                removed += 1
    return removed


def prune_keep_newest(dir_path: Path, keep: int, pattern="*"):
    removed = 0
    if not dir_path.exists():
        return 0
    files = [p for p in dir_path.iterdir() if p.is_file()]
    files = by_mtime(files)
    for p in files[keep:]:
        p.unlink(missing_ok=True)
        removed += 1
    return removed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--min-free-gb", type=float, default=2.0)
    args = ap.parse_args()

    free = free_disk_bytes(ROOT)
    free_gb = free / (1024 ** 3)
    print(f"[disk] free: {free_gb:.2f} GiB")

    if free < args.min_free_gb * 1024 ** 3 and not args.dry:
        print(f"[guard] ABORT: free disk {free_gb:.2f} GiB < threshold "
              f"{args.min_free_gb} GiB", flush=True)
        return 1

    if args.dry:
        print("[dry] would clean work/ + prune out/ and assets/")
        return 0

    w = clean_work()
    o = prune_keep_newest(OUT, KEEP_VIDEOS)
    a = prune_keep_newest(ASSETS, KEEP_ASSETS)
    print(f"[clean] work removed {w}, out pruned {o}, assets pruned {a}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
