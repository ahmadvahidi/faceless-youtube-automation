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

me = api('getMe', {})
my_id = me['result']['id']
# my own membership = my permissions in this group
mm = api('getChatMember', {'chat_id': gid, 'user_id': my_id})
print("MY permissions:", json.dumps(mm.get('result', {}), ensure_ascii=False))
