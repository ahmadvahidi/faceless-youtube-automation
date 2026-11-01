# Faceless YouTube Automation

An open-source pipeline that turns **trending topics into finished, auto-uploaded
YouTube videos** — no human in the loop, no paid API required.

Every run: picks a money/finance topic grounded in real Google Trends → writes the
script with an LLM → voices it (edge-tts, free) → adds cinematic camera motion +
captions (FFmpeg zoompan + PIL) → sends the finished video + title/description to
a Telegram group where your uploader bot pushes it to YouTube.

## It runs in production

The pipeline powers **[DOPEAK](https://www.youtube.com/@wearedopeak)** — 120 videos
produced, rendered and uploaded end to end with no manual editing, on a single VPS,
using only free APIs (edge-tts for voice, Google Trends for topics).

Running cost: one small VPS. No paid TTS, no paid stock footage, no editing time.

## Features

- **Trend-driven topics** — pulls live Google Trends, filters to the high-RPM
  finance/money niche (configurable)
- **LLM scriptwriting** — DeepSeek via Ollama Cloud (any OpenAI-compatible endpoint)
- **Free voiceover** — edge-tts, no API key
- **Cinematic motion** — eased zoom/pan (Ken Burns), teal-orange grade, vignette,
  readable captions with a soft dark gradient
- **Self-managing** — housekeeping prunes old outputs, cleans intermediates, and
  guards free disk space
- **Auto-delivery** — posts the MP4 + caption straight to a Telegram group

## Requirements

- Python 3.10+
- FFmpeg on PATH
- Python deps: `edge-tts`, `moviepy`, `Pillow`, `numpy`

```bash
pip install edge-tts moviepy Pillow numpy
```

## Setup

```bash
git clone <this-repo>
cd <this-repo>
cp .env.example .env   # then fill in LLM_API_KEY + TELEGRAM_BOT_TOKEN + group id
```

## Usage

**One-off — build + send N videos now:**
```bash
python run_daily.py 2
```

**Schedule it (cron):**
```
0 9,21 * * *  cd /path/to/repo && python run_daily.py 2
```

## How it works

```
pick_topics (Google Trends → finance niche)
   → llm_script (DeepSeek narration)
   → synth_with_boundaries (edge-tts + sentence timing)
   → render scenes (ffmpeg zoompan motion + PIL caption PNG)
   → assemble + grade (ffmpeg concat, teal-orange, vignette)
   → send_video (Telegram bot → your uploader group)
   → housekeeping (prune + disk guard)
```

## Configuration

All secrets live in `.env`. Key knobs (in `daily_videos.py` / `housekeeping.py`):

| Knob | Where | Default |
|---|---|---|
| Niche / topic prompt | `pick_topics()` | finance/money |
| Voice | `VOICE` | `en-US-GuyNeural` |
| N videos per run | `run_daily.py N` | 2 |
| Keep N videos | `KEEP_VIDEOS` | 6 |
| Disk guard | `MIN_FREE_BYTES` | 2 GiB |

## License

MIT
