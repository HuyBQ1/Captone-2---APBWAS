import {createContext,useContext,useEffect,useRef,useState,ReactNode} from 'react';
import {AnimatePresence,motion} from 'framer-motion';
import {AlertCircle,Check,ChevronLeft,ChevronRight,Loader2,Search,X} from 'lucide-react';
import {statusLabels} from './api';

const ToastContext=createContext<(text:string)=>void>(()=>{});
export const useToast=()=>useContext(ToastContext);
export function ToastProvider({children}:{children:ReactNode}) {
 const [toast,setToast]=useState(''); useEffect(()=>{if(toast){const t=setTimeout(()=>setToast(''),4500);return()=>clearTimeout(t)}},[toast]);
 return <ToastContext.Provider value={setToast}>{children}<AnimatePresence>{toast&&<motion.div role="status" className="toast" initial={{y:16,opacity:0}} animate={{y:0,opacity:1}} exit={{opacity:0}}><Check size={18}/>{toast}<button aria-label="Đóng thông báo" onClick={()=>setToast('')}><X size={16}/></button></motion.div>}</AnimatePresence></ToastContext.Provider>;
}
export function Badge({status}:{status:string}){return <span className={'badge '+status}><i/>{statusLabels[status]||status}</span>}
export function Loading(){return <div className="skeletons" aria-label="Đang tải"><div/><div/><div/></div>}
export function ErrorBox({error,retry}:{error:any;retry?:()=>void}){return <div className="error-box" role="alert"><AlertCircle size={24}/><h3>{error?.status===403?'Bạn không có quyền truy cập':'Không thể tải dữ liệu'}</h3><p>{error?.message||'Kiểm tra kết nối backend rồi thử lại.'}</p>{retry&&<button className="btn secondary" onClick={retry}>Thử lại</button>}</div>}
export function Empty({text='Chưa có dữ liệu trong khoảng thời gian này.'}:{text?:string}){return <div className="empty"><Search size={28}/><h3>Chưa có kết quả</h3><p>{text}</p></div>}
export function PageHeader({eyebrow='WORKSPACE',title,description,action}:{eyebrow?:string;title:string;description:string;action?:ReactNode}){return <div className="page-heading"><div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1><p>{description}</p></div>{action}</div>}
export function Pagination({page,total,size=10,onChange}:{page:number;total:number;size?:number;onChange:(n:number)=>void}){return <div className="pagination"><span>{total} kết quả · Trang {page}/{Math.max(1,Math.ceil(total/size))}</span><div><button className="icon-btn" aria-label="Trang trước" disabled={page<=1} onClick={()=>onChange(page-1)}><ChevronLeft size={17}/></button><button className="icon-btn" aria-label="Trang sau" disabled={page*size>=total} onClick={()=>onChange(page+1)}><ChevronRight size={17}/></button></div></div>}
export function Modal({title,children,onClose,wide=false}:{title:string;children:ReactNode;onClose:()=>void;wide?:boolean}){
 const ref=useRef<HTMLDivElement>(null);
 useEffect(()=>{const prior=document.activeElement as HTMLElement; const node=ref.current; const controls=()=>Array.from(node?.querySelectorAll<HTMLElement>('button:not(:disabled),input,select,textarea,a[href],[tabindex="0"]')||[]); controls()[0]?.focus();const handler=(e:KeyboardEvent)=>{if(e.key==='Escape')onClose();if(e.key==='Tab'){const elements=controls();const first=elements[0],last=elements[elements.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus()}}};document.addEventListener('keydown',handler); const old=document.body.style.overflow;document.body.style.overflow='hidden';return()=>{document.removeEventListener('keydown',handler);document.body.style.overflow=old;prior?.focus()}},[]);
 return <motion.div className="modal-overlay" initial={{opacity:0}} animate={{opacity:1}} onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}><motion.div ref={ref} role="dialog" aria-modal="true" aria-label={title} className={'modal '+(wide?'wide':'')} initial={{y:15,scale:.98}} animate={{y:0,scale:1}}><div className="modal-head"><h2>{title}</h2><button className="icon-btn" aria-label="Đóng hộp thoại" onClick={onClose}><X size={20}/></button></div>{children}</motion.div></motion.div>
}
export function Busy({busy,label}:{busy:boolean;label:string}){return <>{busy&&<Loader2 className="spin" size={16}/>} {label}</>}
