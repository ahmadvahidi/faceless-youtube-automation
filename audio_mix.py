"""Bed gain-staging + ducking for every narration mix.

WHY THIS EXISTS (measured 2026-10-17 on the real published output):
the trend/CS shorts shipped their music bed 38 dB below the voice (speech p90 -13.2 dBFS,
bed-only tail -51.8 dBFS) and the maths shorts 30 dB below — while the audio research places
the useful band at 14-20 dB. A bed that far down is not "subtle", it is a dropout: every gap
between phrases AND the closing loop bumper played as digital near-silence, which is the audio
version of a frozen frame. The bed gain used to be two magic numbers multiplied together
(`make_bg_music(volume=0.12)` x `volume=0.20` = 0.024), so it was set by hand and never checked
against the narration it has to sit under.

The rule here: MEASURE the two stems, then place the bed at a DEFINED distance under the spoken
level, and let a sidechain compressor lift it back up whenever the voice stops. That is what the
research describes (bed at 15-20 % of the voice while speaking, 25-30 % in the pauses) and it is
self-calibrating: edge-tts, the Piper fallback and a quiet take all land in the same place.

The gate that proves it lives next to this file: `audio_gate.py`.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

# Unducked bed level, dB below the narration's spoken level. The compressor below pulls it
# further down while the voice is talking, so this is the level the gaps and the loop bumper hear.
TARGET_UNDER_DB = 16.0

# Gentle broadcast ducking: ~5 dB of gain reduction on a voice at -18 dBFS.
# threshold 0.05 = -26 dBFS, ratio 3, attack 20 ms (fast enough that the first syllable is never
# covered), release 400 ms (below ~100 ms the bed "pumps" between words, which is worse than none).
SIDECHAIN = "sidechaincompress=threshold=0.05:ratio=3:attack=20:release=400"
RES = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"

HOP_MS = 20.0
SR = 48000


def _frame_db(path: str) -> list:
    """20 ms frame RMS in dBFS. Empty list if the measurement is not possible."""
    try:
        import numpy as np  # local: keeps this module importable without numpy
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(SR),
             "-f", "s16le", "-"], capture_output=True, check=True).stdout
        a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        hop = int(SR * HOP_MS / 1000)
        n = len(a) // hop
        if n < 3:
            return []
        f = a[:n * hop].reshape(n, hop)
        rms = np.sqrt((f ** 2).mean(axis=1) + 1e-12)
        return [float(x) for x in 20 * np.log10(rms + 1e-12)]
    except Exception:  # noqa: BLE001 — a missing numpy must never kill a render
        return []


def _pct(db: list, p: float, default: float) -> float:
    if not db:
        return default
    s = sorted(db)
    k = min(len(s) - 1, max(0, int(round((len(s) - 1) * p / 100.0))))
    return s[k]


def speech_db(path: str, default: float = -18.0) -> float:
    """The spoken level: the 90th percentile of the 20 ms frame energy."""
    return _pct(_frame_db(path), 90, default)


def bed_db(path: str, default: float = -30.0) -> float:
    """The bed's own level. A pad is steady, so the median is the honest number."""
    return _pct(_frame_db(path), 50, default)


def bed_gain(narration: str, bed: str, under_db: float = TARGET_UNDER_DB) -> float:
    """Linear gain that puts `bed` exactly `under_db` below the narration's spoken level."""
    s, b = _frame_db(narration), _frame_db(bed)
    if not s or not b:
        return 1.0
    return float(10 ** ((_pct(s, 90, -18.0) - under_db - _pct(b, 50, -30.0)) / 20.0))


def _dur(path: str, default: float = 0.0) -> float:
    try:
        p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", str(path)], capture_output=True, text=True,
                           check=True)
        return float(p.stdout.strip())
    except Exception:  # noqa: BLE001
        return default


def mix_audio(narr_idx: int, bed_idx: int, narr: str, bed: str,
              loud: str, extra: str = "", under_db: float = TARGET_UNDER_DB) -> str:
    """Filter snippet: narration at full level, bed gain-staged then ducked under it.

    `extra` is appended to the narration leg before the resample (unused today; kept so a
    caller can add a filter without touching this file).
    """
    g = bed_gain(narr, bed, under_db)
    # The narration feeds TWO filters (the sidechain key and the final mix). Reusing one label
    # makes libavfilter fail the whole graph with the misleading "Stream specifier 'n' ...
    # matches no streams" / "Error binding filtergraph inputs/outputs" — measured on a real
    # build, and it silently degraded to a narration-only mux. An explicit asplit fixes it.
    # Second trap, measured on the same build: sidechaincompress stops at the SHORTER of its
    # two inputs, so the ducked bed ended with the voice and the tail became narration-length —
    # which then let `-shortest` cut the 0.75 s loop bumper off the picture (frame_gate
    # LOOP_BROKEN 47.8 %). The key is padded with silence past the end of the bed instead: a
    # silent key is exactly right there, because it leaves the bed unducked through the bumper.
    pad = _dur(bed) + 0.5
    key = f",apad=whole_dur={pad:.3f}" if pad > 0.6 else ""
    return (
        f"[{narr_idx}:a]{extra}{RES}{key},asplit=2[n1][n2];"
        f"[{bed_idx}:a]volume={g:.4f},{RES}[bgr];"
        f"[bgr][n1]{SIDECHAIN}[bgd];"
        f"[n2][bgd]amix=inputs=2:duration=longest:normalize=0,{loud}[a]"
    )
