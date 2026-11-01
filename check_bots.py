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

# full member count + who is a bot
cnt = api('getChatMemberCount', {'chat_id': gid})
print("member count:", cnt.get('result'))

# admins (already known) + try getChatAdministrators
adm = api('getChatAdministrators', {'chat_id': gid})
print("\nADMINS:")
for m in adm.get('result', []):
    u = m.get('user', {})
    print(f"  id={u.get('id')} @{u.get('username','')} bot={u.get('is_bot')} "
          f"name={u.get('first_name','')} status={m.get('status')}")

# my own bot permissions
me = api('getMe', {})
print("\nMY BOT:", me.get('result', {}).get('username'))
