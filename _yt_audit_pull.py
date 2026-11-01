#!/usr/bin/env python3
"""Pull every live video of the channel with stats, dump JSON + quick stats."""
import json, sys, statistics, datetime as dt
sys.path.insert(0, "/opt/data/workspace/faceless-youtube")
import yt_uploader as y

tok = y.get_access_token()

def api(path):
    return y._api(tok, path)

ch = api("/youtube/v3/channels?part=contentDetails,statistics&mine=true")["items"][0]
uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
print("channel subs:", ch["statistics"].get("subscriberCount"),
      "views:", ch["statistics"].get("viewCount"),
      "videos:", ch["statistics"].get("videoCount"))

ids, page = [], None
while True:
    p = f"/youtube/v3/playlistItems?part=contentDetails&playlistId={uploads}&maxResults=50"
    if page:
        p += f"&pageToken={page}"
    d = api(p)
    ids += [it["contentDetails"]["videoId"] for it in d["items"]]
    page = d.get("nextPageToken")
    if not page:
        break

vids = []
for i in range(0, len(ids), 50):
    chunk = ",".join(ids[i:i+50])
    d = api(f"/youtube/v3/videos?part=snippet,statistics,contentDetails&id={chunk}")
    vids += d["items"]

def isos(sec):
    s = sec or "PT0S"
    import re
    h = re.search(r"(\d+)H", s); m = re.search(r"(\d+)M", s); sec_ = re.search(r"(\d+)S", s)
    return int(h.group(1)) * 3600 if h else 0 + (int(m.group(1)) * 60 if m else 0) + (int(sec_.group(1)) if sec_ else 0)

rows = []
for v in vids:
    sn, st, cd = v["snippet"], v["statistics"], v["contentDetails"]
    secs = isos(cd.get("duration"))
    rows.append({
        "id": v["id"], "title": sn["title"], "published": sn["publishedAt"],
        "views": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0)),
        "comments": int(st.get("commentCount", 0)), "seconds": secs,
        "kind": "short" if secs <= 61 else "long",
    })

json.dump(rows, open("/opt/data/workspace/faceless-youtube/_audit_videos.json", "w"), ensure_ascii=False, indent=1)

shorts = [r for r in rows if r["kind"] == "short"]
longs = [r for r in rows if r["kind"] == "long"]
for name, grp in (("ALL", rows), ("SHORTS", shorts), ("LONG", longs)):
    if not grp:
        continue
    v = sorted(r["views"] for r in grp)
    print(f"{name}: n={len(grp)} median={statistics.median(v):.0f} mean={statistics.mean(v):.0f} "
          f"min={v[0]} max={v[-1]} total={sum(v)}")

print("\nTOP 10 by views:")
for r in sorted(rows, key=lambda r: -r["views"])[:10]:
    print(f"  {r['views']:>6}  {r['kind']:<5} {r['seconds']:>4}s  {r['published'][:10]}  {r['title'][:70]}")

print("\nBOTTOM 10 by views:")
for r in sorted(rows, key=lambda r: r["views"])[:10]:
    print(f"  {r['views']:>6}  {r['kind']:<5} {r['seconds']:>4}s  {r['published'][:10]}  {r['title'][:70]}")

# rhythm: uploads per ISO week
from collections import Counter
weeks = Counter(dt.date.fromisoformat(r["published"][:10]).isocalendar()[:2] for r in rows)
print("\nUploads per week (last 12):")
for k, v in sorted(weeks.items())[-12:]:
    print(f"  {k[0]}-W{k[1]:02d}: {v}")

# views per day since publish (age-normalised)
today = dt.date(2026, 10, 25)
print("\nTop by views/day:")
def vpd(r):
    age = max(1, (today - dt.date.fromisoformat(r["published"][:10])).days)
    return r["views"] / age
for r in sorted(rows, key=vpd, reverse=True)[:8]:
    print(f"  {vpd(r):>6.1f}/day  {r['views']:>5}  {r['kind']:<5}  {r['published'][:10]}  {r['title'][:60]}")
