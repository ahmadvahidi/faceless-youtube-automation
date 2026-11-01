import sys, json
sys.path.insert(0, "/opt/data/workspace/faceless-youtube")
import yt_uploader as yt
tok = yt.get_access_token()
ch = yt._api(tok, "/youtube/v3/channels?part=snippet,statistics&mine=true")
for it in ch.get("items", []):
    s = it["statistics"]
    print(it["snippet"]["title"], "| subs", s.get("subscriberCount"), "| views", s.get("viewCount"), "| vids", s.get("videoCount"))
r = yt._api(tok, "/youtube/v3/search?forMine=true&type=video&maxResults=50&order=date")
ids = [i["id"]["videoId"] for i in r.get("items", [])]
print("recent count:", len(ids))
v = yt._api(tok, "/youtube/v3/videos?part=contentDetails,statistics,snippet&id=" + ",".join(ids[:50]))
rows = []
for it in v.get("items", []):
    rows.append((it["snippet"]["title"][:50], it["contentDetails"]["duration"], it["statistics"].get("viewCount"), it["id"], it["snippet"]["publishedAt"][:10]))
rows.sort(key=lambda x: x[4], reverse=True)
for t, d, vc, i, p in rows:
    print(f"{p} {d:>9} {vc:>5}v  {t}  [{i}]")
