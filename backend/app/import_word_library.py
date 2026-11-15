"""Publish verified Word files without destroying old documents or citations."""
import argparse,hashlib,io,json
from pathlib import Path
from sqlalchemy import select,text
from .db import Session
from .models import Document,DocumentFile,DocumentChunk,User,Job,SystemSetting
from .retrieval import word_text
from .provider import embed,model_id,embedding_provider
from .audit import audit

KEY='nova-commerce-word-library-1.1'
LEGACY_NAMES=['Chính sách nghỉ phép 2026.txt','Quy trình quản lý tồn kho.txt','Hướng dẫn báo cáo kinh doanh.txt']

def publish(db,folder):
    if db.get(SystemSetting,'sample-data-removed-v1'):raise ValueError('Kho tài liệu mẫu đã được xóa theo yêu cầu; không tự nạp lại.')
    if embedding_provider()!='lexical':raise ValueError('Word import uses local lexical indexing only; no external provider calls.')
    if db.bind.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(730031)'))
    prior=db.get(SystemSetting,KEY)
    if prior:return {**prior.value,'already_published':True}
    folder=Path(folder).resolve();manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if len(manifest)!=26:raise ValueError('Expected the complete 26-document controlled library.')
    admin=db.scalar(select(User).where(User.role=='Admin',User.active.is_(True)).order_by(User.created_at.desc()))
    if not admin:raise ValueError('An active Admin is required.')
    prepared=[]
    for item in sorted(manifest,key=lambda x:x['id']):
        path=(folder/item['file']).resolve()
        if path.parent!=folder or path.suffix!='.docx':raise ValueError('Unexpected Word file path.')
        content=path.read_bytes()
        if len(content)>10*1024*1024 or hashlib.sha256(content).hexdigest()!=item['sha256']:raise ValueError('Verified Word file changed.')
        old=db.scalar(select(Document).where(Document.id==item['id']).with_for_update())
        blob=db.get(DocumentFile,item['id'])
        if not old or old.scope!=item['scope'] or old.status!='indexed' or not blob or hashlib.sha256(blob.content).hexdigest()!=item['source_sha256']:
            raise ValueError('Source document changed; re-export and review before publishing.')
        content_text=word_text(io.BytesIO(content))
        if not content_text or item['code'] not in content_text:raise ValueError('Word document content or code is missing.')
        prepared.append((item,old,content,content_text))
    mapping=[];archived=[]
    for item,old,content,content_text in prepared:
        current=Document(user_id=admin.id,name=f"[{item['code']}] {item['title']}.docx",scope=old.scope,status='indexed',content=content_text)
        db.add(current);db.flush();db.add(DocumentFile(document_id=current.id,content=content))
        count=0
        for offset in range(0,len(content_text),850):
            chunk=content_text[offset:offset+1000].strip()
            if chunk:
                db.add(DocumentChunk(document_id=current.id,content=chunk,position=count,embedding=embed(chunk),model=model_id()));count+=1
        current.chunks=count;db.add(Job(resource=current.id,kind='document',status='done'))
        old.status='archived';archived.append(old.id)
        mapping.append({'code':item['code'],'old_id':old.id,'new_id':current.id,'name':current.name,'scope':current.scope,'sha256':item['sha256']})
        audit(db,admin,'document.word_version_published',current.id,{'previous_id':old.id,'code':item['code'],'version':'1.1','scope':old.scope})
    for old in db.scalars(select(Document).where(Document.name.in_(LEGACY_NAMES),Document.path.is_(None),Document.status=='indexed').with_for_update()):
        if not db.get(DocumentFile,old.id):
            old.status='archived';archived.append(old.id);audit(db,admin,'document.legacy_archived',old.id,{'library':KEY})
    result={'library':KEY,'version':'1.1','documents':mapping,'archived_ids':archived,'published_count':len(mapping),'archived_count':len(archived),'old_chunks_preserved':True,'external_ai_calls':0}
    db.add(SystemSetting(key=KEY,value=result));audit(db,admin,'document.word_library_published',KEY,{'published':len(mapping),'archived':len(archived)})
    db.commit();return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder');args=parser.parse_args()
    with Session() as db:print(json.dumps(publish(db,args.folder),ensure_ascii=True,indent=2))
