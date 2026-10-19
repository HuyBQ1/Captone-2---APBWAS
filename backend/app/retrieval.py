from pathlib import Path
from sqlalchemy import select, delete, or_
from .models import Document, DocumentChunk
from .provider import embed, model_id

def allowed_scopes(user):
    return ['all',user.role] + (['Manager','Employee'] if user.role == 'Admin' else [])

def search(db,user,query):
    vector = embed(query)
    base = select(DocumentChunk,Document).join(Document,Document.id == DocumentChunk.document_id).where(
        Document.status == 'indexed',Document.scope.in_(allowed_scopes(user)),DocumentChunk.model == model_id())
    if db.bind.dialect.name == 'postgresql':
        distance = DocumentChunk.embedding.cosine_distance(vector)
        rows = db.execute(base.add_columns(distance.label('distance')).order_by(distance).limit(5)).all()
        candidates = [(chunk,doc,1-float(dist)) for chunk,doc,dist in rows]
    else:
        candidates = [(c,d,sum(a*b for a,b in zip(c.embedding,vector))) for c,d in db.execute(base).all()]
        candidates = sorted(candidates,key=lambda x:x[2],reverse=True)[:5]
    return [{'chunk_id':c.id,'document_id':d.id,'name':d.name,'content':c.content,'page':c.page,'score':round(score,3)}
            for c,d,score in candidates if score >= 0.12]

def index_document(db,doc):
    doc.status = 'processing'
    db.commit()
    if doc.path:
        path = Path(doc.path)
        if path.suffix.lower() == '.pdf':
            from pypdf import PdfReader
            pages = [(i+1,p.extract_text() or '') for i,p in enumerate(PdfReader(path).pages)]
        elif path.suffix.lower() == '.docx':
            from docx import Document as Docx
            pages = [(None,'\n'.join(p.text for p in Docx(path).paragraphs))]
        else:
            pages = [(None,path.read_text(encoding='utf-8'))]
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
