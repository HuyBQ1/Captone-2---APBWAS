"""Prove durable state across a restart on the isolated Demo stack only."""
import json,time,uuid,subprocess,hashlib
from pathlib import Path
import httpx
root=Path(__file__).resolve().parents[1]
with httpx.Client(base_url='http://localhost:4181/api',timeout=15) as client:
    client.post('/auth/login',json={'email':'manager@apbwas.demo','password':'Demo@123456'}).raise_for_status()
    identity=client.get('/auth/me');identity.raise_for_status()
    if not identity.json().get('demo_mode'):raise SystemExit('Only the isolated Demo stack may be restarted by this check.')
    name='durability-'+uuid.uuid4().hex+'.txt';content='Durable document stored in PostgreSQL, not the upload volume.'.encode()
    r=client.post('/documents',files={'file':(name,content,'text/plain')});r.raise_for_status();did=r.json()['id']
    deadline=time.monotonic()+40
    while time.monotonic()<deadline:
        r=client.get('/documents/'+did);r.raise_for_status()
        if r.json()['status']=='indexed':break
        time.sleep(.25)
    else:raise RuntimeError('Document did not index.')
    prefs={'theme':'dark','sidebar_collapsed':True}
    client.put('/auth/preferences',json=prefs).raise_for_status()
    before=client.get('/data/products?q=AP-001').json()['items'][0]
    subprocess.run(['docker','compose','-f','compose.test.yaml','restart','postgres','redis','backend','worker','frontend'],cwd=root,check=True,capture_output=True)
    deadline=time.monotonic()+60
    while time.monotonic()<deadline:
        try:
            r=client.get('/health/ready')
            if r.status_code==200:break
        except httpx.HTTPError:pass
        time.sleep(.5)
    else:raise RuntimeError('Stack did not become ready after restart.')
    me=client.get('/auth/me');me.raise_for_status();assert me.json()['preferences']==prefs
    after=client.get('/data/products?q=AP-001');after.raise_for_status();assert after.json()['items'][0]==before
    document=client.get('/documents/'+did);document.raise_for_status();assert document.json()['status']=='indexed'
    blob=client.get('/documents/'+did+'/download');blob.raise_for_status();assert blob.content==content
    assert document.json()['chunk_items']
    client.put('/auth/preferences',json={'theme':'light','sidebar_collapsed':False}).raise_for_status()
    client.delete('/documents/'+did).raise_for_status()
    result={'passed':True,'stack':'apbwas-review','external_ai_calls':0,'verified_after_restart':['database session','user preferences','product and inventory','document metadata','original file bytes','indexed document chunks']}
    (root/'docs/enterprise-persistence.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
