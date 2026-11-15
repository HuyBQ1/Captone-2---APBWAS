"""Copy legacy upload files into DB without deleting the original volume."""
from pathlib import Path
from sqlalchemy import select
from .db import Session
from .models import Document,DocumentFile

def migrate():
    copied=missing=0
    with Session() as db:
        for doc in db.scalars(select(Document).where(Document.path.is_not(None))):
            if db.get(DocumentFile,doc.id):continue
            path=Path(doc.path)
            if not path.is_file():missing+=1;continue
            content=path.read_bytes()
            if len(content)>10*1024*1024:raise RuntimeError('Legacy document exceeds the configured 10 MB limit.')
            db.add(DocumentFile(document_id=doc.id,content=content));copied+=1
        db.commit()
    print(f'Legacy document persistence: copied={copied}, missing_originals={missing}')
if __name__=='__main__':migrate()
