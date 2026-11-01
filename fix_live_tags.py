#!/usr/bin/env python3
"""Re-tag uploads that still carry a RETIRED niche's tag pool.

Why this exists: the tag pool is one of the three inputs YouTube uses to decide which audience
tests a new upload. DOPEAK moved to maths/science Shorts, but 17 of the 25 most recent uploads
were still tagged with the retired FINANCE pool ("investing for beginners", "index funds",
"build wealth") — including "What Makes a Superhabitable Planet?" and "How Fast Do Colliding
Objects Lose Energy?". Those videos are still being served to a finance audience that has no
reason to watch them.

This script is READ-ONLY unless you pass --apply.

    python fix_live_tags.py                 # dry run: print every change it would make
    python fix_live_tags.py --limit 3       # dry run, first 3 only
    python fix_live_tags.py --apply --limit 1   # change ONE video, then eyeball it

It never deletes anything and never touches the title, description or thumbnail. YouTube's
videos.update REPLACES the whole `snippet` part, so this reads the existing snippet and changes
only `tags` — a hand-built snippet would silently blank the title.
"""
from __future__ import annotations

import argparse
import re
import sys

import yt_uploader as yt
from yt_publish import POOLS

HERE_POOL = POOLS["maths"]

# Every pool that is no longer this channel's niche. A tag in here is a leftover, not content.
RETIRED = set(POOLS["finance"])

# Tags that carry no categorisation signal at all — a bare year, "trending", "shorts".
JUNK = {"2024", "2025", "2026", "trending", "trend", "viral", "fyp", "shorts", "us", "news"}

# A FINANCE video's finance pool is CORRECT: the point of this script is to stop maths/science
# videos being served a finance audience, not to relabel the money content. When a video's own
# tags are nothing but the retired pool the tags say nothing, so the title decides — and a title
# with no finance vocabulary in it is treated as maths/science.
FIN_WORDS = {"stock", "stocks", "invest", "investing", "investor", "ipo", "portfolio",
             "inflation", "wealth", "money", "retirement", "fund", "funds", "dividend",
             "market", "robo", "advisor", "finance", "financial", "savings", "spend",
             "spending", "dollar", "gain", "gains", "return", "returns", "debt", "credit",
             "budget", "tax", "pension", "economy", "politics", "sanctions"}


def live_videos(token: str, limit: int = 25) -> list[dict]:
    """The channel's own uploads, newest first: [{id, title, categoryId, snippet, tags}]."""
    s = yt._api(token, "/youtube/v3/search?part=snippet&forMine=true&type=video"
                       f"&maxResults={min(limit, 50)}&order=date")
    out = []
    for i in s.get("items", []):
        vid = i["id"].get("videoId")
        if vid:
            out.append({"id": vid, "title": i["snippet"].get("title", "")})
    ids = [v["id"] for v in out]
    for k in range(0, len(ids), 25):
        r = yt._api(token, "/youtube/v3/videos?part=snippet&id=" + ",".join(ids[k:k + 25]))
        for it in r.get("items", []):
            for v in out:
                if v["id"] == it["id"]:
                    v["snippet"] = it["snippet"]
                    v["tags"] = it["snippet"].get("tags") or []
    return [v for v in out if "snippet" in v]


def _is_finance(title: str) -> bool:
    if re.search(r"social\s+security", title, re.I):
        return True
    return bool({w for w in re.findall(r"[a-z0-9]+", title.lower()) if w in FIN_WORDS})


def retag(snippet: dict) -> tuple[list[str], str] | None:
    """(corrected tag list, pool name) for one video, or None when it is already clean.

    Keeps every tag the video genuinely owns (anything not in a retired pool, minus pure junk) and
    appends the pool that MATCHES ITS SUBJECT, so a probability short keeps "lottery odds" and loses
    "index funds" while an IPO long-form keeps its finance tags.
    """
    tags = snippet.get("tags") or []
    if not (set(tags) & RETIRED):
        return None
    keep = [t for t in tags if t not in RETIRED and t.lower() not in {r.lower() for r in RETIRED}
            and t.lower() not in JUNK and not re.fullmatch(r"20\d\d", t)]
    pool = "finance" if _is_finance(snippet.get("title", "")) else "maths"
    new = list(dict.fromkeys(keep + POOLS[pool]))[:30]
    if set(new) == set(tags):      # already correct for its own subject — no write needed
        return None
    return new, pool


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="actually write the change (default: dry run, prints only)")
    ap.add_argument("--limit", type=int, default=25)
    a = ap.parse_args()

    token = yt.get_access_token()
    ch = yt._api(token, "/youtube/v3/channels?part=snippet&mine=true")["items"][0]
    print(f"[channel] {ch['snippet']['title']} ({ch['id']})")
    vids = live_videos(token, a.limit)

    changed = []
    for v in vids:
        r = retag(v["snippet"])
        if r is None:
            continue
        new, pool = r
        changed.append((v, new))
        print(f"\n  {v['id']}  {v['title'][:58]}")
        print(f"     had  ({len(v['tags']):2d}): {', '.join(v['tags'][:12])}")
        print(f"     gets ({len(new):2d}, {pool} pool): {', '.join(new[:12])}")

    print(f"\n=> {len(changed)} of {len(vids)} checked videos carry a retired pool")
    if not changed:
        return 0
    if not a.apply:
        print("   DRY RUN — nothing written. Re-run with --apply to write it (Ahmad's call).")
        return 0

    for v, new in changed:
        sn = dict(v["snippet"])          # keep title/description/categoryId/defaultLanguage
        sn["tags"] = new
        try:
            yt._api(token, "/youtube/v3/videos?part=snippet",
                    {"id": v["id"], "snippet": sn}, method="PUT")
            print(f"  [updated] {v['id']} {v['title'][:50]}")
        except Exception as e:  # noqa: BLE001
            print(f"  [FAILED]  {v['id']} {str(e)[:120]}")
    # Read one back so success is proved by the API, not by the 200.
    vid0 = changed[0][0]["id"]
    back = yt._api(token, f"/youtube/v3/videos?part=snippet&id={vid0}")
    got = back["items"][0]["snippet"].get("tags") or []
    print(f"\n[verify] read back {vid0}: {len(got)} tags, "
          f"retired leaks: {sorted(set(got) & RETIRED)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
