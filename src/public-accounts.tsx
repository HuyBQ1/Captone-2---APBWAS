import {useState} from 'react';
import {Link} from 'react-router-dom';
import {useQuery,useQueryClient} from '@tanstack/react-query';
import {Layers,ArrowLeft,CheckCircle2} from 'lucide-react';
import {api,post,Row,date} from './api';
import {Busy,ErrorBox,useToast} from './ui';

export function RegisterPage(){
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
 return <div className="public-auth-page"><section className="card public-auth-card"><Link className="public-auth-brand" to="/"><Layers size={27}/>APBWAS</Link><h1>Tạo tài khoản</h1><p>Tài khoản nhân viên cần quản trị viên duyệt trước khi truy cập dữ liệu công ty.</p>{message?<div role="status"><CheckCircle2 size={28}/><p>{message}</p><Link className="btn primary full" to="/login">Trở về đăng nhập</Link></div>:<form onSubmit={async e=>{e.preventDefault();setError('');const f=new FormData(e.currentTarget);if(f.get('password')!==f.get('confirm')){setError('Mật khẩu xác nhận chưa khớp.');return}setBusy(true);try{const r=await post('/auth/register',{name:f.get('name'),email:f.get('email'),password:f.get('password')});setMessage(r.message)}catch(err:any){setError(err.message)}finally{setBusy(false)}}}><label>Họ và tên<input name="name" autoComplete="name" minLength={2} maxLength={120} required/></label><label>Email đăng nhập<input name="email" type="email" autoComplete="username" maxLength={180} required/></label><label>Mật khẩu<input name="password" type="password" autoComplete="new-password" minLength={10} maxLength={128} required/></label><small>Tối thiểu 10 ký tự.</small><label>Xác nhận mật khẩu<input name="confirm" type="password" autoComplete="new-password" minLength={10} maxLength={128} required/></label>{error&&<p role="alert" className="error-text">{error}</p>}<button className="btn primary full" disabled={busy}><Busy busy={busy} label="Tạo tài khoản"/></button><Link className="back-link" to="/login"><ArrowLeft size={15}/>Đã có tài khoản? Đăng nhập</Link></form>}</section></div>
}

export function ForgotPasswordPage(){
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
 return <div className="public-auth-page"><section className="card public-auth-card"><Link className="public-auth-brand" to="/"><Layers size={27}/>APBWAS</Link><h1>Quên mật khẩu</h1><p>Nhập email đăng nhập để yêu cầu liên kết đặt lại mật khẩu. Liên kết chỉ dùng một lần và có hiệu lực 1 giờ.</p>{message?<div role="status"><CheckCircle2 size={28}/><p>{message}</p><p>Không chia sẻ liên kết khôi phục cho người khác.</p><Link className="btn primary full" to="/login">Trở về đăng nhập</Link></div>:<form onSubmit={async e=>{e.preventDefault();setError('');setBusy(true);const f=new FormData(e.currentTarget);try{const r=await post('/auth/forgot-password',{email:f.get('email')});setMessage(r.message)}catch(err:any){setError(err.message)}finally{setBusy(false)}}}><label>Email đăng nhập<input name="email" type="email" autoComplete="username" maxLength={180} required/></label>{error&&<p role="alert" className="error-text">{error}</p>}<button className="btn primary full" disabled={busy}><Busy busy={busy} label="Gửi liên kết khôi phục"/></button><Link className="back-link" to="/login"><ArrowLeft size={15}/>Trở về đăng nhập</Link></form>}</section></div>
}

export function RegistrationsAdmin(){
 const [busy,setBusy]=useState(''),toast=useToast(),client=useQueryClient();
 const query=useQuery({queryKey:['registrations'],queryFn:()=>api('/admin/registrations'),refetchInterval:10000});
 if(query.error)return <ErrorBox error={query.error}/>;
 if(!query.data?.items?.length)return null;
 async function decide(id:string,action:string){setBusy(id);try{await post('/admin/registrations/'+id+'/'+action);await Promise.all([client.invalidateQueries({queryKey:['registrations']}),client.invalidateQueries({queryKey:['users']})]);toast(action==='approve'?'Đã duyệt tài khoản nhân viên.':'Đã từ chối yêu cầu đăng ký.')}catch(err:any){toast(err.message)}finally{setBusy('')}}
 return <section className="card padded"><h2>Đăng ký chờ duyệt</h2><p className="subtle">Xác minh người đăng ký là nhân viên của công ty trước khi cho phép truy cập. Tài khoản được duyệt có vai trò Employee.</p>{query.data.items.map((u:Row)=><div className="service-row registration-row" key={u.id}><div><b>{u.name}</b><small className="block">{u.email} · {date(u.created_at)}</small></div><div className="flex"><button className="btn primary" disabled={!!busy} onClick={()=>decide(u.id,'approve')}><Busy busy={busy===u.id} label="Duyệt tài khoản"/></button><button className="btn secondary" disabled={!!busy} onClick={()=>decide(u.id,'reject')}>Từ chối</button></div></div>)}</section>
}
