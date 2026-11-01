"""Audio gate: is the finished mix actually mixed?

No publisher called a gate on the MIX before this one — `verify_video.py` only proves the file
is decodable (44.1/48 kHz stereo, moov at the head). So a short could ship with its music bed
38 dB below the voice, i.e. with silent gaps and a silent loop bumper, and pass every check.

Three numbers come out of ONE decode of the finished file (no stems needed, so it audits what
was actually PUBLISHED, not what the code intended):

  voice_over_bed  = p90 - p10 of the 20 ms frame energy, dB
                    (p90 is the spoken level, p10 the level of the quiet stretches — the bed)
  dead_air        = share of frames more than 30 dB below the spoken level
  I / TP          = ffmpeg's own integrated LUFS and true peak

Verdicts: AUDIO_OK, or BED_TOO_QUIET / BED_TOO_LOUD / DEAD_AIR / LOUDNESS_OFF.
Exit 0 only for AUDIO_OK. Nothing here is fatal by design — a checker bug must never cost the
day's upload — so callers log it loudly and keep going.

Usage: python audio_gate.py <file> [more files]
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

SR = 48000
HOP_MS = 20.0

BED_MIN_DB = 9.0     # louder than this and the bed competes with the voice (research: -3-5% retention)
BED_MAX_DB = 24.0    # quieter than this and it is a dropout, not a bed
DEAD_AIR_MAX = 0.15  # share of frames 30 dB under the spoken level
LUFS_LO, LUFS_HI = -16.0, -12.5


def frames(path: str) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(SR),
         "-f", "s16le", "-"], capture_output=True, check=True).stdout
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    hop = int(SR * HOP_MS / 1000)
    n = len(a) // hop
    if n < 5:
        raise RuntimeError("audio too short to measure")
    f = a[:n * hop].reshape(n, hop)
    return 20 * np.log10(np.sqrt((f ** 2).mean(axis=1) + 1e-12) + 1e-12)


def ebur128(path: str) -> dict:
    p = subprocess.run(["ffmpeg", "-v", "info", "-i", str(path), "-vn",
                        "-filter_complex", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    t, out = p.stderr, {}
    i = t.rfind("Integrated loudness:")
    if i >= 0:
        for line in t[i:i + 400].splitlines():
            line = line.strip()
            if line.startswith("I:"):
                out["I"] = float(line.split(":")[1].strip().split()[0])
    j = t.rfind("True peak:")
    if j >= 0:
        try:
            out["TP"] = float(t[j:j + 120].splitlines()[0].split(":")[1].strip().split()[0])
        except Exception:  # noqa: BLE001
            pass
    return out


def measure(path: str) -> dict:
    db = frames(path)
    p90 = float(np.percentile(db, 90))
    p10 = float(np.percentile(db, 10))
    m = {
        "file": Path(path).name,
        "speech_dbfs": round(p90, 1),
        "bed_dbfs": round(p10, 1),
        "voice_over_bed_dB": round(p90 - p10, 1),
        "dead_air": round(float((db < p90 - 30).mean()), 3),
    }
    m.update({k: round(v, 1) for k, v in ebur128(path).items()})
    return m


def verdict(m: dict) -> str:
    if m["voice_over_bed_dB"] > BED_MAX_DB:
        return "BED_TOO_QUIET"
    if m["voice_over_bed_dB"] < BED_MIN_DB:
        return "BED_TOO_LOUD"
    if m["dead_air"] > DEAD_AIR_MAX:
        return "DEAD_AIR"
    if "I" in m and not (LUFS_LO <= m["I"] <= LUFS_HI):
        return "LOUDNESS_OFF"
    return "AUDIO_OK"


def main(argv=None) -> int:
    files = (argv or sys.argv[1:])
    if not files:
        print("usage: audio_gate.py <file> [more files]")
        return 2
    bad = 0
    for p in files:
        try:
            m = measure(p)
            v = verdict(m)
        except Exception as e:  # noqa: BLE001
            print(f"AUDIO_GATE_ERROR {Path(p).name}: {type(e).__name__}: {e}")
            bad += 1
            continue
        print(f"{v}: {json.dumps(m)}")
        if v != "AUDIO_OK":
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
