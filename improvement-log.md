# Improvement-agent log

One line per run: date · lens · what changed · how it was verified.
Rotate the lens so four runs a day are not redundant:
(a) retention/hooks · (b) packaging: title/thumbnail/first frame · (c) audio/voice/music ·
(d) subtitles/visual style/pacing · (e) money formats/monetization · (f) novel formats.

| date | lens | change | evidence |
|---|---|---|---|
| 2026-10-15 | (b) packaging + (e) monetization | `trend-radar/trend_scout.py`: listicle prompt (count in title AND hook), `strip_signoff()` + `sanitize_concept()` packaging gate, `load_offlimits()` (fixes an undefined `HERE` that crashed the CLI before generating anything), category-404 fallback for the YouTube chart. `trend-radar/build_concept.py`: on-screen "idea N of M" counter, recap strip on the payoff card, duplicate-caption suppression, `sanitize()` on concepts read from disk, `--no-record`, `--max-seconds` default 42→32. `run_trend_short.sh`: 32s cap. Lessons + money thresholds in the `faceless-youtube` skill and PLAYBOOK.md. | `test_layout.py` → LAYOUT_OK (19 checks, gap ≥ 20px, sign-off/recap/dedup gates); real render of today's concept `3 ways Powerball odds surprise you` → 27.3s, `OK: aac 48000Hz 2ch, moov at byte 36`; frames read back by vision (counter "idea 2 of 3" on the steps card, full recap on the payoff card, no duplication) |
| 2026-10-15 (2nd) | (d) subtitles/visual style/pacing | `trend-radar/build_concept.py`: **word-by-word (karaoke) burned captions** — new `synth_timed()` grabs edge-tts `WordBoundary` timings (`boundary="WordBoundary"`; 7.3 defaults to SentenceBoundary and silently yields 0 word marks), `sentence_times()` maps them (char-proportional fallback for the Piper voice), `caption_strip()` draws one transparent band per word with the active word amber + numbers teal, `encode_sentence()` chains one continuous `zoompan` per sentence with `overlay=...:enable='between(t,a,b)'` so the motion never stutters; loop bumper recomposites the caption. Caption band position **pinned** (`CAP_BOTTOM = H-400`, `CAP_GAP = 56`) instead of hugging the content, so it never sits under the Shorts UI and never moves between cards; hook card got a fit loop to respect the smaller content box. `test_layout.py`: +3 check groups (caption zone, karaoke strip, timings). Lesson in the `faceless-youtube` skill; PLAYBOOK.md short-form standard updated. | `test_layout.py` → LAYOUT_OK (30 checks: band bottom pinned at 1520 = clear of the y>1540 UI strip, one band position across hook/steps/payoff, strip changes per active word, teal number, estimate fallback keeps every word). Real render `--index 0 --slug test_karaoke --no-record` → `[cap] 76 word boundaries for 76 words (word-synced)`, 29.9s, `OK: aac 48000Hz 2ch, moov at byte 36`. Pixel proof: amber centroid advances 171→298→454→671→877 within one caption line (18 distinct positions, no line ever moves backwards, 0 frames inside the UI strip) → KARAOKE_OK. Vision read-back at word #4 (`heavy.` 2.92-4.24s) and #30 (`twenty` 13.72-14.05s) shows exactly those words amber → sync confirmed against the audio's own timings. Forced-Piper build (marks=0) → 18.7s, 48kHz stereo, caption band present with "life." highlighted, no tofu. Test renders deleted afterwards; `used.json` untouched. |

