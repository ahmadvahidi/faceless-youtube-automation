import json, os, urllib.request
from pathlib import Path

for line in open(Path('/opt/data/workspace/faceless-youtube/.env')):
    line=line.strip()
    if line and not line.startswith('#') and '=' in line:
        k,v=line.split('=',1); os.environ.setdefault(k,v)

tok=os.environ['TELEGRAM_BOT_TOKEN']
gid=os.environ['TELEGRAM_GROUP_ID']

def api(method, payload=None):
    url=f"https://api.telegram.org/bot{tok}/{method}"
    data=json.dumps(payload).encode() if payload is not None else None
    req=urllib.request.Request(url, data=data, headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

a = api('getChatAdministrators', {'chat_id': gid})
print("ADMINS:")
for m in a.get('result', []):
    u = m.get('user', {})
    print(f"  id={u.get('id')} @{u.get('username','')} is_bot={u.get('is_bot')} name={u.get('first_name','')}")

# also check recent messages to find bots posting in group
upd = api('getUpdates', {'limit': 100, 'timeout': 0})
print("\nRECENT MESSAGES (bots):")
for u in upd.get('result', []):
    m = u.get('message') or u.get('channel_post')
    if not m: continue
    frm = m.get('from', {})
    if frm.get('is_bot'):
        print(f"  bot id={frm.get('id')} @{frm.get('username','')} name={frm.get('first_name','')} text={m.get('text','')[:80]!r}")
