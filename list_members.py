import json, os, urllib.request
from pathlib import Path

for line in open(Path('/opt/data/workspace/faceless-youtube/.env')):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1); os.environ.setdefault(k, v)

tok = os.environ['TELEGRAM_BOT_TOKEN']
gid = os.environ['TELEGRAM_GROUP_ID']

def api(method, payload):
    url = f"https://api.telegram.org/bot{tok}/{method}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

# try to list members (may fail without enough perms, but try)
try:
    up = api('getChat', {'chat_id': gid})
    print("chat info:", json.dumps(up.get('result', {}), ensure_ascii=False)[:400])
except Exception as e:
    print("getChat err:", e)

# check recent updates for any other bot that posted
upd = api('getUpdates', {'limit': 200, 'timeout': 0})
seen = {}
for u in upd.get('result', []):
    m = u.get('message') or u.get('channel_post')
    if not m: continue
    frm = m.get('from', {})
    if frm.get('is_bot'):
        key = f"{frm.get('id')}:@{frm.get('username','')}"
        if key not in seen:
            seen[key] = (frm.get('first_name',''), m.get('date'))
for k, v in seen.items():
    print(f"BOT seen: {k} name={v[0]}")