| 2026-10-15 (3rd) | (c) audio/voice/music | Measured first, then fixed, on a real render: the raw narration was **-19.9 LUFS / -1.1 dBTP** (YouTube normalises to -14 LUFS and never boosts a quiet upload → the channel played ~6 dB under the whole feed) and held **7.16 s of DETECTED silence in 27.1 s** — a ~0.89 s perceptual pause at every sentence boundary (the detector's span overstates a real gap by ~0.18 s, so the perceptual dead air was ~4.5 s / 17%). `trend-radar/build_concept.py`: new `detect_silences`/`spoken_words`/`plan_cuts`/`shift_time`/`remap_times`/`tighten_audio` — cuts the excess of every pause measured from the END of the last spoken word, never inside `next word onset - PRE`, and the caption table is moved through the SAME cuts; `speech_text()` (standalone en-dashes removed → word count matches the marks again); `align_marks()` (text-based mark↔word alignment + skip tolerance, replacing the count-equality test that silently collapsed the whole video to estimated captions); `loudnorm=I=-14:TP=-1.5:LRA=11` in the final mux; bed `volume` 0.14→0.20, `fade_in` 2 s→0.3 s, bed rendered past the picture so its fade-out never silences the loop bumper; the timing table is dumped to `out/<slug>/caps.json` so sync is checkable after the fact (edge-tts does NOT return the same marks twice: 27.12 s vs 26.86 s for identical text). `math-videos/bg_music.py`: `fade_in`/`fade_out` params. `pipeline_v3.assemble_final` (faceless-youtube + cs-videos copies) and `math-videos/build_video.assemble`: loudnorm added — this lifts the math, CS and finance lines too. New gates `test_pacing.py` + `test_audio.py`. | `test_pacing.py` → PACING_OK (65/65 marks aligned word-synced; 5 pauses cut = 3.27 s; boundary pauses 0.89 s → **0.24 s**; video 27.6 s → 24.3 s, 12% shorter). Real render `build_concept.py --index 3 --slug test_pace_loud --no-record` → 20.8 s, `OK: aac 48000Hz 2ch, moov at byte 36`; `test_audio.py` → AUDIO_OK (dead air in the spoken part 10%, **-14.3 LUFS**, TP -1.4 dBTP, text on 8/8 sampled frames); karaoke sync verified numerically against the render's own timing table → **19/19 sampled words highlighted at their own x (worst 1.4 px)**, `SYNC_OK`; `test_layout.py` → LAYOUT_OK; raw-vs-fixed comparison at four silencedetect thresholds; `assemble_final` test on 2 scenes + fresh edge-tts narration → -19.7 → **-14.1 LUFS**, ASSEMBLE_OK. One bug of my own caught by the test and fixed (an inverted regex collapsed the narration 67→16 words). |

| 2026-10-15 (4th) | (a) retention/hooks + structure | **The maths line was never publishing Shorts at all.** `pipeline_v3` and the Manim maths scenes render 1920x1080 LANDSCAPE, and YouTube only classifies a video as a Short when it is vertical/square and <=3 min — so every maths upload was locked out of the Shorts feed (the one surface that reaches non-subscribers). Proved with the `/shorts/<id>` redirect test: the vertical trend-radar short answers HTTP 200, every maths upload answers 303 -> /watch. New `math-videos/captions.py` composes the finished landscape render onto a 1080x1920 canvas whose `pad` colour is the SCENE'S OWN background (theme.BG, reloaded per build), with a frame-1 headline band (the title + a "MATH IN 45 SECONDS" kicker) and a word-synced karaoke caption band at y=1180 (61-77% of height, clear of the Shorts UI). The caption band is ONE alpha qtrle .mov built with the concat demuxer over per-word stills, overlaid in a single ffmpeg pass, with each still held to the NEXT word's onset (using a word's own spoken duration made the track finish 12s before the voice). Font chosen per string from the font's cmap so maths glyphs (pi, superscript 2) can never render tofu. `build_video.build()` gained `title`/`tag`; `daily_math.py` passes the title as the headline. Captions/headline are best-effort: any failure falls back to the old plain mux. | `test_captions.py` on the real PythagoreanTriples narration -> `109/110 words word-synced`, 26 bands, caption track 44.57s vs narration 45.5s. `build_video.assemble()` on a real scene -> `1080x1920`, 45.8s, `verify_video` OK (aac 48000Hz 2ch, moov at byte 36); headline band present on every sampled frame (11.8% ink), caption band changes between t=25 and t=40 (mean abs diff 20.0); vision read-back confirms the amber active word is inside the caption sentence ("carved a table **of** them") and pi/r-squared render as real glyphs. Lessons in the `faceless-youtube` skill + PLAYBOOK.md. |

| 2026-10-16 (1st) | (f) novel formats + channel structure | **ALGORHYTHM had no Shorts line at all** (4 uploads, 0 views, 0 subs — every one of them 8-12 min long-form, the one format a cold channel can never be discovered with). New `cs-videos/run_cs_shorts.py`: a CS-flavoured concept prompt (Google Trends US/DE + YouTube trending Education/Science&Tech + the next curriculum-roadmap entries, with a rule that prefers a DIRECT technical trend over a celebrity one) feeds `trend-radar/build_concept.build()` — the animated concept-card renderer — so a CS short inherits the motion engine, karaoke captions, loop bumper, palette/motion rotation and the -14 LUFS mix. Own `cs_shorts_used.json` + `cs_short_style.json` so DOPEAK's counters stay untouched; `verify_video` + `motion_gate` before publish; a failed build notifies instead of dying silently. **Second, bigger fix: a WRONG-CHANNEL publish.** The first live run reported `[uploaded]` and landed on DOPEAK, because `trend_scout.py` executes `sys.path.insert(0, ".../faceless-youtube")` at module level and stole the import race for `yt_publish`/`yt_uploader`. `run_cs_shorts.py` now binds its own modules by ABSOLUTE PATH through `importlib.util.spec_from_file_location` (registering them in `sys.modules` before `exec_module`), passes the bound module object into shared helpers, and asserts `list_channels()[0]["id"] == EXPECTED_CHANNEL` before spending a render. Also: `cs-videos/yt_publish.py` was shipping DOPEAK's finance tag pool on every CS upload. **Reach lever:** new `faceless-youtube/localize.py` + a best-effort call in both `yt_publish.publish()` copies writes the German title/description to every new upload (`videos.update?part=localizations` — one video competing in a second feed, no second render; needs `snippet.defaultLanguage` first and lags on read-back). Skill split: the long-form section moved to `references/longform-finance.md`, new `references/multi-channel-and-reach.md`. | `run_cs_shorts.py 1 --no-generate --index 0` → `[channel] ALGORHYTHM (UCyjhiQ4Tr_M_qn42B0Vdp3A) OK`, `3 ways data centers survive Japan earthquakes` 21.5s / 24.7MB, `OK: aac 48000Hz 2ch, moov at byte 36`, `MOTION_OK: median 12.22`, 75/75 word marks word-synced, uploaded → https://youtube.com/shorts/yLcHI0_HPNQ ; `oembed` author = ALGORHYTHM, `curl /shorts/<id>` → 200 (it IS a Short). German localisation read back: `3 Wege, wie Rechenzentren japanische Erdbeben überstehen`. **Thumbnail was refused with HTTP 403 "doesn't have permissions to upload and set custom video thumbnails" — that is channel phone-verification on ALGORHYTHM (a different channel from the verified DOPEAK), an owner action, NOT a scope problem; the upload still succeeded.** The wrong-channel incident is proved by `oembed author_name = DOPEAK` on the first run's id (`tum35fpuVlA`) and by `find_spec` resolving `yt_publish` to faceless-youtube once `trend_scout` was imported. `localize.apply_de` verified on 3 real videos: `Der Satz des Pythagoras visuell erklärt` (first call wrote + title-matched read-back, second call idempotent), `Warum die Fläche eines Kreises πr² ist`, `Pythagoräische Tripel`. |

| 2026-10-16 (2nd) | (e) monetization + (d) visual pacing (finishing the run killed at 10:36) | **A frozen maths line, found by measuring live output.** The two maths Shorts the 15:43 cron published (`E8qNCebzPI8`, `wWcxjRRqSNk`) measure `MOTION_STATIC: median 2.15 | min 1.38 | content 2.92` with `bg 3.14` — the animated plate was moving everywhere EXCEPT the middle third, because `assemble()` composites the opaque Manim card over it. Fix in `math-videos/build_video.py` + `motion.py`: the plate's own low-frequency layers (blobs/dots/sweep) are re-composited OVER the content card before the headline/caption are drawn (`TUNE ovl_blob/dots/sweep`, distinct labels b0a/b0b/b0c); `MATH_MOTION_BOOST` scales them for a one-shot retry. **The maths line now GATES before upload** (`daily_math.motion_status()` + one boost-and-retry, weak result reported to the group); `trend-radar/build_concept.py` (every trend + CS short) now refuses to publish below the floor, beside its `verify_video` gate. **Money lens:** new `faceless-youtube/watch_hour_stream.py` — a 24/7 live "study stream" of the channel's OWN renders (the only machine here that can fill the 4,000-hour gate Shorts contribute ZERO hours to). Measured: live watch hours count ONLY if the stream is archived as a public VOD, and a bare 3-file loop is the reused-content shape → curation + a live-only layer + a new render weekly. Lessons in the `faceless-youtube` skill. | Fast 12 s A/B harness (truncated narration + symlinked cached plate) reproduced the PUBLISHED video's numbers exactly (2.15/1.38/2.92/7.85) — so the fix was scored in ~40 s: over-layers ON -> `MOTION_OK median 5.21 | min 2.30 | content 4.50`, boost x1.9 -> 7.29. Full-length real re-mux (49.0 s, 48.9 MB) -> `MOTION_OK median 5.21` + `verify_video: OK aac 48000Hz 2ch, moov at byte 36`. `daily_math.motion_status()` on the live artefact returns `(False, MOTION_STATIC …)` and `True` on the fixed render. Frame read-back: content + karaoke + headline all legible, no washout. Stream engine: `--check` = 19 clips/11.9 min (DOPEAK), 7 clips/38.9 min (ALGORHYTHM); `--to-file 20` -> h264 1080x1920 + aac 48000Hz 2ch in **21.2 s wall with `-re`** (~1.05 cores); frame read-back shows LIVE, brand, `16:08:36 UTC`, moving bar, top hook unobstructed. Entry points: `ast.parse` on all 5 changed files, `daily_math` import + gate, `build_concept.py --help`, `run_cs_shorts.py` import, plus the trend short published at 16:04 gates `MOTION_OK 5.86`.

| 2026-10-16 (3rd) | (b) packaging/first-frame + (a) retention/hooks | **Frame 1 of every trend/CS short was an EMPTY background — no text at all.** It is the Shorts cover AND (because the loop bumper is a still of it) the frame the video ends on. Root cause: every layer in `anim_frame` starts at alpha 0 and fades in over 0.4-0.5 s, and a full-frame accent flash is painted over the first 0.16 s. `build_concept.build()` now sets `instant_open` on the first segment (title/steps/card/caption band at full alpha from t=0, no slide-in; the opening punch moves to a 3.5% camera pull-out that provably cannot crop the card's 60 px inner margin) and `instant_open`/`open_flash=False` together. **Second, independent defect: the loop bumper was encoded by a different ffmpeg path**, so it was tagged limited-range (yuv420p) while every JPEG-sequence segment is full-range (yuvj420p / color_range=pc); the concat stamps the file with the FIRST stream's tag, so the bumper was read as full-range and expanded +11-13 luma and the seam failed. The still is now written as `loop_frames/f_0000.jpg` and encoded by the identical command. New `trend-radar/frame_gate.py` (COVER / HOOK / LOOP, one ffmpeg pass; called from `build()`, non-fatal, one loud line) — a luma-only check passes a blank cover, so the cover test is INK-based. **Niche lens:** `trend_scout.niche_report()` + prompt/schema now demand a `mechanism` (<=6 words) and `timeless: true` on >=1 concept per batch, with one bounded re-prompt; entity vocabulary = capitalised MID-string words in today's Trends + trending titles, minus stop-words/science terms. Skill updated (3 new rules). | Before/after on real renders of the same concept: published shorts measured `COVER_FLASH` cover ink **0.58%** vs settled **7.24%** (luma 65.4 vs 48.0) and the bumper path measured `LOOP_BROKEN 36.7-41.4%` pixels differing; after the fix `COVER_OK` frame1 luma 45.26 **ink 6.21%** vs settled 45.09 / 6.03%, `HOOK_OK 6.69` (floor 3.0), `LOOP_OK 0.21%`, `verify_video: OK aac 48000Hz 2ch moov@36 motion 38.46%`. Isolated encode test: the new loop path gives identical tags (`yuvj420p / pc / bt470bg`) and frame 0 == `v_00` frame 0 at 0.41% diff. Niche gate: `NICHE_GATE_TEST_OK` (published batch `ok=False` 0/5 declared, Disney concept flagged `entities=['disney','halloween']`, maths title not flagged) and a live `trend_scout.py 3` run printed `[niche] 37 entity words ... declared timeless 1/3 | mechanism 3/3 | reported timeless 2/3` (concepts file restored, rotation state untouched, test renders deleted). |

| 2026-10-17 (1st) | (c) audio/voice/music | **Every channel was shipping a music bed that was not there.** Measured the real published files (20 ms frame RMS: p90 = spoken level, p10 = gap/bed level) and found the bed **43 dB under the voice** on the DOPEAK trend/CS shorts (bed-only tail -51.8 dBFS vs speech -13.2) with **17.7-19.3 % of frames >30 dB under the speech**, 29.9 dB under on the maths shorts, and **53.5 dB under with 21.8 % dead air on the ALGORHYTHM long-form** — because the level was two hand-written gains multiplied together (0.12 built x 0.20 mixed = 0.024) and NOTHING ever measured the result against the narration. The research band is 14-20 dB (below that it is a dropout, not a bed; a dropout at the loop point is what tells a viewer the video ended). New `audio_mix.py` (canonical in `math-videos/`, byte-identical copies in `cs-videos/` + `faceless-youtube/`, imported locally — never via a cross-project `sys.path` insert, which is how a wrong-channel module gets picked): `mix_audio()` measures BOTH stems at build time (`speech_db` = p90 of the narration, `bed_db` = median of the bed), applies the gain that puts the bed `TARGET_UNDER_DB=16` under the spoken level, and ducks it with `sidechaincompress=threshold=0.05:ratio=3:attack=20:release=400` (~5 dB, no pumping). Wired into `trend-radar/build_concept.py`, `math-videos/build_video.assemble` and both `pipeline_v3.assemble_final` copies. New gate `audio_gate.py`: one decode of the FINISHED file prints `AUDIO_OK` / `BED_TOO_QUIET` / `BED_TOO_LOUD` / `DEAD_AIR` / `LOUDNESS_OFF`; called from `build_concept.build()` beside `frame_gate` and by `daily_math.audio_status()` BEFORE the upload (a weak result now warns in the Telegram report). Two ffmpeg traps cost a debug cycle each and are in the skill: **`sidechaincompress` ends at the SHORTER of its inputs** (the ducked bed stopped with the voice and `-shortest` then cut the 0.75 s loop bumper off — `frame_gate LOOP_BROKEN 47.8 %`; pad the key with `apad=whole_dur=<bed+0.5>`), and **a label consumed twice in one graph where one consumer is a sidechain kills the whole graph** with the misleading `Stream specifier 'n' ... matches no streams` (the build's own `except` then silently degraded to a narration-only mux) — use `asplit=2`. | Real renders, before → after. Trend/CS: `BED_TOO_QUIET ... voice_over_bed 42.6-43.3 dB, dead_air 0.177-0.193` → rebuilt `3 numbers behind Disney's Halloween McDonald's buckets` → `AUDIO_OK voice_over_bed 18.3 dB, dead_air 0.003, -14.5 LUFS`, 22.77 s (bumper intact: `frame_gate loop OK 0.24%`, cover OK 7.03 % ink, hook OK 6.56, motion 37.97 %). Maths: published `DerivativeSlope_final` 29.9 dB / 0.083 → real `assemble()` on the same stems + a fresh bed → `AUDIO_OK 15.2 dB, dead_air 0.004, -14.5 LUFS`, 49.03 s, bed gain auto-computed 7.70. ALGORHYTHM long-form: published `What an operating system does...` 53.5 dB / 0.218 → real `assemble_final` on the two cached scenes + shipped bed → `AUDIO_OK 15.9 dB, dead_air 0.001, -14.1 LUFS`, gain 11.43. Entry points: `ast.parse` on all 7 changed files, `import daily_math` + `sys.argv=['x','2']`, `run_cs_daily`, `run_daily`, `run_longform_daily`, `longform_pipeline` + `audio_mix` import, `daily_math.audio_status()` returns `False` on the old live file and `True` on the fixed render. Test renders deleted, `used.json` untouched (8 entries). |

| 2026-10-17 (2nd) | (a) retention/hooks — the LOOP as a format | **The closing frame told the viewer to leave.** The payoff card's band printed `DOPEAK - follow for one idea a day` — a soft invite, burned into the last content frame and onto the card a rewatch lands on (the loop bumper is a still of frame 1). Research is explicit: the final second decides whether the replay happens, an outro CTA/leave-invite spends it on a frame with no content, and the CTA belongs in the caption/description. `build_concept.py`: `LOOP_CUES` + `loop_cue()` — the band now carries the concept's own `mechanism` with a replay cue, rotated over 3 phrasings by palette seed; the CTA moved to the upload description. **New format:** `--loop` renders the loop-native ultra-short (the trend line's daily mix is now 1 x ~12-15 s loop short + 2 x <=32 s listicles — same 3 uploads/day, so the fresh channel's daily quota is untouched). **A prompt rule for a format is worth 0:** the batch prompt asked for one loop concept and the live batch came back as five 55-70-word listicles (circularity 0.00-0.20) whose shortest was then trimmed to fit — deleting the sentence that explains the mechanism. `trend_scout.request_loop_concept()` makes a SEPARATE bounded request (3 attempts) validated on word count AND `circularity()` AND `max_repeats()`; if none passes it keeps the BEST attempt flagged `loop_weak` rather than falling back to a trimmed listicle. Two further bugs found on real renders: `trim_narration` popped index 0 of a 2-sentence script — **it deleted the HOOK** and the short opened mid-explanation ("By toggling each segment..." with no number) → trims from the MIDDLE now; and `trend_scout._ask` crashed on a reply that was a list of STRINGS (`'str' object does not support item assignment`), which silently disabled the shape-rotation retry. New tests `test_loop_gate.py` (14 checks) + 4 loop-cue checks in `test_layout.py`; skill: `references/loop-retention.md`. | `test_layout.py` → **LAYOUT_OK (35 checks)**, `test_loop_gate.py` → **LOOP_GATE_OK (14)**, `test_pacing.py` → PACING_OK, `test_audio.py` → AUDIO_OK, all 11 trend-radar modules `ast.parse` clean. Real render `build_concept.py --concepts concepts-2026-10-17.json --loop --no-record` → 12.0 s, `[loop] DURATION 12.0s — in band (5-15s)`, `cover OK ink 4.50% vs 4.40% \| hook OK 6.55 \| loop OK 0.30%`, `AUDIO_OK 17.3 dB bed / 0.5% dead air / -14.4 LUFS`, `verify_video OK aac 48000Hz 2ch moov@36 motion 39.89% 1080x1920`. Budget calibrated on the MEASURED pace: 42 words spoke for 16.4 s (2.56 w/s, not the assumed 2.6) → 17.1 s out of band, so `LOOP_MAX_WORDS` 42 → 38. Vision read-back of the payoff frame: band reads `» it loops - Light three segments` in the accent colour, **no tofu**, and **no follow/subscribe CTA anywhere on the frame**. State files untouched (`used.json` 8 entries, `concept_palette.json` last=3) — a `--no-record` render burns no palette and no quota. |
| 2026-10-17 (2nd, extra) | (a) content integrity | The loop prompt's callback requirement pushed the model into **padding and invention**: the first accepted loop script used "vanish" 3x in 28 words and claimed "only 5 primes below 20" (there are 8). The loop gate now also rejects a script where any content word appears more than twice, and the prompt bans invented statistics. The same accuracy rule went into the BATCH prompt (rule 2b) because today's batch carried 4 invented percentages in 4 titles ("99% seamless", "cut odds by 99%", "over 90% capacity", "70% traffic") — an unsupported number is the one error a viewer can check and the fastest route to a report on a 3-subscriber channel. |

| 2026-10-17 (3rd) | (b) packaging / metadata + (e) algorithm match | **A retired niche's tag pool was on every upload.** Measured on the live feed: **17 of the last 25 DOPEAK uploads** carried the FINANCE pool ("investing for beginners", "index funds", "build wealth") — including "What Makes a Superhabitable Planet?" and "How Fast Do Colliding Objects Lose Energy?" — because `trend-radar/build_concept.py` imported `yt_publish` out of `faceless-youtube/` and the pool there was a module-level finance default, so maths/science shorts were tested against a finance audience. Fixed: named `POOLS` (`maths`/`finance`/`cs`), DOPEAK's default = maths, `base_tags=` argument + `YT_BASE_TAGS` env override, the trend line states its own pool explicitly, and the paused finance callers now pass `POOLS["finance"]` so re-enabling them stays correct. **Second: the description.** It shipped `narration[:400]` (truncated MID-SENTENCE, payoff deleted) plus up to EIGHT hashtags; `build_concept.upload_description()` now leads with the concept's own `payoff` (the first ~25 words are what a search surface reads), carries the full narration, the mechanism in one line, and exactly 3-5 hashtags broad→specific→brand with `_hashtag_ok` rejecting `#viral/#fyp/trending`, bare years and scaffolding tags in CODE. **Third: session time.** New `yt_publish.related_line()` appends "Watch next: <title> → <url>" for the closest video on THIS token's channel (reusing `live_titles()`, cached weekly in `related_pool.json`), and returns "" rather than forcing an unrelated link. **Fourth (built, awaiting Ahmad):** `faceless-youtube/fix_live_tags.py` re-tags the already-published mislabelled videos — dry-run by default, classifies each video's real subject from its title so the genuine finance long-forms are NOT relabelled into maths. | Live measurement before the fix (`/tmp/before.py`): `=> 17 of the 25 most recent uploads were mislabelled to the finance audience`. Dry-run of the actual publish path (upload intercepted, real file through `verify_video`): `TAGS SENT (20)` with `finance leaks: []` on the same concepts that leaked 11 finance tags live, `cats 27`; description 98 words, final sentence complete, 5 hashtags. Cross-link proof: concept "2 rules that cut Mega Millions odds by 99%" → `Watch next: 3 ways Powerball odds surprise you → https://youtu.be/5ysndP_ZoL0`, while the unrelated Verizon concept correctly got NO link. Real end-to-end render `build_concept.py --index 3 --max-seconds 32 --no-record` → 19.6s, `motion 40.26%`, `cover OK 6.19% ink`, `hook OK 6.92`, `loop OK 0.30%`, `AUDIO_OK 17.8 dB / -14.5 LUFS`. `fix_live_tags.py` dry run: `=> 9 of 25 need a change`, the IPO/Dollar-Cost/Inflation long-forms detected as finance and left alone. Entry points: `ast.parse` on all 6 changed files, `build_concept.py --help`, `import run_daily`, `run_longform_daily`, `trend_scout`, `run_cs_daily`, `yt_publish` (cs) all OK. Test render + dir deleted, `used.json` 11 entries and `concept_palette.json` untouched. Skill: SKILL.md was at 100,960/100,000 chars, so `references/topical-images.md`, `references/publishing-projects.md` and the new `references/metadata-packaging.md` now hold the depth and SKILL.md is 97,771 chars with 3 pointers (~2.2k chars of headroom back). |

| 2026-10-17 (4th) | (d) rebuild integrity — the STATIC backlog, and same-title duplicates | Ran the upgrade agent end-to-end. **ALGORHYTHM needed nothing** (all 12 live videos measure 5.24-8.79 % motion). **DOPEAK's 4 remaining static long-forms were rebuilt and replaced** (`fd5qMT48dKk`, `o31GLaacmuY`, `hexKBY88gAE`, `patIhtPVm9s` — all measured 0.00 % live, i.e. built before the camera-motion engine). Three same-title duplicates were removed under the standing approval (`ZuArG7SRHZQ` 10 s static copy of "What Is π, Really?" — its 46 s copy measures 18.68 %; `KnnTNBwo7gY` 52 s AND `PbWfvE6izWk` 17 s, BOTH static copies of "Why the Area of a Circle is πr²" — the first was rebuilt and re-published as `H7rC4dxacsM`, then both old copies deleted) and one more maths Short that was still static (`b13M7FAwGE8`, Pythagorean Triples, 0.00 %) rebuilt → `panIJ9ia7CQ`. **Every live video on both channels now passes the motion gate**: DOPEAK long-form 15.13-28.38 %, DOPEAK maths 16.32 / 21.19 / 22.83 / 18.68 %, ALGORHYTHM 5.24-8.79 %. Two latent bugs fixed: `upgrade_longform_motion.py --limit` was a **no-op** (`done` was never incremented, so `--limit 1` rebuilt all four); and the live-title guard names only ONE duplicate when a title is live twice, so a caller passing the other id gets a false refusal — `math-videos/upgrade_topic.py` (new) parses the guard's own `replace_of='…'` hint and retries. Also `cs-videos/_live_motion.py` matched only `*.mp4` while yt-dlp writes `*.webm`, so it printed "DOWNLOAD FAILED" for files it had in hand. | 6 rebuilds: local gates `OK aac 48000Hz 2ch moov@36, motion 20.34 / 29.48 / 18.63 / 23.02 %, 1920x1080` + `AUDIO_OK 15.3-15.7 dB bed, 0.0 % dead air, -14.1/-14.2 LUFS`; maths gates `MOTION_OK median 4.21 / 3.97` + `AUDIO_OK 15.3 / 16.0 dB`. **LIVE** re-measurement of every published file (yt-dlp section + `verify_video.motion_score`): long-forms 17.59 / 18.81 / 15.13 / 28.38 %, maths 27.21 / 22.83 %, and the 8 superseded ids re-queried after each delete → GONE (`fd5qMT48dKk`, `o31GLaacmuY`, `hexKBY88gAE`, `patIhtPVm9s`, `ZuArG7SRHZQ`, `KnnTNBwo7gY`, `PbWfvE6izWk`, `b13M7FAwGE8`); DOPEAK upload count 60 → 57 with no duplicate title left among OUR uploads (the `untitled`/`unknown`/emoji-title clusters are Ahmad's own pre-pipeline uploads — never touched). `pending_deletions.json` pruned on both channels: every entry re-queried, 0 still live. Thumbnails on the new uploads were skipped with HTTP **429** (per-account thumbnail quota spent; the backfill drains few-per-day) — not a verification problem. |

Next run suggestion (after the loop run): the loop short now renders, is gated, and is in the daily mix — but the length-band table added to `channel_report.py` (see below) is the FIRST evidence the bet works, so the next run should act on the numbers rather than on theory: the 5-15 s band measured **0.59 views/hour mean (4 videos, 516 views)** against 0.03 for the 16-32 s band the line used to publish and 0.12 for the 33-60 s maths shorts — i.e. the loop band is ~20x the old default, and the 33-60 s maths line is second. Second, a QUOTA problem to settle with Ahmad: DOPEAK published 3 rebuilt long-forms at 06:46 today, and the 13:00 maths (2) + 15:00 premium-rebuild resume + 16:00 trend (3) jobs still share a fresh channel's cap of ~4-5/day, so the loop short can lose its slot to a 0-view long-form. The `Premium Rebuild Resume` job (`96ebf4aef1c4`) is the one to pause — long-form is paused by his own decision. Third, packaging: the batch is still entity-heavy (today 4 of 5 concepts ride iPhone/Zverev/NYT/Mega Millions) and the trend line has no cross-batch taste check — a `timeless:true` requirement exists but the re-prompt gave up. Next lens: (e) money formats (the low-tier fan-funding door is 500 subs + 3 uploads/90d, which is reachable) or (b) packaging.

Next run suggestion (audio run, previous): the audio line is gated, so the next lever is the one thing nothing can currently prove — **retention**. The YouTube Analytics API is NOT enabled on the project: `curl https://www.googleapis.com/youtube/analytics/v2/reports?...` returns HTML **404** even with a bogus key, while the same host answers `youtube/v3/channels` with JSON **403** (the control). One console toggle (Google Cloud → the OAuth project → enable "YouTube Analytics API") plus a re-consent for the `yt-analytics.readonly` scope would unlock `averageViewPercentage` / `averageViewDuration` per video — i.e. whether a short is actually watched and rewatched, which is the only feedback loop that can rank the packaging, pacing and audio changes. Ahmad's action; ask him with the exact click path. Next lens in the rotation: (a) retention/hooks, or (e) money formats — and the researched length finding worth prototyping: viral Shorts are BIMODAL (13-15 s for loops, >100 % retention, vs 50-60 s for total watch time) while the trend line currently sits in the middle at 22-32 s; DOPEAK's only video above 10 views is a **13-second** short.

Next run suggestion (previous): lens (b) packaging — the two live maths Shorts are still the OLD weak-motion files (a rebuilt-and-replace, which needs Ahmad's go-ahead for the deletes); the trend/CS shorts published BEFORE today carry the blank cover + washed tail, so 3-5 of them are worth rebuilding too (again: his call).

Openings left: (1) DONE — the maths line moves and is gated; (2) the CS long-form shorts still burn SENTENCE-level captions through `longform_pipeline._loop_and_caption` — no karaoke, no counter, no recap card; (3) nothing measures whether a published short was actually rewatched loop-wise (a per-video viewed%/rewatch read where the API offers it); (4) OWNER DECISIONS PENDING: the live-stream key + VOD-archive toggle (the watch-hour engine is built and verified, waiting on two owner actions); ALGORHYTHM publishes 3 x 8-12 min long-form/day to 0 viewers — recommend reallocating to its shorts line; and the CS short that landed on DOPEAK (id `tum35fpuVlA`) needs Ahmad's call.

| 2026-10-20 (1st) | (d) visual style — ANIME-PHYSICS format (weakest of the three) | **Silhouette anatomy rebuild + the format's missing motion engine.** `anime_physics.katana_figure_v3()` (v2 kept behind `ANIME_FIG=v2`): tapered-quad limbs (`taper()`) instead of equal-width strokes, a DIAGONAL shoulder line + deltoid caps (the horizontal yoke read as "an architectural ledge"), taper chains for bicep/forearm mass, both knees flexed with the front knee stacked ahead of the ankle, boot wedges with toe/heel, a neck column longer than the head is deep, and a fist wider than the wrist (2.3x) so the hilt no longer "grows out of the arm". Blade widened 0.095→0.118 units + two glow passes (17 px @0.13, 8 px @0.34) because at thumbnail size the weapon — the subject of the question — was a hairline. Thin interior "rim light" strokes were measured as *glitches* and default OFF (`ANIME_RIM=1` to A/B). **Second: the format failed the motion gate outright** — `motion_gate median 0.16` on an animated scene, because `self.play` beats are small-area moves and the gate samples ADJACENT frame pairs. `polish_short.py` now composites the channel's own `motion.build_assets` stack (blobs/dots/sweep + the coarse grain plate from `build_video.assemble`) with `POLISH_MG`; `2.4 → MOTION_OK 3.90`. **Third: loop seam** — caption tail holds the FIRST caption for 0.7 s and every periodic layer is locked to whole cycles in the clip duration: LOOP 18.9 → 15.4 → **5.2 %** (residual = per-frame random grain; blur test proves content matches 2.68 vs 2.30 reference). Also: `polish_short.narrate` got the 5-attempt edge-tts retry the skill requires, and the payoff hold went 1.6→3.0 s so the gauge can be read (and the clip clears the 8 s floor under which `verify_video.motion_score` refuses to measure). | Vision A/B on a 1:1 crop, side-by-side: figure anatomy **3/10 → 8/10**; cover frame **5/10 → 7.5/10**; payoff frame 9/10 ("20 m/s, the 20 mark and the cheetah comparison all readable"). Gates on the finished `out/katana_v3_short.mp4` (10.4 s): `verify_video OK aac 48000Hz 2ch, moov@36, motion 20.69 %, 1080x1920`; `motion_gate MOTION_OK median 3.90 min 3.23`; `frame_gate COVER_OK ink 7.74 % (settled 7.76), HOOK_OK 3.44, LOOP 5.20 %`; `AUDIO_OK 16.7 dB bed, dead air 1.9 %, -14.2 LUFS`. Pixel proof that the "clipped headline" both reads reported was imaginary: hook ink bbox x 73-918 in BOTH builds, zero ink in the last 14 columns. Lessons in `references/anime-physics-short.md` + a pointer in SKILL.md.

## 2026-10-20 — repetition guardian: the count-promise axis + architecture rotation

- Measured on the LIVE feed: 11 of the newest 20 DOPEAK titles promise a count and 4 of the newest
  5 do; every concept generated 15-19 Oct did (5/5 per day). Shape families split them into
  'what'/'question'/'how', and `hook_numbers` ignores a leading count, so no gate saw it.
- 16 of 20 concepts across 17-20 Oct were ONE skeleton: small-number promise -> N parallel items ->
  payoff recapping them ((3,3) x13, (2,2) x8 over 32 concepts). The prompt itself mandated it.
- Fixes: `shape_guard.count_promise/promise_budget` + a batch gate + an audit; new
  `trend-radar/arch_guard.py` rotating five architectures (list/chain/flip/threshold/single),
  classified in code, mandated per slot in the prompt, gated in `trend_scout.generate`, recorded at
  publish in `build_concept.mark_used`, preferred at pick time (`ARCH_PICK`). `count` is no longer
  an assignable shape family (it collided with the non-count architectures).
- Palette rotation is REAL: the newest six uploads show four distinct accent hues (pink, orange,
  cyan, blue) and no two adjacent frames share a luma layout — the repetition was content, not look.
- A dry run of `trend_scout.generate()` overwrote `concepts-2026-10-20.json`; the narration was
  rebuilt from `out/<slug>/caps.json`, steps were lost. `TREND_DRY=1` now redirects the write.

## 2026-10-22 (4th run) — (d) visual style: the motion engine was painting a RECTANGLE on the picture

Format worked: **Manim maths explainer** (`math-videos/discriminant_cover.py`, the strongest of the
three). Score before → after on the finished 25.4 s short: **7.0 → 8.3 / 10** (same frame position,
same prompt, five independent reads; sub-scores depth 7.4→8.1, icon 5.0-6.8→7.8, accent 8.5→8.7,
composition 8.1→8.2). Deliverable `math-videos/out/discriminant_v8_short.mp4`.

- **The defect nobody had ever measured:** `motion.build_assets` drew the over-content light sweep
  as a POLYGON that ran off its own canvas (vertices at `-0.30*sw` and `0`), so alpha was FULL (40)
  exactly at x=0 with a hard cut, blurred only 30 px over a 680 px canvas. Composited as a moving
  overlay it painted a lighter RECTANGLE with abrupt borders at x=341/837 the full height of the
  frame — through the headline and the formula. A vision read of the *published* `v2` called it
  "a compositing artifact", depth 7/10. Every polished short on every format inherits that asset.
- Fix: the band is a **cos² window** (alpha 0 at 8 % and 92 % of the canvas, peak 54) — no column of
  the asset can carry a step. New `TUNE["sweep_shape"]=2` because `build_assets` keys its cache on
  TUNE, so a code-only change would be served the OLD hard-edged PNG (partial-movie-cache trap, one
  level down). Measured on the published file vs the rebuild: strongest column step in the
  background rows **14.1 → 1.1** (max 17.8 → 4.1), `columns with step >= 6: 1 → 0`; a stacked A/B
  crop read back "hard-edged rectangular panel = compositing artifact (A) / smooth light gradient (B)".
- Three further layout faults came out of the same frame reads and were fixed in the same pass:
  a **graph plate** + axes at 8.4:1 (they were the faintest ink in the frame at 3.1:1 and the plot
  floated on the starfield), **icon weight** (0.34→0.40 u wide with depth scaled, 4.2→5.4 px strokes,
  dots +25 %) because a 270 px read sees the glyph at ~20 px, and **one grid width** `GRID_W=3.90 u`
  for both plates + the answer row inside it (the formula plate ended 41 px from the frame edge,
  i.e. under the Shorts action rail).
- Gates on `out/discriminant_v8_short.mp4`: `MOTION_OK median 5.79 min 2.07`, `verify_video OK aac
  48000Hz 2ch moov@36 motion 25.95 % 1080x1920`, `frame_gate COVER_OK ink 7.80 % / HOOK_OK 4.71 /
  LOOP_OK 0.67 %`. `POLISH_MG=1.6` was required: at the default 1.0 the same build measured
  `NOT SHIPPABLE min 1.10` even though the median passed — the seam's removal took away a chunk of
  the weakest pair's changed pixels.
- **Captions must be budgeted per BEAT, not per video.** The first rebuild reused a 7-sentence
  narration against a 6-beat scene and the finished file read Δ=−6 + "no roots" while the burned
  caption still said "one repeated root" (a frame read scored it 4/10 for an editorial mismatch).
  Re-cut to 6 sentences whose WORD SHARES match the beat shares (±3 %): every sampled beat then
  agreed — Δ=−6 / "no roots" tile / "No crossing at all" on one frame.
- Not published: the live discriminant short is a replacement, which is Ahmad's call.


## 2026-10-23 (1st run) — (d) visual style: the caption and the case on screen disagreed

Format worked: **Manim maths explainer** (`math-videos/discriminant_cover.py`).
Deliverable `math-videos/out/discriminant_v13_short.mp4` (14.7 s, 1080x1920).
One measurable change, chosen after measuring the file the previous run left behind.

- **The defect (measured on `out/discriminant_v8_short.mp4`, t=8.00 s):** the frame showed
  `Δ = 0` with the "two roots" tile lit while the burned caption read "…the axis twice, so two
  real roots". A vision read of that frame: **4/10 — "three competing signals"**. Two independent
  causes: (1) `polish_short` fits picture to voice with ONE uniform `setpts=PTS*k` (18.2 s clip
  against a 25.4 s read = k **1.39**, i.e. the whole scene in slow motion with its beats landing
  wherever the ratio puts them) and the previous run's word-SHARE matching (shares ±3 %) is not a
  timing; (2) the 4-word caption chunker merged the tail of one sentence onto the head of the next
  ("axis. Negative") because it only counted words.
- **Fix A — beat-locked narration.** New `math-videos/speak_beats.py` speaks the script sentence by
  sentence and writes the MEASURED length of each (`disc_beats.json`); `discriminant_cover.py` reads
  that plan (`_beat_plan()`) and sizes its own plays to it, so beat i IS sentence i and
  `polish_short.py <clip> <out> <title> "<script>" disc_beats.json` runs at **k = 1.00** (no
  stretch). Measured: clip 14.68 s vs voice 14.69 s, drift **−0.00 s**. Bonus: total went
  25.4 s → **14.7 s**, i.e. into the 5-15 s band that measured 0.59 views/hour vs 0.03 for 16-32 s.
- **Fix B — caption integrity.** `caption_beats(..., breaks=)` never merges across a sentence and
  splits a sentence into EVEN chunks (3+2, 3+3, 4+3) so no one-word tail like "reaches it" is left
  stranded from its negation; the hook beat is left BLANK because the hook is already the on-screen
  headline (it was printing "How many answers" under "how many / answers?" — a cover read called it
  "dead weight that repeats the top headline").
- **Fix C — value and tile move together.** Sequencing `activate(2)` before the curve lifted left a
  ~2 s window of "no roots" lit under `Δ = 0`; a frame read at t=9.33 scored it **"mathematically
  incorrect … it teaches the wrong rule"**. Beat 2/3 now animate `D` and the tile in the SAME play.
- **Fix D — the cover stopped answering its own question.** Root markers were drawn from t=0; they
  now appear on the spoken word ("crosses twice") and are retracted before the closing beat, so the
  loop bumper still lands on frame 1 (`LOOP_OK 0.98 %`).
- **New gate `math-videos/check_beat_sync.py <video> <plan>`** — recomputes the chunk list from the
  plan and asserts the caption at `beat_start + 0.55` is the START of that beat's sentence.
  `BEAT_SYNC_OK` on all 5 beats (beat 0 = blank by design). Re-runnable after any polish change.
- Gates on `out/discriminant_v13_short.mp4`: `MOTION_OK median 6.44 min 2.09`, `verify_video OK aac
  48000Hz 2ch moov@36 motion 33.62 % 1080x1920`, `frame_gate COVER_OK ink 5.86 / HOOK_OK 6.51 /
  LOOP_OK 0.98 %`, `AUDIO_OK 20.9 dB bed, 1.2 % dead air, −14.0 LUFS`, `BEAT_SYNC_OK`.
- Scores (same prompt, 480 px reads): negative beat **4/10 → 7/10** and its state now reads
  consistent (`Δ = −6` + curve clear of the axis + "no roots" lit); cover **5.5 → 6.0**.
- **Next gap, named by both reads and NOT fixable by tuning:** the cover still pre-answers itself —
  the parabola visibly crosses twice under a hook that asks "how many answers?", so the three tiles
  look redundant. The fix is conceptual (start the graph at one crossing, or hide the tile labels
  until each case lands), not a polish pass.
- Not published: replacing the live discriminant short is Ahmad's call.


## 2026-10-26 (1st run) — (b) visual style / timing: the notes page answered its own question early

Format worked: **Aesthetic study notes** (`math-videos/aesthetic_notes.py`).
Deliverable `math-videos/out/notes_v9_short.mp4` (32.4 s incl. 0.75 s bumper, 1080x1920).

- **The defect, measured on the shipped `notes_v7_short.mp4`:** the page was still
  stretched onto its voice (`scale = audio_dur / sum(BEATS)` = **x1.37**), so the worked
  example opened at **~23.0 s** while the narrator did not reach "forty nine" until
  **~25.1 s** — the card printed b²−4ac = 25+24 = 49 and "two answers" while the voice
  was still reading the question out. Every gate passed; none of them can see a clock.
- **Fix:** `SENTENCES` (one per beat) → `speak_beats.py notes_beats.json` → frame i is
  held for the MEASURED length of sentence i (k = 1.00), the example beat is split into
  setup (6) and answer (7), and `WORD_ANCHOR = {7: "forty"}` pulls that one boundary onto
  the spoken word (25.75 s → 26.84 s). Verified in the finished file: the answer ink
  turns over between 26.60 s and 26.95 s, word at 26.839 s.
- **Score before → after, same question, same timestamp (t = 23.5 s, voice mid-question):
  5/10 → 10/10** picture/voice agreement ("Panel A … spoils the answer before it is
  spoken"; "Panel B … matching the spoken question precisely").
- **Second, smaller change on the same build — the payoff card now ends on the ANSWER:**
  roots 46 → **92 ink px** in the brand green, question equation 72 → 66, card 306 → 336 px,
  "two answers" badge right-aligned on the answer row (A/B on one image: beside the roots
  **8.2** vs right-aligned **8.8**). Full-frame payoff read **7.5 → 8.5/10**.
- Gates on `out/notes_v9_short.mp4`: `verify_video OK` (aac 48 kHz 2ch, moov@36, motion
  25.25 %, 1080x1920), `MOTION_OK median 7.61 min 2.41`, `frame_gate COVER_OK ink 6.98 % /
  HOOK_OK 7.10 / LOOP_OK 0.00 %`, `AUDIO_OK` 19.4 dB bed-under, dead air 5.1 %, −15.0 LUFS.
- Kill switches: `NOTES_SYNC=0` (proportional build), `NOTES_BEATS=<path>`,
  `NOTES_PAYOFF=0` (old 46 px roots / 306 px card), `NOTES_BADGE=adjacent`.
- **Next gap (named by the cover read, unfixed):** frame 1 is still a complete cheat
  sheet — "a complete cheat sheet masquerading as a cover; the three cases and the
  exercise already deliver most of the lesson" (6.5/10 broad-audience read). Hiding part
  of the page on frame 1 costs the loop bumper, so it needs its own measurement.
- Not published: publishing a replacement is Ahmad's call.


## 2026-10-26 (3rd run) — (d) visual style: the three root-case cards were placed by their BOUNDING BOX, not by their axis

Format worked: **Manim maths explainer** (`math-videos/discriminant_cover.py`, format 1 of 3).
Deliverable `math-videos/out/discriminant_v29_short.mp4` (14.7 s, 1080x1920).

- **The defect, measured on `out/discriminant_v28_short.mp4` frame 1:** the three root-case tiles
  ("2 roots / 1 root / 0 roots") each carry a mini parabola drawn around a local axis, and
  `mark.move_to(...)` centred each mark's **bounding box** — boxes whose heights differ because
  "2 roots" spans the axis both ways, "1 root" only above it, "0 roots" higher still. The three
  axis lines therefore landed at 0.256 / 0.115 / 0.069 u = **1260 / 1288 / 1304 px**, a 43-46 px
  staircase across the row. Two independent full-frame reads named it the cover's #1 defect
  ("the first case appears to float … the three cases are meant to be parallel").
- **Fix:** the axis is the datum. `MARK_AXIS_LOCAL` / `CHIP_AXIS_Y` module constants +
  `mark.shift(UP * (CHIP_AXIS_Y - MARK_AXIS_LOCAL))`; only the curve's RELATION to the axis now
  differs between the three cards, which is exactly what they teach.
- **Score before → after (one image, two panels, phone size, same question, final polished files):
  7.5/10 → 8/10**, and **7 → 9** on a second pair read; both reads name the cause ("the moving
  axis … makes the three cases feel less directly comparable"). Pixel proof: axis-row spread
  **46 px → 4 px**.
- **Two pipeline bugs surfaced while verifying, both fixed:**
  `speak_beats.py` wrote the concatenated narration to ONE shared `narration.wav`, so the notes
  run had overwritten the discriminant's audio — `disc_beats.json` claimed 14.69 s and its audio
  measured **31.61 s** (`[lock] drift -16.92s`, captions from the wrong script). Now
  `narration_<plan-stem>.wav`. And `caption_beats`' orphan rule ran over the whole track, pushing
  a sentence's last word into the next sentence's first chunk — the plate shipped as
  **"it Count the crossings"** (`BEAT_SYNC_FAIL`) until `_deorphan` was applied per sentence.
- Gates on `out/discriminant_v29_short.mp4`: `verify_video OK` (aac 48 kHz 2ch, moov@36, motion
  32.09 %, 1080x1920), `MOTION_OK median 5.43 | min 2.22` (**only with `POLISH_MG=1.7`** — the
  same clip at the default 1.0 read `min 0.99` = NOT SHIPPABLE), `COVER_OK ink 6.33 % / HOOK_OK
  6.47 / LOOP_OK 0.67 %`, `AUDIO_OK` 22.9 dB bed-under, dead air 1.2 %, −14.0 LUFS, `BEAT_SYNC_OK`
  5/5. Kill switch: `DISC_AXIS_ALIGN=0`.
- **Next gap (named by both reads, unfixed):** the band between the cards and the caption plate is
  dead space at phone size ("there is a large amount of unused space below the cards"), and the
  `?` medallion repeats what the headline and `Δ = ?` already say.
- Not published: publishing a replacement is Ahmad's call.

## 2026-10-27 (5th run) — (d) visual style: the speed chart measured a thing that never touched the picture

Format worked: **Anime Physics** (`math-videos/anime_physics.py`, format 3 of 3 — the weakest at 6/10).
Deliverable `math-videos/out/katana_v35_short.mp4` (9.2 s, 1080x1920).

- **The defect, measured on `out/katana_v34_short.mp4` (two independent full-frame reads of the
  payoff and the cover):** the figure is no longer the problem — the chart is a **footer**. *"The
  bottom infographic is visually detached from the anime action ... the top feels like dramatic
  anime poster art; the middle is an action illustration; the bottom becomes a separate, generic
  slide-like footer"*, and the read's own prescription: *"connect the katana's motion arc directly
  to the speed scale with a vector, trail, or labeled radius"*. The cover read independently said
  the lower half *"reads like a dashboard caught mid-build"*.
- **Fix:** the blade's own trail now runs from the TIP down onto the gold **20** mark — 36 Line
  segments sampled along one cubic bezier, width 2.8→4.8 px and opacity 0.42→0.86 toward the node,
  a small bright dot anchoring the origin on the tip and a larger flare (r .042 over an r .085
  halo) on the value. Drawn with `LaggedStart(Create…)` inside the fill beat so the value lands
  where the trail arrives. Absent from frame 1 (cover diff vs the old build: **maxdiff 0**),
  faded out in the loop bumper. Then the three blade-arc hairlines were re-weighted to soft wide
  smears (6.0/4.6/3.4 px @ .16/.11/.08) because beside a crisp connector they read as its stray
  branches.
- **Score before → after:** payoff frame **7/10 → 8.5/10** on the integration read; on ONE
  identical question put to both finished frames the coarse score held at 8/10 but the verdict
  flipped — *"they mostly read as two separate systems"* (v34) → *"they read as one connected
  system"* (v35). Four A/B iterations were needed: fade-to-thin (too faint at feed size) →
  taper-up but arriving from above (tucked behind the "20") → radial departure (fork at the tip)
  → tangential departure + arc re-weight.
- Gates on `out/katana_v35_short.mp4`: `verify_video OK` (aac 48 kHz 2ch, moov@36, motion
  24.73 %), `COVER_OK ink 6.77 % / HOOK_OK 3.43 / LOOP_OK 0.64 %`, `MOTION_OK median 4.91 |
  min 3.22`, `AUDIO_OK` 21.4 dB bed-under, dead air 1.5 %, −14.3 LUFS.
- Kill switches: `ANIME_TRAIL=0`, `ANIME_ARCFAN=hairline`.
- **Next gap (named by one read, deliberately NOT fixed):** at feed width the head-edge rim stroke
  was called *"a stray shard ... the biggest remaining defect"*, while a 2× crop of the same
  pixels read it as *"a stylized facial/cheek highlight"*. The two disagree, so the figure needs a
  feed-width A/B first — editing a silhouette on one small-scale read is how the 6/10 version
  happened.
- Not published: publishing a replacement is Ahmad's call.

## 2026-10-28 (4th run) — (c) motion: the anime opening was a still frame and HOOK was reading grain

Format worked: **Anime Physics** (`math-videos/anime_physics.py`, format 3 of 3).
Deliverable `math-videos/out/katana_v37_short.mp4` (9.3 s, 1080x1920).

- **The defect, measured on the RAW render (not the polished file):** adjacent-frame diff was
  **0.00 for frames 0-0.95 s**, one 91 spike for the slash burst, then 0.0-0.5 — a 2 s median of
  **0.14**, under a title that promises a slash. The polished v36 gated `HOOK_OK 3.43` only because
  `polish_short`'s grain reads 3.2-3.8 on every frame by itself: HOOK is a median, so grain sets the
  floor. A feed read of the cover said the same in words — *"much more static than full of motion …
  a poster illustration of a swordsman getting ready to strike, not a frame captured during a
  high-speed slash"*, and a 4-frame read of the opening: *"the katana is a frozen cutout: the sword
  does not actually swing"*.
- **Two rejected fixes, both measured:** a full-frame light BAND (correct cos^2 composite) lifted the
  raw median to **8.05** and scored **2/10** — *"a lens flare or light leak … no clear origin at the
  sword"*; a radial fan pivoting at the hand scored **6/10** and named its own fix — *"one consistent,
  narrow crescent generated by the moving tip"*.
- **Shipped (one device: the swing):** the blade itself rotates about the guard (0.86 rad in 0.34 s),
  four hard-edged blade afterimages fan behind it, an annular tip-trail crescent sits at the blade's
  own radius and sweeps with it, and a camera punch (scale 1.035 + 0.085 u rise, peak 0.36 s, exact
  identity by 1.90 s) makes the whole picture strike. Everything is hidden on frame 1 and unwinds.
- **Score before → after (same question, feed width):** opening kinetic energy **2-3/10 → 8/10**;
  *"does the sword visibly swing? Yes … blade smear present … tip trail present"*, no detached blade,
  no smeared text, no chart collision. Gates on the final file: `HOOK 3.40 → 4.53`,
  `MOTION_OK 6.04 → 6.05 | min 3.21`, `COVER_OK` ink 7.24 vs 8.67, `LOOP_OK 1.43 %`, `verify_video OK`
  (aac 48 kHz 2ch, moov@36, motion 26.41 %), `AUDIO_OK` 19.3 dB bed-under, dead air 1.5 %, -14.8 LUFS.
- **Two rendering bugs found while answering the read:** `set_opacity(env)` on the smear GROUP
  OVERRODE the four blade copies' own alphas with one uniform value, which is why the fan rendered
  near-solid and "swallowed the blade" on two reads; it now multiplies each copy's base alpha. And
  `z_index` cannot lift the blade above that fan — `Scene.add` sorts once, at add time, and the blade
  was added with the figure — so the fix was COLOUR (fan -> the format's ghost red) plus a 9 px
  hard-edged white core line appended last inside the smear group. Read after: "the ice-white blade
  reads as a continuous hard-edged spine … the sword is shown mid-cut", kinetic **8/10**.
- **Two traps worth the log:** `fig[-1]` is only the blade's 2.6 px edge hairline — rotating it moved
  nothing; the blade is the last six elements. And an updater runs on frame 1 too, so a sweep with
  `t0=0` put light on the cover (maxdiff 54 vs v36); start layers at `t0 >= 0.10`.
- **Next gap:** the hilt-root flare still blooms over the guard ("the sword appears to erupt from a glowing blob"), and the payoff still holds ~3 s of a completely still frame before the bumper (named by
  the v36 run and still open) — a kinetic beat INSIDE the hold, built to `Restore()` exactly.
- Not published: replacing the live katana short is Ahmad's call.
