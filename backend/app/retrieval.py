from pathlib import Path
from io import BytesIO
from sqlalchemy import select, delete, text
from .models import Document, DocumentChunk, DocumentFile
from .provider import embed, model_id

def allowed_scopes(user):
    return ['all',user.role] + (['Manager','Employee'] if user.role == 'Admin' else [])

def word_text(source):
    from docx import Document as Docx
    from docx.oxml.ns import qn
    word=Docx(source)
    paragraphs=[''.join(t.text or '' for t in p.iter(qn('w:t'))).strip()
                for p in word.element.body.iter(qn('w:p'))]
    return '\n'.join(p for p in paragraphs if p)

def search(db,user,query,document_ids=None):
    if document_ids==[]:return []
    vector = embed(query)
    base = select(DocumentChunk,Document).join(Document,Document.id == DocumentChunk.document_id).where(
        Document.status == 'indexed',Document.workspace_id==user.workspace_id,Document.scope.in_(allowed_scopes(user)),DocumentChunk.model == model_id())
    if document_ids is not None:base=base.where(Document.id.in_(document_ids),Document.workspace_id==user.workspace_id)
    if db.bind.dialect.name == 'postgresql':
        db.execute(text("SET LOCAL statement_timeout = '2500ms'"))
        # Continue scanning when the nearest HNSW candidates are outside the user's scope.
        db.execute(text("SET LOCAL hnsw.iterative_scan = 'strict_order'"))
        distance = DocumentChunk.embedding.cosine_distance(vector)
        rows = db.execute(base.add_columns(distance.label('distance')).order_by(distance).limit(5)).all()
        if len(rows) < 5 or any(float(row[2]) > 0.88 for row in rows):
            # Exact ranking also supports older pgvector versions and restrictive filters.
            rows = db.execute(base.add_columns(distance.label('distance')).order_by(distance + 0.0).limit(5)).all()
        candidates = [(chunk,doc,1-float(dist)) for chunk,doc,dist in rows]
    else:
        candidates = [(c,d,sum(a*b for a,b in zip(c.embedding,vector))) for c,d in db.execute(base).all()]
        candidates = sorted(candidates,key=lambda x:x[2],reverse=True)[:5]
    return [{'chunk_id':c.id,'document_id':d.id,'name':d.name,'content':c.content,'page':c.page,'score':round(score,3)}
            for c,d,score in candidates if score >= 0.12]

def index_document(db,doc):
    doc.status = 'processing'
    db.commit()
    blob=db.get(DocumentFile,doc.id)
    if blob or doc.path:
        suffix=Path(doc.name if blob else doc.path).suffix.lower()
        source=BytesIO(blob.content) if blob else Path(doc.path)
        if suffix == '.pdf':
            from pypdf import PdfReader
            pages = [(i+1,p.extract_text() or '') for i,p in enumerate(PdfReader(source).pages)]
        elif suffix == '.docx':
            # The procedure's main content may be in tables. Preserve body order,
            # including cell paragraphs; Document.paragraphs alone drops tables.
            pages = [(None,word_text(source))]
        else:
            pages = [(None,blob.content.decode('utf-8') if blob else source.read_text(encoding='utf-8'))]
    else:
        pages = [(None,doc.content)]
    if sum(len(text) for _,text in pages)>2_000_000:
        raise ValueError('Nội dung trích xuất vượt 2 triệu ký tự; hãy chia tài liệu.')
    if not any(text.strip() for _,text in pages):
        raise ValueError('Không trích xuất được văn bản. PDF scan cần OCR (chưa hỗ trợ).')
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
    count = 0
    for page,text in pages:
        for offset in range(0,len(text),850):
            chunk = text[offset:offset+1000].strip()
            if chunk:
                db.add(DocumentChunk(document_id=doc.id,content=chunk,page=page,position=count,embedding=embed(chunk),model=model_id()))
                count += 1
    doc.content = '\n'.join(text for _,text in pages)
    doc.chunks = count
    doc.status = 'indexed'
    doc.error = None
    db.commit()
