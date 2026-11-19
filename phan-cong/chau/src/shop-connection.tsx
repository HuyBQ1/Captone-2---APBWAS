import {useState} from 'react';
import {useQuery,useQueryClient} from '@tanstack/react-query';
import {ExternalLink,RefreshCw,Store,ShieldCheck} from 'lucide-react';
import {api,post,date} from './api';
import {useUser} from './main';
import {Busy,useToast} from './ui';

export function ShopConnection(){
 const user=useUser(),toast=useToast(),cache=useQueryClient(),[key,setKey]=useState(''),[replace,setReplace]=useState(false),[busy,setBusy]=useState(false);
 const canManage=user.permissions.includes('settings.manage'),canRead=user.permissions.includes('inventory.read');
 const q=useQuery({queryKey:['shop-connection'],queryFn:()=>api('/connections/shop'),enabled:canRead,refetchInterval:30000});
 const connected=!!q.data?.last_sync;
 async function perform(connect:boolean){setBusy(true);try{if(connect)await api('/connections/shop',{method:'PUT',body:JSON.stringify({api_key:key.trim(),replace_existing:replace})});else await post('/connections/shop/sync');setKey('');setReplace(false);await cache.invalidateQueries({queryKey:['shop-connection']});cache.invalidateQueries({queryKey:['business']});cache.invalidateQueries({queryKey:['finance']});toast('Đã đồng bộ dữ liệu từ website Nova Commerce.')}catch(e:any){toast(e.message)}finally{setBusy(false)}}
 return <article className="card connection-card"><div className="connection-card-top"><span className="connection-icon" style={{background:'#eeedff',color:'#7061d1'}}><Store size={30}/></span><span className={'connection-state '+(connected&&!q.data?.last_error?'online':'')}>{q.isError?'Chưa tải được trạng thái':connected?'Đã kết nối website':'Chưa kết nối'}</span></div><h2>Nova Commerce</h2><span className="connection-mode">WEBSITE BÁN HÀNG · API CHỈ ĐỌC</span><p>Sản phẩm, ảnh, tồn kho và giao dịch được đồng bộ từ website. Doanh thu đã trừ hoàn hàng; chi phí giữ trạng thái xác nhận từ nguồn.</p><a className="text-link" href="https://nova-commerce-neon.vercel.app/" target="_blank" rel="noreferrer">Mở website bán hàng <ExternalLink size={14}/></a>
 {connected&&<div style={{marginTop:16}}><b>{q.data!.counts?.products||0} sản phẩm{user.permissions.includes('sales.read')&&<> · {q.data!.counts?.orders||0} đơn hàng</>}</b><small className="block">Đồng bộ gần nhất: {date(q.data!.last_sync)}</small><small className="block">Tự kiểm tra đồng bộ mỗi 5 phút khi worker hoạt động.</small>{q.data?.last_error&&<p className="error-text">{q.data.last_error}</p>}</div>}
 {canManage&&<><div className="connection-card-actions">{connected&&<button className="btn secondary" disabled={busy} onClick={()=>perform(false)}><RefreshCw size={15}/><Busy busy={busy} label="Đồng bộ ngay"/></button>}</div><details style={{marginTop:15}}><summary style={{cursor:'pointer',fontSize:12}}>{connected?'Cập nhật API key':'Thiết lập kết nối'}</summary><form onSubmit={e=>{e.preventDefault();perform(true)}}><label>API key Nova Commerce<input type="password" autoComplete="off" value={key} onChange={e=>setKey(e.target.value)} placeholder="nova_…" required minLength={10}/></label>{!connected&&<label className="checkbox"><input type="checkbox" checked={replace} onChange={e=>setReplace(e.target.checked)}/>Sao lưu và thay dữ liệu sản phẩm, giao dịch, chi phí cũ bằng dữ liệu website.</label>}<button className="btn primary" disabled={busy||!key.trim()}><Busy busy={busy} label={connected?'Lưu và đồng bộ':'Kết nối website'}/></button></form></details></>}
 <small className="block" style={{marginTop:18}}><ShieldCheck size={13} style={{verticalAlign:'middle'}}/> API key lưu mã hóa tại backend. Chỉnh dữ liệu trên website bán hàng.</small></article>
}

export function ShopSourceBanner(){
 const user=useUser();const q=useQuery({queryKey:['shop-connection'],queryFn:()=>api('/connections/shop'),enabled:user.permissions.includes('inventory.read'),refetchInterval:30000});
 if(!q.data?.last_sync)return null;
 return <div className="card padded" style={{marginBottom:18}}><b><Store size={16} style={{verticalAlign:'middle',marginRight:7}}/>Nguồn dữ liệu: website Nova Commerce</b><p className="subtle">Đồng bộ lúc {date(q.data.last_sync)}. Cập nhật sản phẩm và giao dịch trên website bán hàng; APBWAS đọc bản đồng bộ để phân tích và tạo báo cáo.</p>{q.data.last_error&&<p className="error-text">{q.data.last_error}</p>}<a className="text-link" href="/connections">Quản lý kết nối <ExternalLink size={13}/></a></div>
}
