import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
const require=createRequire('C:/Users/huydd/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json');
const {instance}=require('@viz-js/viz');
const sharp=require('sharp');
sharp.concurrency(1);sharp.cache(false);
const dir=path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/,'$1'));
const root=decodeURIComponent(dir);
const out=path.join(root,'diagrams');fs.mkdirSync(out,{recursive:true});
const tables=JSON.parse(fs.readFileSync(path.join(root,'schema-metadata.json'),'utf8'));
const order=['roles','users','auth_sessions','conversations','messages','workflows','workflow_steps','tool_executions','workflow_events','approval_requests','approval_decisions','reports','usage_records','documents','document_chunks','products','inventory','sales','permissions','audit_logs','system_settings','jobs'];
const byName=Object.fromEntries(tables.map(t=>[t.name,t]));
const esc=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
const palette={roles:['#DAB0F6','#FAF2FF'],users:['#DAB0F6','#FAF2FF'],auth_sessions:['#DAB0F6','#FAF2FF'],permissions:['#DAB0F6','#FAF2FF'],conversations:['#40BAC8','#F0FEFF'],messages:['#40BAC8','#F0FEFF'],products:['#E8A349','#FFFAEF'],inventory:['#E8A349','#FFFAEF'],sales:['#E8A349','#FFFAEF'],documents:['#69B58A','#F2FFF7'],document_chunks:['#69B58A','#F2FFF7'],approval_requests:['#ED8CA6','#FFF4F6'],approval_decisions:['#ED8CA6','#FFF4F6']};
let relations=[];
for(const t of tables)for(const c of t.columns)for(const fk of c.fks){const [parent,key]=fk.target.split('.');relations.push({child:t.name,column:c.name,parent,key,nullable:c.nullable,unique:c.unique||c.pk});}
const viz=await instance();
let physical=['digraph APBWAS {',
'graph [rankdir=LR, bgcolor="white", pad="0.35", nodesep="0.28", ranksep="0.6", splines=polyline, outputorder=edgesfirst, fontname="Times New Roman", pack=false, label="APBWAS Table Relationship Diagram\\n22 tables · 143 columns · 21 foreign keys", labelloc=t, fontsize=22];',
'node [shape=plain,fontname="Times New Roman",fontsize=11];',
'edge [fontname="Times New Roman",fontsize=9,color="#647080",penwidth=1.0,arrowsize=0.65];'];
for(const name of order){const t=byName[name];const [stroke,fill]=palette[name]||['#8FA2D3','#F5F7FF'];
let rows=`<TR><TD COLSPAN="3" BGCOLOR="${stroke}"><B>${name.toUpperCase()}</B></TD></TR>`;
for(const c of t.columns){const markers=[c.pk?'PK':'',c.fks.length?'FK':'',c.unique?'UQ':''].filter(Boolean).join(',');const type=c.type.replace('TIMESTAMP WITH TIME ZONE','timestamptz').replace('VARCHAR','varchar').replace('INTEGER','integer').replace('BOOLEAN','boolean').replace('NUMERIC','numeric').replace('VECTOR','vector').replace('JSON','json').replace('TEXT','text');
rows+=`<TR><TD ALIGN="LEFT">${esc(type)}</TD><TD PORT="${c.name}" ALIGN="LEFT">${c.pk?'<B>':''}${c.name}${c.pk?'</B>':''}${c.nullable?' ?':''}</TD><TD>${markers}</TD></TR>`;}
physical.push(`${name} [label=<<TABLE BORDER="1" CELLBORDER="1" CELLSPACING="0" CELLPADDING="4" COLOR="${stroke}" BGCOLOR="${fill}">${rows}</TABLE>>];`);}
for(const r of relations){const child=r.unique?'odottee':'odotcrow';const parent=r.nullable?'odottee':'teetee';physical.push(`${r.parent}:e -> ${r.child}:w [constraint=false,dir=both,arrowtail=${parent},arrowhead=${child},tooltip="${r.child}.${r.column} references ${r.parent}.${r.key}"];`);}
const ranks=[['roles','users','permissions','audit_logs','system_settings','jobs'],['auth_sessions','conversations','products','documents'],['messages','inventory','sales','document_chunks','workflows'],['workflow_steps','tool_executions','workflow_events','reports','usage_records','approval_requests'],['approval_decisions']];
for(const [i,names] of ranks.entries()){physical.push(`anchor${i} [shape=point,width=0,style=invis]; {rank=same; anchor${i}; ${names.join(';')};}`);if(i)physical.push(`anchor${i-1} -> anchor${i} [style=invis,weight=100];`);}
physical.push('legend [shape=plain,label=<<TABLE BORDER="1" CELLBORDER="0" CELLPADDING="6"><TR><TD><B>Notation</B></TD></TR><TR><TD ALIGN="LEFT">PK primary key · FK foreign key · UQ unique · ? nullable</TD></TR><TR><TD ALIGN="LEFT">Crow foot = many · circle = optional · bar = one</TD></TR><TR><TD ALIGN="LEFT">permissions, audit_logs, system_settings, jobs have no FK.</TD></TR><TR><TD ALIGN="LEFT">JSON references are not foreign keys.</TD></TR></TABLE>>];');
physical.push('}');
const physicalDot=physical.join('\n');

