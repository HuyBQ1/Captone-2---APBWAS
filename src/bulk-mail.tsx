import {useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {Link,useNavigate,useParams} from 'react-router-dom';
import {api,post,date} from './api';
import {PageHeader,Loading,ErrorBox,useToast,Busy,Modal} from './ui';
import {FilePreview} from './file-preview';

const labels:Record<string,string>={draft:'Bản nháp',queued:'Trong hàng đợi',sending:'Đang gửi',pending:'Chưa gửi',sent:'Google đã nhận',completed:'Hoàn tất',partial:'Hoàn tất một phần',unknown:'Chưa xác định',failed:'Thất bại',skipped:'Bỏ qua',cancelled:'Đã dừng'};

export function EmployeeMail(){
 const nav=useNavigate(),toast=useToast(),[subject,setSubject]=useState(''),[body,setBody]=useState(''),[all,setAll]=useState(true),[selected,setSelected]=useState<string[]>([]),[busy,setBusy]=useState(false),[key]=useState(()=>crypto.randomUUID());
 const q=useQuery({queryKey:['mail-employees'],queryFn:()=>api('/mail/employees')});
 const history=useQuery({queryKey:['mail-campaigns'],queryFn:()=>api<any[]>('/mail/campaigns'),refetchInterval:5000});
 if(q.isLoading)return <Loading/>;if(q.error)return <ErrorBox error={q.error}/>;const data=q.data!;
 return <><PageHeader title="Email cho nhân viên" description="Chọn người nhận, lưu bản nháp và kiểm tra trước khi gửi. Mỗi người nhận một email riêng." action={<Link to="/mail" className="btn secondary">Kết nối Gmail</Link>}/>
 <section className="card padded mail-section"><h2>1. Địa chỉ nhận thư</h2><p>Đăng nhập bằng tài khoản Admin để cập nhật email nhận thư thật của nhân viên. Địa chỉ này không thay đổi email đăng nhập.</p>
 {data.items.map((u:any)=><Contact key={u.id} u={u} editable={data.can_manage||data.current_user_id===u.id} refresh={()=>q.refetch()}/>)}
 {!data.items.some((u:any)=>u.ready)&&<p className="error-text" role="alert">Chưa có địa chỉ nhận thư thật. Email mẫu .example không nhận được thư.</p>}</section>
 <section className="card padded mail-section"><h2>2. Soạn email</h2><form onSubmit={async e=>{e.preventDefault();setBusy(true);try{const c=await post('/mail/campaigns',{subject,body_text:body,recipient_ids:all?null:selected,idempotency_key:key});nav('/mail/campaigns/'+c.id)}catch(e:any){toast(e.message)}finally{setBusy(false)}}}>
 <label><input type="checkbox" checked={all} onChange={e=>setAll(e.target.checked)}/> Tất cả nhân viên đang hoạt động (gồm Admin, Manager)</label>
 {!all&&<div className="mail-people">{data.items.map((u:any)=><label key={u.id}><input type="checkbox" checked={selected.includes(u.id)} onChange={e=>setSelected(e.target.checked?[...selected,u.id]:selected.filter(id=>id!==u.id))}/>{u.name} · {u.recipient||'Thiếu email thật'}</label>)}</div>}
 <label>Tiêu đề<input required maxLength={180} value={subject} onChange={e=>setSubject(e.target.value)}/></label>
 <label>Nội dung<textarea aria-label="Nội dung" required rows={9} maxLength={20000} value={body} onChange={e=>setBody(e.target.value)}/></label>
 <button className="btn primary" disabled={busy||!all&&!selected.length}><Busy busy={busy} label="Lưu và xem trước"/></button></form>
 <p className="subtle">Bạn cũng có thể yêu cầu AI Workspace soạn email. AI tạo bản nháp để bạn xem và xác nhận; chưa gửi ngay.</p></section>
 <section className="card padded mail-section"><h2>Lịch sử gửi của bạn</h2>{history.error?<ErrorBox error={history.error}/>:history.data?.length?history.data.map(c=><div className="mail-history" key={c.id}><Link to={'/mail/campaigns/'+c.id}>{c.subject}</Link><span>{labels[c.status]} · {date(c.created_at)}</span></div>):<p>Chưa có bản nháp.</p>}</section></>
}

function Contact({u,editable,refresh}:{u:any;editable:boolean;refresh:()=>void}){
 const [value,setValue]=useState(u.delivery_email||''),[busy,setBusy]=useState(false),toast=useToast();
 return <div className="mail-contact"><div><b>{u.name}</b><small>{u.role} · {u.login_email}</small><small>{u.ready?'Nhận thư tại: '+u.recipient:'Cần bổ sung email thật'}</small></div>{editable&&<form onSubmit={async e=>{e.preventDefault();setBusy(true);try{await api('/mail/employees/'+u.id,{method:'PUT',body:JSON.stringify({delivery_email:value})});refresh();toast('Đã lưu email nhận thư.')}catch(e:any){toast(e.message)}finally{setBusy(false)}}}><input aria-label={'Email nhận thư của '+u.name} type="email" maxLength={180} value={value} onChange={e=>setValue(e.target.value)} placeholder="nhanvien@gmail.com"/><button className="btn secondary" disabled={busy}>Lưu</button></form>}</div>
}

export function MailCampaign(){
 const [preview,setPreview]=useState<any>(null);
 const {id}=useParams(),toast=useToast(),[confirm,setConfirm]=useState(false),[busy,setBusy]=useState(false),[edit,setEdit]=useState<{subject:string;body_text:string;revision:number}|null>(null);
 const q=useQuery({queryKey:['mail-campaign',id],queryFn:()=>api('/mail/campaigns/'+id),refetchInterval:3000});
 const gmail=useQuery({queryKey:['gmail-status'],queryFn:()=>api('/mail/status')});
 if(q.isLoading)return <Loading/>;if(q.error)return <ErrorBox error={q.error}/>;const c=q.data!;
 const send=async()=>{setBusy(true);try{await post('/mail/campaigns/'+id+'/send',{confirmed:true,revision:c.revision});setConfirm(false);await q.refetch();toast('Đã đưa thư vào hàng đợi. Theo dõi kết quả từng người bên dưới.')}catch(e:any){toast(e.message)}finally{setBusy(false)}};
 return <><PageHeader title={c.subject} description={'Trạng thái: '+labels[c.status]} action={<Link className="btn secondary" to="/mail/employees">Trở về email nhân viên</Link>}/>
 <section className="card padded mail-section"><p>Người gửi: <b>{c.sender_email||gmail.data?.email||'Chưa kết nối Gmail'}</b></p><h3>Nội dung sẽ gửi</h3><div className="mail-preview">{c.body_text}</div>
 {!!c.attachments?.length&&<section aria-label="Tệp đính kèm email"><h3>Tệp đính kèm ({c.attachments.length})</h3>{c.attachments.map((f:any)=><div className="mail-history" key={f.id}><div><b>{f.title}</b><small>{f.filename} · {Math.ceil(f.size/1024)} KB</small></div><button type="button" className="btn secondary" onClick={()=>setPreview(f)}>Xem trước tệp</button><a className="btn secondary" href={f.download_url}>Tải tệp</a></div>)}</section>}
 {c.attachment_error&&<p className="error-text" role="alert">{c.attachment_error}</p>}
 <h3>Người nhận ({c.recipients.length})</h3><p>Mỗi địa chỉ nhận một thư riêng; không hiển thị email của nhân viên khác.</p>
 {c.recipients.map((r:any)=><div className="mail-history" key={r.id}><div><b>{r.name}</b><small>{r.email}</small>{r.error&&<small>{r.error}</small>}</div><span>{labels[r.status]}</span></div>)}
 {!!c.skipped.length&&<div className="finance-note"><h3>Không gửi cho {c.skipped.length} nhân viên</h3>{c.skipped.map((r:any)=><p key={r.id}>{r.name}: {r.reason}</p>)}<p>Cập nhật email ở danh sách nhân viên rồi tạo bản nháp mới để bổ sung những người này.</p></div>}
 {c.error&&<p role="alert">{c.error}</p>}
 {c.status==='draft'&&<><p>Kiểm tra kỹ nội dung và danh sách trên. Giới hạn mặc định của ứng dụng là 100 thư trong 24 giờ.</p><button className="btn secondary" disabled={busy} onClick={()=>setEdit({subject:c.subject,body_text:c.body_text,revision:c.revision})}>Chỉnh sửa nội dung</button><button className="btn primary" disabled={busy||!c.recipients.length||!gmail.data?.connected} onClick={()=>setConfirm(true)}>Xem xác nhận gửi</button>{!gmail.data?.connected&&<Link className="text-link" to="/mail">Kết nối Gmail trước khi gửi</Link>}</>}
 {['draft','queued','sending'].includes(c.status)&&<button className="btn secondary" disabled={busy||c.cancel_requested} onClick={async()=>{setBusy(true);try{await post('/mail/campaigns/'+id+'/cancel');await q.refetch();toast('Đã yêu cầu dừng những thư chưa gửi.')}catch(e:any){toast(e.message)}finally{setBusy(false)}}}>{c.cancel_requested?'Đã yêu cầu dừng':'Dừng đợt gửi'}</button>}
 <p className="subtle">“Google đã nhận” nghĩa là Google chấp nhận yêu cầu gửi, không xác nhận thư đã vào hộp thư đến. Nếu kết quả chưa xác định, kiểm tra Thư đã gửi trong Gmail trước khi tạo đợt gửi mới. Dừng đợt gửi không thu hồi thư đã gửi.</p></section>
 {preview&&<FilePreview file={preview} onClose={()=>setPreview(null)}/>}
 {confirm&&<Modal title="Xác nhận gửi email cho nhân viên" onClose={()=>setConfirm(false)}><p>Gửi từ <b>{gmail.data?.email}</b> tới <b>{c.recipients.length} địa chỉ</b> trong danh sách đã xem.</p><p>Tiêu đề: <b>{c.subject}</b></p><p>Tệp đính kèm: {c.attachments?.length||0}</p><p>Sau khi xác nhận, worker sẽ gửi thư thật. Các thư đã gửi không thể thu hồi tại đây.</p><button className="btn primary" disabled={busy||!!c.attachment_error} onClick={send}><Busy busy={busy} label="Xác nhận gửi ngay"/></button></Modal>}
 {edit&&<Modal title="Chỉnh sửa bản nháp" onClose={()=>setEdit(null)}><form onSubmit={async e=>{e.preventDefault();setBusy(true);try{await api('/mail/campaigns/'+id,{method:'PUT',body:JSON.stringify(edit)});await q.refetch();setEdit(null);toast('Đã lưu bản nháp mới. Hãy kiểm tra lại trước khi gửi.')}catch(e:any){toast(e.message)}finally{setBusy(false)}}}><label>Tiêu đề<input required maxLength={180} value={edit.subject} onChange={e=>setEdit({...edit,subject:e.target.value})}/></label><label>Nội dung<textarea aria-label="Nội dung" required rows={9} maxLength={20000} value={edit.body_text} onChange={e=>setEdit({...edit,body_text:e.target.value})}/></label><button className="btn primary" disabled={busy}>Lưu thay đổi</button></form></Modal>}</>
}
