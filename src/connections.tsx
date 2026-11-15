import {useRef,useState} from 'react';
import {Link,useNavigate} from 'react-router-dom';
import {useQuery,useQueryClient} from '@tanstack/react-query';
import {ArrowUpRight,FileText,FileSpreadsheet,Mail,Plug,Upload,ShieldCheck,ArrowLeft} from 'lucide-react';
import {api} from './api';
import {useUser} from './main';
import {PageHeader,useToast,Busy} from './ui';
import {FinancePanel} from './finance';
import {ShopConnection} from './shop-connection';

export function ConnectionIcon({kind}:{kind:string}){
 return <span className={'connection-icon '+kind} aria-hidden="true">{kind==='gmail'?<Mail size={30}/>:<><span className="connection-paper">{kind==='excel'||kind==='csv'?<FileSpreadsheet size={31}/>:<FileText size={31}/>}</span><b>{({word:'W',excel:'X',pdf:'PDF',csv:'CSV',text:'TXT'} as Record<string,string>)[kind]}</b></>}</span>
}

export function Connections(){
 const user=useUser(),nav=useNavigate(),toast=useToast(),client=useQueryClient(),picker=useRef<HTMLInputElement>(null);
 const [busy,setBusy]=useState(false),[format,setFormat]=useState('.docx');
 const can=(p:string)=>user.permissions.includes(p),canFinance=can('sales.read')&&can('inventory.read'),canConnect=can('mail.connect')||can('mail.send');
 const gmail=useQuery({queryKey:['gmail-status'],queryFn:()=>api('/mail/status'),enabled:canConnect});
 const choose=(extension:string)=>{setFormat(extension);if(picker.current){picker.current.accept=extension;picker.current.click()}};
 const upload=async(file:File)=>{
  if(!file.name.toLowerCase().endsWith(format)||!file.size||file.size>10*1024*1024){toast('Chọn đúng định dạng '+format+', từ 1 byte đến 10 MB.');return}
  setBusy(true);try{const body=new FormData();body.append('file',file);const doc=await api('/documents',{method:'POST',body});await client.invalidateQueries({queryKey:['documents']});nav('/knowledge/'+doc.id);toast('Đã lưu tài liệu. Hệ thống đang xử lý để AI có thể tra cứu.')}catch(e:any){toast(e.message)}finally{setBusy(false)}
 };
 const files=[{kind:'word',name:'Microsoft Word',extension:'.docx',description:'Đưa hợp đồng, quy trình và chính sách vào kho tri thức. AI tra cứu nội dung và dẫn nguồn.'},
 {kind:'pdf',name:'PDF',extension:'.pdf',description:'Đọc tài liệu PDF có văn bản, lưu bản gốc và tìm kiếm nội dung trong AI Workspace.'},
 {kind:'text',name:'Tệp văn bản',extension:'.txt',description:'Nạp ghi chú và hướng dẫn dạng TXT UTF-8 để AI có thể tra cứu cùng tài liệu nội bộ.'}];
 return <><PageHeader eyebrow="APPS & DATA" title="Kết nối" description="Email, tài liệu và bảng tính của doanh nghiệp trong một không gian." action={<Link className="btn secondary" to="/workspace"><Plug size={16}/>Mở AI Workspace</Link>}/>
 <section className="connections-intro card"><div><span className="eyebrow">CÔNG CỤ CỦA BẠN</span><h2>Chọn ứng dụng để bắt đầu</h2><p>Gửi email, thêm tài liệu cho AI hoặc làm việc với số liệu Excel. Mỗi ứng dụng hiển thị cách sử dụng và quyền truy cập hiện có.</p></div><span className="connections-art" aria-hidden="true"><Plug size={48}/></span></section>
 <input ref={picker} type="file" className="connection-file-input" aria-label="Chọn tệp kết nối" disabled={busy} accept={format} onChange={e=>{const file=e.target.files?.[0];e.target.value='';if(file)upload(file)}}/>
 <div className="connections-grid">
 <ShopConnection/>
 <article className="card connection-card"><div className="connection-card-top"><ConnectionIcon kind="gmail"/><span className={'connection-state '+(gmail.data?.connected?'online':'')}>{!canConnect?'Cần quyền kết nối':gmail.isError?'Chưa tải được trạng thái':gmail.isLoading?'Đang kiểm tra…':gmail.data?.connected?'Đã kết nối':'Chưa kết nối'}</span></div><h2>Gmail</h2><span className="connection-mode">TÀI KHOẢN GOOGLE</span><p>{can('mail.send')?'Kết nối Gmail để soạn và gửi email cho nhân viên. Xem trước nội dung, người nhận và theo dõi từng lượt gửi.':'Kết nối Gmail cá nhân. Bạn chỉ được gửi thư thử đến chính mình; chưa có quyền gửi thư cho người khác hoặc gửi hàng loạt.'}</p>{gmail.data?.connected&&<small className="connection-account">{gmail.data.email}</small>}<div className="connection-card-actions">{canConnect?<><Link className="btn primary" to="/mail"><Mail size={16}/>Quản lý Gmail</Link>{can('mail.send')&&<Link className="text-link" to="/mail/employees">Soạn email <ArrowUpRight size={15}/></Link>}</>:<span className="subtle">Liên hệ Admin để được cấp quyền kết nối Gmail.</span>}</div></article>
 <article className="card connection-card"><div className="connection-card-top"><ConnectionIcon kind="word"/><span className="connection-state">{can('documents.read')?'Sẵn sàng qua tệp':'Cần quyền tài liệu'}</span></div><h2>Microsoft Word</h2><span className="connection-mode">TỆP DOCX · TỐI ĐA 10 MB</span><p>{files[0].description}</p><FileActions canRead={can('documents.read')} canWrite={can('documents.write')} busy={busy} name="Word" onUpload={()=>choose('.docx')}/></article>
 <article className="card connection-card"><div className="connection-card-top"><ConnectionIcon kind="excel"/><span className="connection-state">{canFinance?'Sẵn sàng qua tệp':'Cần quyền tài chính'}</span></div><h2>Microsoft Excel</h2><span className="connection-mode">TỆP XLSX · MẪU APBWAS</span><p>Xuất báo cáo có công thức tính doanh thu, giá vốn và lợi nhuận. Admin có thể nhập lại số liệu theo mẫu sau khi xem trước.</p><div className="connection-card-actions">{canFinance?<Link className="btn primary" to="/connections/excel"><FileSpreadsheet size={16}/>Mở Excel tài chính</Link>:<span className="subtle">Cần quyền đọc doanh thu và tồn kho.</span>}</div></article>
 {files.slice(1).map(item=><article className="card connection-card" key={item.kind}><div className="connection-card-top"><ConnectionIcon kind={item.kind}/><span className="connection-state">{can('documents.read')?'Sẵn sàng qua tệp':'Cần quyền tài liệu'}</span></div><h2>{item.name}</h2><span className="connection-mode">TỆP {item.extension.toUpperCase()} · TỐI ĐA 10 MB</span><p>{item.description}</p><FileActions canRead={can('documents.read')} canWrite={can('documents.write')} busy={busy} name={item.kind==='pdf'?'PDF':'TXT'} onUpload={()=>choose(item.extension)}/></article>)}
 <article className="card connection-card"><div className="connection-card-top"><ConnectionIcon kind="csv"/><span className="connection-state">{can('sales.read')?'Sẵn sàng xuất tệp':'Cần quyền báo cáo'}</span></div><h2>Báo cáo CSV</h2><span className="connection-mode">XUẤT DỮ LIỆU</span><p>Tải báo cáo doanh thu dạng CSV để mở trong Excel hoặc xử lý với các công cụ bảng tính khác.</p><div className="connection-card-actions">{can('sales.read')?<Link className="btn secondary" to="/reports">Mở báo cáo <ArrowUpRight size={16}/></Link>:<span className="subtle">Liên hệ Admin để được cấp quyền đọc báo cáo.</span>}</div></article>
 </div><div className="connections-note"><ShieldCheck size={20}/><p>Word, Excel, PDF và TXT hiện làm việc qua tệp tải lên hoặc tải xuống. Chưa đồng bộ trực tiếp với tài khoản Microsoft 365, OneDrive hay Google Drive. Gmail sử dụng kết nối tài khoản Google đã cấp quyền.</p></div></>
}

function FileActions({canRead,canWrite,busy,name,onUpload}:{canRead:boolean;canWrite:boolean;busy:boolean;name:string;onUpload:()=>void}){
 return <div className="connection-card-actions">{canWrite&&<button className="btn primary" disabled={busy} onClick={onUpload}><Upload size={16}/><Busy busy={busy} label={'Thêm tệp '+name}/></button>}{canRead?<Link className={canWrite?'text-link':'btn secondary'} to="/knowledge">Mở kho tri thức <ArrowUpRight size={15}/></Link>:<span className="subtle">Cần quyền đọc tài liệu.</span>}</div>
}

export function ExcelConnection(){
 const user=useUser(),allowed=['sales.read','inventory.read'].every(p=>user.permissions.includes(p));
 return <><Link className="back-link" to="/connections"><ArrowLeft size={15}/>Trở về kết nối</Link><PageHeader title="Microsoft Excel" description="Nhập và xuất bảng tính theo mẫu APBWAS. Dữ liệu tài chính được đọc từ database."/>{allowed?<FinancePanel/>:<section className="card padded"><h2>Cần quyền truy cập tài chính</h2><p>Liên hệ Admin để được cấp quyền đọc doanh thu và tồn kho.</p></section>}</>
}