// Full Chen notation. Every mapped column is a distinct oval; no fabricated JSON relationships.
let chen=['graph APBWAS_Chen {',
'graph [bgcolor="white",pad="0.3",overlap=true,splines=true,outputorder=edgesfirst,pack=false,notranslate=true,label="APBWAS Entity Relationship Diagram\\nChen notation · 22 entities · 143 attributes · 21 relationships",labelloc=t,fontsize=30,fontname="Times New Roman"];',
'node [fontname="Times New Roman",fontsize=12,color="#52525B",penwidth=1.0];',
'edge [color="#71717A",penwidth=1.1,fontsize=14,fontname="Times New Roman"];'];
const grid=[['roles','auth_sessions','system_settings','audit_logs'],['users','conversations','documents','document_chunks'],['permissions','messages','workflow_steps','tool_executions'],['approval_decisions','approval_requests','workflows','workflow_events'],['products','inventory','reports','usage_records'],['sales','jobs']];
const positions={},occupied=[];const at=(x,y)=>`pos="${x/72},${y/72}!",pin=true`;
for(const [row,names] of grid.entries())for(const [col,name] of names.entries())positions[name]=[400+col*930,300+(5-row)*700];
for(const name of order){const t=byName[name];const [x,y]=positions[name];chen.push(`${name} [shape=box,style=filled,fillcolor="#FAFAFA",label="${name.toUpperCase()}",fontsize=20,margin="0.15,0.12",${at(x,y)}];`);occupied.push([x-145,y-28,x+145,y+28]);
for(const [i,c] of t.columns.entries()){const id=`${name}__${c.name}`;const label=c.pk?`<<U>${c.name}</U>>`:`"${c.name}"`;const angle=(2*Math.PI*i/t.columns.length)-Math.PI/2;const ax=x+335*Math.cos(angle),ay=y+235*Math.sin(angle);const width=Math.max(110,c.name.length*8.5+24);occupied.push([ax-width/2,ay-22,ax+width/2,ay+22]);chen.push(`${id} [shape=ellipse,label=${label},fontsize=17,margin="0.11,0.08",${at(ax,ay)}];`);chen.push(`${name} -- ${id};`);}}
const labels={roles:'assigned to',users:'owns',conversations:'contains',workflows:'records',products:'has',documents:'contains',approval_requests:'receives'};
for(const [i,r] of relations.entries()){const id='rel_'+i;let label=labels[r.parent]||'belongs to';if(r.parent==='users')label=r.column==='user_id'?'owns':'assigned';if(r.child==='approval_decisions'&&r.parent==='users')label='decides';if(r.child==='approval_requests'&&r.parent==='workflows')label='requires';if(r.parent==='products'&&r.child==='sales')label='records';
const [px,py]=positions[r.parent],[cx,cy]=positions[r.child];let candidate;
for(const off of [0,80,-80,160,-160,240,-240,320,-320]){for(const t of [.5,.35,.65,.2,.8]){const x=px+(cx-px)*t+off,y=py+(cy-py)*t+off/2;const box=[x-80,y-38,x+80,y+38];if(!occupied.some(b=>box[0]<b[2]&&box[2]>b[0]&&box[1]<b[3]&&box[3]>b[1])){candidate=[x,y];occupied.push(box);break;}}if(candidate)break;}
candidate??=[(px+cx)/2,(py+cy)/2+100];
chen.push(`${id} [shape=diamond,label="${label}",fontsize=16,width=1.5,height=0.85,margin=0.06,${at(...candidate)}];`);
chen.push(`${r.parent} -- ${id} [taillabel="${r.nullable?'0..1':'1'}",labeldistance=1.6];`);
chen.push(`${id} -- ${r.child} [headlabel="${r.unique?'0..1':'0..N'}",labeldistance=1.6,tooltip="${r.child}.${r.column}"];`);}
chen.push(`legend [shape=plain,${at(2300,250)},label=<<TABLE BORDER="1" CELLBORDER="0" CELLPADDING="10"><TR><TD><B>Chen notation</B></TD></TR><TR><TD ALIGN="LEFT">Rectangle = entity · oval = attribute · diamond = relationship</TD></TR><TR><TD ALIGN="LEFT">Underlined attribute = primary key</TD></TR><TR><TD ALIGN="LEFT">1 = exactly one · 0..1 = optional one · 0..N = zero or many</TD></TR><TR><TD ALIGN="LEFT">Only declared foreign keys form relationships.</TD></TR></TABLE>>];`);chen.push('}');
for(const [name,dot,engine] of [['APBWAS_Table_Relationship_Diagram',physicalDot,'dot'],['APBWAS_Entity_Relationship_Diagram',chen.join('\n'),'neato']]){
fs.writeFileSync(path.join(out,name+'.dot'),dot);
const svg=viz.renderString(dot,{format:'svg',engine});fs.writeFileSync(path.join(out,name+'.svg'),svg);
const size=await sharp(Buffer.from(svg)).metadata();
await sharp(Buffer.from(svg),{density:72,limitInputPixels:false}).resize({width:6500,withoutEnlargement:false}).png().toFile(path.join(out,name+'.png'));
await sharp(Buffer.from(svg),{density:40,limitInputPixels:false}).resize({width:1500}).png().toFile(path.join(out,name+'-preview.png'));
console.log(name,JSON.stringify({width:size.width,height:size.height}));
}
fs.writeFileSync(path.join(out,'validation.json'),JSON.stringify({tables:tables.length,columns:tables.reduce((s,t)=>s+t.columns.length,0),foreign_keys:relations.length,chen_entities:22,chen_attributes:143,chen_relationships:relations.length},null,2));
