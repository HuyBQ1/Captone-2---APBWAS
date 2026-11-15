"""Export the current SQLAlchemy schema without reading application data."""
import json,sys,html
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from sqlalchemy.dialects import postgresql
from app.db import Base
from app import models

root=Path(__file__).resolve().parents[1]/'docs/database-design/enterprise'
root.mkdir(parents=True,exist_ok=True)
tables=[];relations=[]
for table in Base.metadata.sorted_tables:
    columns=[]
    for column in table.columns:
        fks=[fk.target_fullname for fk in column.foreign_keys]
        columns.append({'name':column.name,'type':str(column.type.compile(dialect=postgresql.dialect())),
                        'nullable':column.nullable,'primary_key':column.primary_key,'unique':bool(column.unique),'foreign_keys':fks})
        for target in fks:relations.append((table.name,column.name,*target.split('.')))
    tables.append({'name':table.name,'columns':columns})
summary={'tables':len(tables),'columns':sum(len(t['columns']) for t in tables),'foreign_keys':len(relations)}
(root/'schema.json').write_text(json.dumps({'summary':summary,'tables':tables},indent=2),encoding='utf-8')
lines=['# Database design — Nova Commerce / APBWAS, migration 0003','',f"{summary['tables']} tables · {summary['columns']} columns · {summary['foreign_keys']} foreign keys.",'',
       'Generated from SQLAlchemy metadata; no business data or secrets are exported. Historical DOCX version 1.1 describes migration 0002 and is retained as an earlier revision.','',
       '![Table relationship diagram](table-relationships.svg)','','## Storage rules','',
       '- PostgreSQL stores employee profiles, hashed passwords/session/recovery tokens, preferences, company settings, conversations, workflow state, notifications, sales, stock movements, audit, extracted text, vectors and original document bytes.',
       '- Passwords are Argon2 hashes; opaque access tokens are SHA256 hashes. Raw activation links are shown once to the authorized administrator.',
       '- Runtime API keys and the audit signing key remain server environment secrets. Temporary initial account passwords are delivered through a private, ignored file.',
       '- A sale, inventory decrement, version increment, movement and audit commit atomically. Product and inventory versions are separate fields.',
       '- Agent inventory changes retain human approval. Business sales are explicit human operations with permission checks and idempotency references.',
       '- Legacy upload originals are copied into document_files during initialization, without deleting the original volume.',
       '- Roles store permission assignments as JSON; permissions is a catalog, not a many-to-many join table.','']
dot=['digraph schema {','graph [rankdir=LR, bgcolor="white", pad="0.3", nodesep="0.4", ranksep="1.0", splines=polyline, label="Nova Commerce / APBWAS - migration 0003", labelloc=t, fontsize=22];','node [shape=plain,fontname="Arial"];','edge [color="#65748b",arrowsize=0.65,fontname="Arial",fontsize=9];']
for table in tables:
    lines.extend(['## '+table['name'],'','| Column | PostgreSQL type | Null | Keys |','|---|---|---|---|'])
    rows=[f'<TR><TD COLSPAN="2" BGCOLOR="#dfe6ff"><B>{table["name"]}</B></TD></TR>']
    for c in table['columns']:
        keys=', '.join((['PK'] if c['primary_key'] else [])+(['UQ'] if c['unique'] else [])+['FK '+f for f in c['foreign_keys']])
        lines.append(f"| {c['name']} | {c['type']} | {'yes' if c['nullable'] else 'no'} | {keys} |")
        rows.append(f'<TR><TD PORT="{c["name"]}_w" ALIGN="LEFT">{html.escape(c["name"])} {"PK" if c["primary_key"] else "FK" if c["foreign_keys"] else ""}</TD><TD PORT="{c["name"]}_e" ALIGN="LEFT">{html.escape(c["type"])}</TD></TR>')
    dot.append(f'{table["name"]} [label=<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="4">'+''.join(rows)+'</TABLE>>];')
    lines.append('')
for child,column,parent,key in relations:dot.append(f'{parent}:{key}_e:e -> {child}:{column}_w:w [label="{column}"];')
dot.append('}')
(root/'README.md').write_text('\n'.join(lines),encoding='utf-8')
(root/'table-relationships.dot').write_text('\n'.join(dot),encoding='utf-8')
print(json.dumps(summary))
