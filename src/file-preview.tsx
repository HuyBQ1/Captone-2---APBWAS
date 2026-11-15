import {useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {Download,ChevronLeft,ChevronRight,Maximize2,Minimize2} from 'lucide-react';
import {api,Row} from './api';
import {Modal,Loading,ErrorBox} from './ui';

export function FilePreview({file,onClose}:{file:Row;onClose:()=>void}){
 const [sheet,setSheet]=useState(0),[page,setPage]=useState(1),[formulas,setFormulas]=useState(false);
 const [expanded,setExpanded]=useState(false),[fit,setFit]=useState(true);
 const q=useQuery({queryKey:['file-preview',file.id,sheet,page],queryFn:()=>api(`/files/${file.id}/preview?sheet=${sheet}&page=${page}`),gcTime:0,retry:false});
 const data=q.data;
 return <Modal wide className={'file-preview-modal '+(expanded?'preview-expanded':'')} title={'Xem trước · '+file.title} onClose={onClose}><div className="file-preview-toolbar"><p>{file.filename}</p><div className="preview-actions"><button type="button" className="btn secondary" aria-pressed={expanded} onClick={()=>setExpanded(v=>!v)}>{expanded?<Minimize2 size={15}/>:<Maximize2 size={15}/>} {expanded?'Thu gọn':'Toàn màn hình'}</button><a className="btn primary" href={file.download_url}><Download size={15}/>Tải {file.kind==='xlsx'?'Excel':'Word'}</a></div></div>
 <p className="subtle">Xem nội dung từ tệp đã lưu. Tải file để giữ đầy đủ định dạng trong Word hoặc Excel.</p>
 {q.isLoading?<Loading/>:q.error?<ErrorBox error={q.error} retry={()=>q.refetch()}/>:data?.kind==='xlsx'?<>
 <div className="preview-sheet-tabs" role="tablist" aria-label="Trang tính">{data.sheets.map((s:Row)=><button key={s.index} type="button" role="tab" aria-selected={s.index===sheet} onClick={()=>{setSheet(s.index);setPage(1)}}>{s.name}</button>)}</div>
 <div className="preview-display-options"><label className="checkbox preview-formula-toggle"><input type="checkbox" checked={formulas} onChange={e=>setFormulas(e.target.checked)}/>Hiện công thức</label><label className="checkbox preview-formula-toggle"><input type="checkbox" checked={fit} onChange={e=>setFit(e.target.checked)}/>Vừa chiều ngang</label></div>
 <div className={'spreadsheet-preview '+(fit?'preview-fit':'')} role="region" aria-label="Bảng xem trước Excel" tabIndex={0}><table><colgroup><col style={{width:40}}/>{data.columns.map((col:string)=><col key={col}/>)}</colgroup><thead><tr><th aria-label="Số dòng"/>{data.columns.map((col:string)=><th key={col} scope="col">{col}</th>)}</tr></thead><tbody>{data.rows.map((r:Row)=><tr key={r.number}><th scope="row">{r.number}</th>{r.cells.map((c:Row,i:number)=><td key={i} className={typeof c.value==='number'?'numeric':''} title={c.formula||undefined} data-formula={c.formula||undefined}>{formulas&&c.formula?<code>{c.formula}</code>:c.missing_cache?<span className="subtle">Chưa có kết quả tính sẵn</span>:c.display}</td>)}</tr>)}</tbody></table></div>
 <div className="preview-pagination"><span>{data.total_rows} dòng · Trang {data.page}/{data.pages}</span><div><button type="button" className="btn secondary" aria-label="Trang dữ liệu trước" disabled={page<=1} onClick={()=>setPage(p=>p-1)}><ChevronLeft size={16}/></button><button type="button" className="btn secondary" aria-label="Trang dữ liệu sau" disabled={page>=data.pages} onClick={()=>setPage(p=>p+1)}><ChevronRight size={16}/></button></div></div>
 </>:data?.kind==='docx'?<><div className="word-preview" role="region" aria-label="Nội dung xem trước Word">{data.blocks.map((b:Row,i:number)=>b.type==='table'?<div className="word-preview-table" key={i}><table><thead><tr>{b.rows[0]?.map((c:string,j:number)=><th key={j}>{c}</th>)}</tr></thead><tbody>{b.rows.slice(1).map((r:string[],j:number)=><tr key={j}>{r.map((c,k)=><td key={k}>{c}</td>)}</tr>)}</tbody></table>{b.truncated&&<p>Chỉ hiển thị 200 dòng đầu của bảng. Tải Word để xem đầy đủ.</p>}</div>:b.style==='Title'?<h2 key={i}>{b.text}</h2>:b.style?.startsWith('Heading')?<h3 key={i}>{b.text}</h3>:<p key={i} className={b.style?.includes('List')?'word-preview-list':''}>{b.style?.includes('List')?'• ':''}{b.text}</p>)}</div>{data.truncated&&<p className="subtle">Đang hiển thị 300 khối nội dung đầu. Tải file để đọc đầy đủ.</p>}</>:null}
 </Modal>
}
