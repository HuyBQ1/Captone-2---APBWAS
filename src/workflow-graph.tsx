import {Link} from 'react-router-dom';
import {ReactFlow,Background,Controls,Position,MarkerType} from '@xyflow/react';
import {Row,statusLabels} from './api';
import {Empty} from './ui';

function stateText(stage:Row){return stage.status==='waiting_approval'&&stage.basis==='live_email'?'Chờ bạn xác nhận':stage.status==='queued'&&stage.basis==='live_email'?'Chưa gửi':statusLabels[stage.status]||stage.status}

export function WorkflowGraph({workflow:w}:{workflow:Row}){
 const graph=w.execution_graph;
 const stages:Row[]=graph?.stages||w.plan.map((s:Row,i:number)=>({id:'tool-'+i,label:s.label,status:w.steps.find((x:Row)=>x.position===i)?.status||'queued',description:'Bước công cụ trong kế hoạch.'}));
 const columns=Math.min(3,stages.length),rows=Math.ceil(stages.length/Math.max(1,columns));
 const list=()=>stages.map((s:Row,i:number)=><li key={s.id} className={s.status}><span className="stage-number">{i+1}</span><div><b>{s.label}</b><span className={'stage-state '+s.status}>{stateText(s)}</span>{s.description&&<p>{s.description}</p>}{s.href&&<Link className="text-link" to={s.href}>Mở email</Link>}</div></li>);
 return <section className="card workflow-graph"><div className="card-head"><h3>Kế hoạch & quan hệ phụ thuộc</h3><span className="subtle">{graph?.tool_count??w.plan.length} công cụ · {stages.length} giai đoạn</span></div>{stages.length?<><div className="flow-canvas workflow-stage-canvas" style={{height:Math.min(620,Math.max(240,rows*150+45))}}><ReactFlow key={stages.map(s=>s.id).join('|')} nodes={stages.map((s:Row,i:number)=>{
  const row=Math.floor(i/columns),column=row%2?columns-1-i%columns:i%columns;
  return {id:s.id,position:{x:column*270,y:row*150},sourcePosition:i%columns===columns-1?Position.Bottom:row%2?Position.Left:Position.Right,targetPosition:i>0&&i%columns===0?Position.Top:row%2?Position.Right:Position.Left,
   data:{label:<div title={s.description}><span className="stage-kicker">GIAI ĐOẠN {i+1}</span><b>{s.label}</b><small className={'stage-state '+s.status}>{stateText(s)}</small>{s.href&&<Link className="text-link nodrag" to={s.href}>Mở email</Link>}</div>},className:'flow-node stage-node '+s.status};
 })} edges={stages.slice(1).map((s:Row,i:number)=>({id:'edge-'+s.id,source:stages[i].id,target:s.id,type:'smoothstep',markerEnd:{type:MarkerType.ArrowClosed},animated:s.status==='running'}))} fitView fitViewOptions={{padding:.12,maxZoom:1}} minZoom={.2} maxZoom={1.5} nodesDraggable={false} nodesConnectable={false}><Background gap={20}/><Controls showInteractive={false}/></ReactFlow></div><ol className="stage-mobile-list" aria-label="Các giai đoạn thực thi">{list()}</ol>{graph?.note&&<p className="stage-graph-note">{graph.note}</p>}<details className="stage-desktop-details"><summary>Xem mô tả từng giai đoạn</summary><ol aria-label="Chi tiết giai đoạn">{list()}</ol></details></>:<Empty text="Không có giai đoạn thực thi được lưu cho lượt chạy này."/>}</section>
}
