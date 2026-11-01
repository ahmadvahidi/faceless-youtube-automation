import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/opt/data/workspace/faceless-youtube")
from verify_video import motion_score  # noqa

S = Path("/opt/data/cache/scratch/live_motion")
PY = "/opt/data/skills/.venv/bin/python"
for sec in ("120-160", "330-370"):
    for f in S.glob("uONR_*"):
        f.unlink()
    subprocess.run([PY, "-m", "yt_dlp", "-f", "bv*[height<=480]/b[height<=480]",
                    "--download-sections", "*" + sec,
                    "-o", str(S / ("uONR_" + sec.replace("-", "_") + ".%(ext)s")),
                    "https://www.youtube.com/watch?v=uONRcial5tg"],
                   capture_output=True, text=True)
    f = next(S.glob("uONR_*"), None)
    print(sec, "->", (f.name, round(motion_score(f), 2)) if f else "no download")
