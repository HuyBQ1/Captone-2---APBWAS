"""Capture generated credentials privately; never overwrite an existing delivery file."""
import argparse,json,os,subprocess
from pathlib import Path
import httpx
parser=argparse.ArgumentParser()
parser.add_argument('--disable-demo',action='store_true')
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
path=root/'backups/novacommerce-accounts.json'
path.parent.mkdir(exist_ok=True)
command=['docker','compose','exec','-T','backend','python','-m','app.provision_company']
if args.disable_demo:command.append('--disable-demo')
with path.open('x',encoding='utf-8') as stream:
    result=subprocess.run(command,cwd=root,stdout=stream,stderr=subprocess.PIPE)
    stream.flush();os.fsync(stream.fileno())
if result.returncode:raise SystemExit('Provisioning failed; use the existing Admin/recovery process. No credentials are overwritten automatically.')
delivery=json.loads(path.read_text(encoding='utf-8'))
for account in delivery['accounts']:
    with httpx.Client(base_url=delivery['login_url'],timeout=15,follow_redirects=False) as client:
        r=client.post('/api/auth/login',json={'email':account['email'],'password':account['temporary_password']});r.raise_for_status()
        assert r.json()['role']==account['role'] and r.json()['must_change_password']
        client.post('/api/auth/logout').raise_for_status()
print('Private account file:',path)
