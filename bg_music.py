"""Generate a soft ambient background-music bed with ffmpeg (no assets needed).

Builds a gentle chord pad (layered sines), fades in/out, at 48kHz stereo so it
mixes cleanly under the narration in assemble_final.
"""
import subprocess

# --- variation engine: ONE bed per video, never the same chord stack twice in a row ----
# Before this, every video on every channel used the identical A-minor pad (measured: the
# faceless and cs copies were byte-identical files, and the math copy used the same five
# frequencies), so the audio signature of a channel never changed. variant 0 is the ORIGINAL
# sound, so existing callers keep their exact output; callers now pass a rotating seed.
_CHORDS = [
    [110.00, 164.81, 220.00, 261.63, 329.63],   # 0 A minor  — the original bed
    [103.83, 155.56, 207.65, 261.63, 311.13],   # 1 Ab/Eb, darker and wider
    [123.47, 185.00, 246.94, 311.13, 369.99],   # 2 B minor, brighter
    [98.00, 146.83, 196.00, 293.66, 392.00],    # 3 G add9, open and calm
    [130.81, 196.00, 261.63, 329.63, 392.00],   # 4 C major, warm
    [116.54, 174.61, 233.08, 349.23, 440.00],   # 5 Bb major, airy
    # 6/7 added 2026-10-27 (repetition guardian): a 6-variant bed returns every sixth video.
    [146.83, 174.61, 220.00, 293.66, 349.23],   # 6 D minor, tense but soft
    [164.81, 196.00, 246.94, 329.63, 392.00],   # 7 E minor, open fifth

]


def make_bg_music(duration: float, out_path: str, volume: float = 0.10,
                  variant: int = 0) -> str:
    """Create a calm chord pad of the given duration (48kHz stereo).

    `variant` selects the chord stack (0 = the original A-minor bed); the pipeline passes a
    seed that rotates per video so consecutive uploads never carry the same music bed.
    """
    freqs = _CHORDS[int(variant) % len(_CHORDS)]
    inputs = []
    parts = []
    for i, f in enumerate(freqs):
        inputs += ["-f", "lavfi", "-i", f"sine=frequency={f}:duration={duration}"]
        parts.append(f"[{i}:a]volume={1.0/len(freqs)}[v{i}]")
    n = len(freqs)
    mix = "".join(f"[v{i}]" for i in range(n))
    filt = (";".join(parts) + f";{mix}amix=inputs={n}:normalize=0,"
            f"volume={volume},afade=t=in:st=0:d=2,"
            f"afade=t=out:st={max(0, duration - 2)}:d=2,"
            f"aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[out]")
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", filt,
           "-map", "[out]", "-t", str(duration), "-ar", "48000", "-ac", "2",
           out_path]
    subprocess.run(cmd, capture_output=True, check=True)
    return out_path
