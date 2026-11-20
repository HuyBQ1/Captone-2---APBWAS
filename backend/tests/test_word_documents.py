import io
import json,hashlib
from sqlalchemy import select,func
from docx import Document as Word
from app.models import Document,DocumentFile,DocumentChunk
from app.retrieval import index_document
from app.import_word_library import publish,LEGACY_NAMES
from conftest import login

def test_docx_indexes_process_tables_in_body_order(env):
    _,factory,users,_=env
    word=Word();word.add_paragraph('Trước bảng')
    table=word.add_table(rows=1,cols=2);table.cell(0,0).text='Trách nhiệm';table.cell(0,1).text='Kiểm đếm trước khi nhập kho'
    word.add_paragraph('Sau bảng');output=io.BytesIO();word.save(output)
    with factory() as db:
        doc=Document(user_id=users['Admin'],name='Quy trình.docx',scope='all');db.add(doc);db.flush()
        db.add(DocumentFile(document_id=doc.id,content=output.getvalue()));db.commit();index_document(db,doc)
        assert 'Kiểm đếm trước khi nhập kho' in doc.content
        assert doc.content.index('Trước bảng')<doc.content.index('Trách nhiệm')<doc.content.index('Sau bảng')

def test_word_publication_preserves_history_scopes_and_is_repeatable(env,tmp_path):
    client,factory,users,_=env;manifest=[];old_chunks=[]
    with factory() as db:
        for i in range(26):
            old=Document(user_id=users['Admin'],name=f'Old {i}.txt',scope='Admin' if i==0 else 'all',status='indexed',content='Original source')
            db.add(old);db.flush();db.add(DocumentFile(document_id=old.id,content=b'Original source'))
            chunk=DocumentChunk(document_id=old.id,content='Original citation',position=0,embedding=[1.0]+[0.0]*383,model='demo-hash-v1-384');db.add(chunk);db.flush();old_chunks.append(chunk.id)
            word=Word();code=f'NC-TST-{i:03}';word.add_paragraph(code);word.add_table(rows=1,cols=1).cell(0,0).text='Bước xác nhận số lượng'
            data=io.BytesIO();word.save(data);filename=f'{code}.docx';(tmp_path/filename).write_bytes(data.getvalue())
            manifest.append({'id':old.id,'file':filename,'code':code,'scope':old.scope,'title':f'Procedure {i}',
                             'sha256':hashlib.sha256(data.getvalue()).hexdigest(),'source_sha256':hashlib.sha256(b'Original source').hexdigest()})
        for name in LEGACY_NAMES:db.add(Document(user_id=users['Admin'],name=name,scope='all',status='indexed',content='Legacy text'))
        db.commit();(tmp_path/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
        result=publish(db,tmp_path);assert result['published_count']==26 and result['archived_count']==29
        assert all(db.get(DocumentChunk,id).content=='Original citation' for id in old_chunks)
        for item in result['documents']:
            assert db.get(Document,item['old_id']).status=='archived'
            assert db.get(Document,item['new_id']).scope==item['scope']
            assert 'Bước xác nhận số lượng' in db.get(Document,item['new_id']).content
        assert publish(db,tmp_path)['already_published'] is True
        assert db.scalar(select(func.count()).select_from(Document))==55
    login(client,'Admin');assert client.get('/api/documents').json()['total']==26
    assert client.get('/api/documents?include_archived=true').json()['total']==55
    old_id=manifest[1]['id'];assert client.get('/api/documents/'+old_id).status_code==200
    assert client.post('/api/documents/'+old_id+'/reindex').status_code==409
    assert client.delete('/api/documents/'+old_id).status_code==409
    login(client,'Employee');assert client.get('/api/documents').json()['total']==25
    admin_doc=next(item for item in result['documents'] if item['scope']=='Admin')
    assert client.get('/api/documents/'+admin_doc['new_id']+'/download').status_code==403
