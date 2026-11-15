import {RegisterPage,ForgotPasswordPage} from './public-accounts';
import {Home} from './home';
import React,{useEffect,useState} from 'react';
import ReactDOM from 'react-dom/client';
import {BrowserRouter,Routes,Route,NavLink,Link,useNavigate,useLocation,Navigate} from 'react-router-dom';
import {QueryClient,QueryClientProvider,useQuery} from '@tanstack/react-query';
import {MotionConfig,motion} from 'framer-motion';
import {LayoutDashboard,Sparkles,GitBranch,ChartNoAxesCombined,BookOpen,Database,ShieldCheck,History,Settings,Users,Search,Sun,Moon,Bell,ChevronRight,ChevronLeft,LogOut,Menu,Command,ArrowUpRight,X,Layers,Eye,EyeOff,Plug,Cpu} from 'lucide-react';
import {useForm} from 'react-hook-form';
import {zodResolver} from '@hookform/resolvers/zod';
import {z} from 'zod';
import {api,post,Row} from './api';
import {ToastProvider,Modal,Busy,useToast} from './ui';
import {Dashboard,WorkflowList,WorkflowDetail,Reports,ReportDetail,Approvals,ApprovalDetail,Knowledge,DocumentDetail,Business,Audit} from './pages';
import {NovaSalesDetail} from './nova-sales-report';
import {Workspace} from './workspace';
import {AgentList,AgentEditor,AgentPlayground,AgentVersions} from './agents';
import {GmailPage,GmailCallback} from './mail';
import {Connections,ExcelConnection} from './connections';
import {ModelCenter} from './llm-models';
import {EmployeeMail,MailCampaign} from './bulk-mail';
import {Admin} from './admin';
import {AccountCenter as Account,RecoveryPage,Notifications} from './enterprise';
import './style.css';
import '@xyflow/react/dist/style.css';

export const client=new QueryClient({defaultOptions:{queries:{retry:1,refetchOnWindowFocus:false}}});
const navigation=[{to:'/home',label:'Trang chủ',icon:Layers},{to:'/',label:'Tổng quan',icon:LayoutDashboard},{to:'/agents',label:'AI Agents',icon:Sparkles,permission:'agents.run'},{to:'/workspace',label:'AI Workspace',icon:Sparkles},{to:'/workflows',label:'Workflows',icon:GitBranch},{to:'/reports',label:'Báo cáo',icon:ChartNoAxesCombined,permission:'sales.read'},{to:'/knowledge',label:'Kho tri thức',icon:BookOpen,permission:'documents.read'},{to:'/data',label:'Dữ liệu doanh nghiệp',icon:Database,permission:'inventory.read'},{to:'/approvals',label:'Phê duyệt',icon:ShieldCheck,permission:'inventory.read'},{to:'/connections',label:'Kết nối',icon:Plug},{to:'/models',label:'Mô hình AI',icon:Cpu,permission:'settings.manage'},{to:'/notifications',label:'Thông báo',icon:Bell},{to:'/audit',label:'Lịch sử hoạt động',icon:History,permission:'audit.read'},{to:'/admin',label:'Quản trị',icon:Users,permission:'users.manage'},{to:'/account',label:'Cài đặt tài khoản',icon:Settings}];
const AuthContext=React.createContext<Row>({});
export const useUser=()=>React.useContext(AuthContext);

function Login({onLogin}:{onLogin:(u:Row)=>void}){
 const loginConfig=useQuery({queryKey:['login-config'],queryFn:()=>api('/auth/config')});
 const [show,setShow]=useState(false),[error,setError]=useState('');
 const schema=z.object({email:z.string().email('Email chưa hợp lệ'),password:z.string().min(1,'Vui lòng nhập mật khẩu')});
 const {register,handleSubmit,setValue,formState:{errors,isSubmitting}}=useForm<z.infer<typeof schema>>({resolver:zodResolver(schema),defaultValues:{email:'',password:''}});
 if(window.location.pathname==='/register')return <RegisterPage/>;
 if(['/forgot-password','/account-help'].includes(window.location.pathname))return <ForgotPasswordPage/>;
 if(window.location.pathname==='/reset-password')return location.hash.includes('token=')?<RecoveryPage/>:<ForgotPasswordPage/>;
 return <div className="login-page"><div className="login-story"><Link className="brand" to="/"><span className="brand-mark"><Layers size={24}/></span>APBWAS<span className="brand-dot">.</span></Link><div className="story-content"><span className="pill">AI-POWERED BUSINESS AUTOMATION</span><h1>Từ một câu hỏi.<br/>Đến một quy trình<br/><em>hoàn chỉnh.</em></h1><p>Kết nối dữ liệu, kiến thức và công việc của bạn trong một không gian thông minh.</p><div className="story-flow"><span><Database size={22}/>Dữ liệu</span><ChevronRight/><span><Sparkles size={22}/>AI Agent</span><ChevronRight/><span><ShieldCheck size={22}/>Kiểm soát</span></div></div><small>CAPSTONE 2 · C2SE.06 · APBWAS 2026</small></div><div className="login-form-side"><div className="login-form"><span className="eyebrow">CHÀO MỪNG TRỞ LẠI</span><h2>Đăng nhập workspace</h2><p>Công việc thông minh hơn bắt đầu từ đây.</p><form onSubmit={handleSubmit(async values=>{setError('');try{onLogin(await post('/auth/login',values))}catch(e:any){setError(e.message)}})}><label>Email<input autoComplete="username" placeholder="ban@doanhnghiep.vn" {...register('email')}/></label>{errors.email&&<small className="error-text">{errors.email.message}</small>}<label>Mật khẩu<div className="password-input"><input type={show?'text':'password'} autoComplete="current-password" placeholder="Nhập mật khẩu" {...register('password')}/><button type="button" aria-label="Hiện hoặc ẩn mật khẩu" onClick={()=>setShow(!show)}>{show?<EyeOff size={18}/>:<Eye size={18}/>}</button></div></label>{errors.password&&<small className="error-text">{errors.password.message}</small>}{error&&<p className="error-text" role="alert">{error}</p>}<button className="btn primary full" disabled={isSubmitting}><Busy busy={isSubmitting} label="Đăng nhập"/><ArrowUpRight size={18}/></button></form><div className="auth-links"><Link className="text-link" to="/forgot-password">Quên mật khẩu?</Link><Link className="text-link" to="/register">Tạo tài khoản</Link></div>{loginConfig.data?.demo_accounts&&<div className="demo-accounts"><b>Tài khoản dữ liệu mô phỏng</b><p>Dùng với bộ tài khoản mẫu đã được seed trên backend.</p><div>{['Admin','Manager','Employee'].map(role=><button key={role} className="btn secondary" onClick={()=>{setValue('email',role.toLowerCase()+'@apbwas.demo');setValue('password','Demo@123456')}}>{role}</button>)}</div><small>Mật khẩu mặc định: Demo@123456</small></div>}</div></div></div>
}

function Shell(){
 const toast=useToast();
 const [user,setUser]=useState<Row|null>(null),[ready,setReady]=useState(false),[collapsed,setCollapsed]=useState(false),[mobile,setMobile]=useState(false),[palette,setPalette]=useState(false),[search,setSearch]=useState(''),[account,setAccount]=useState(false);
 const [theme,setTheme]=useState('light');const navigate=useNavigate(),location=useLocation();
 useEffect(()=>{let alive=true;api('/auth/me').then(value=>{if(alive)setUser(value)}).catch(()=>{if(alive)setUser(null)}).finally(()=>{if(alive)setReady(true)});const expired=()=>{setUser(null);client.clear()};window.addEventListener('session-expired',expired);return()=>{alive=false;window.removeEventListener('session-expired',expired)}},[]);
 useEffect(()=>{document.documentElement.dataset.theme=theme},[theme]);
 useEffect(()=>{
  if(!user)return;
  let pending=false,alive=true;
  const refresh=async()=>{
   if(pending)return;pending=true;
   try{
    const fresh=await api('/auth/me');
    if(alive&&(fresh.role!==user.role||JSON.stringify(fresh.permissions)!==JSON.stringify(user.permissions))){
     client.clear();setUser(fresh);toast('Quyền truy cập đã thay đổi. Dữ liệu cũ đã được đóng.');navigate('/403',{replace:true});
    }
   }catch(e:any){if(alive&&e.status===401){client.clear();setUser(null)}}finally{pending=false}
  };
  const interval=window.setInterval(refresh,30000);
  window.addEventListener('focus',refresh);window.addEventListener('permissions-changed',refresh);
  return()=>{alive=false;window.clearInterval(interval);window.removeEventListener('focus',refresh);window.removeEventListener('permissions-changed',refresh)};
 },[user?.id,user?.role,JSON.stringify(user?.permissions)]);
 useEffect(()=>{const listener=(e:KeyboardEvent)=>{if((e.ctrlKey||e.metaKey)&&e.key==='k'){e.preventDefault();setPalette(p=>!p)}};window.addEventListener('keydown',listener);return()=>window.removeEventListener('keydown',listener)},[]);
 useEffect(()=>{setMobile(false);setAccount(false)},[location.pathname]);
 useEffect(()=>{if(user){setTheme(user.preferences?.theme||'light');setCollapsed(!!user.preferences?.sidebar_collapsed)}},[user?.id]);
 const notifications=useQuery({queryKey:['notifications','badge'],queryFn:()=>api('/notifications'),enabled:!!user&&!user.must_change_password,refetchInterval:10000});
 const company=useQuery({queryKey:['company'],queryFn:()=>api('/company'),enabled:!!user&&!user.must_change_password});
 const savePreferences=async(nextTheme:string,nextCollapsed:boolean)=>{try{await api('/auth/preferences',{method:'PUT',body:JSON.stringify({theme:nextTheme,sidebar_collapsed:nextCollapsed})});setTheme(nextTheme);setCollapsed(nextCollapsed)}catch(e:any){toast(e.message)}};
 const approvals=useQuery({queryKey:['pending',user?.id],queryFn:()=>api('/approvals?status=pending'),enabled:!user?.must_change_password&&!!user?.permissions?.includes('inventory.read'),refetchInterval:8000});
 if(!ready)return <div className="boot"><Layers size={34}/><p>Đang kết nối APBWAS…</p></div>;
 if(location.pathname==='/register')return <RegisterPage/>;
 if(['/forgot-password','/account-help'].includes(location.pathname))return <ForgotPasswordPage/>;
 if(location.pathname==='/reset-password')return <RecoveryPage/>;
 if(location.pathname==='/home'||(!user&&location.pathname==='/'))return <Home signedIn={!!user}/>;
 if(user&&location.pathname==='/login')return <Navigate to="/workspace" replace/>;
 if(!user)return <Login onLogin={u=>{setUser(u);client.clear();navigate('/')}}/>;
 if(user.must_change_password)return <AuthContext.Provider value={{...user,refreshUser:()=>api('/auth/me').then(setUser)}}><main className="padded"><Account/></main></AuthContext.Provider>;
 const allowed=navigation.filter(n=>!n.permission||user.permissions.includes(n.permission));
 const current=navigation.find(n=>n.to==='/'?location.pathname==='/':(location.pathname.startsWith(n.to)||(n.to==='/connections'&&location.pathname.startsWith('/mail'))));
 const permitted=(permission:string,child:React.ReactNode)=>user.permissions.includes(permission)?child:<NotFound forbidden/>;
 return <AuthContext.Provider value={{...user,refreshUser:()=>api('/auth/me').then(setUser)}}><div className={'app '+(collapsed?'collapsed ':'')+(mobile?'mobile-open':'')}>
 {mobile&&<button className="sidebar-backdrop" aria-label="Đóng menu" onClick={()=>setMobile(false)}/>}
 <aside className="sidebar"><Link to="/" className="brand"><span className="brand-mark"><Layers size={23}/></span><span className="brand-name">APBWAS<span className="brand-dot">.</span></span></Link><div className="workspace-label"><span className="workspace-square">A</span><div>{company.data?.name||'Business Workspace'}<small>Không gian làm việc</small></div></div><div className="nav-label">WORKSPACE</div><nav>{allowed.slice(0,-1).map(n=><NavLink title={n.label} key={n.to} className={({isActive})=>isActive||(n.to==='/connections'&&location.pathname.startsWith('/mail'))?'active':''} end={n.to==='/'} to={n.to}><n.icon size={19}/><span>{n.label}</span>{n.to==='/approvals'&&!!approvals.data?.total&&<b>{approvals.data.total}</b>}{n.to==='/workspace'&&<small>AI</small>}</NavLink>)}</nav><div className="sidebar-bottom"><div className="sidebar-ai"><span><i/> Công cụ được kiểm soát</span><p>Biến ý tưởng thành hành động.</p><Link to="/workspace">Khám phá AI Workspace <ArrowUpRight size={15}/></Link></div><NavLink to="/account"><Settings size={19}/><span>Cài đặt tài khoản</span></NavLink><button className="collapse-btn" onClick={()=>savePreferences(theme,!collapsed)} aria-label="Thu gọn hoặc mở rộng sidebar">{collapsed?<ChevronRight size={18}/>:<><ChevronLeft size={18}/><span>Thu gọn menu</span></>}</button></div></aside>
 <div className="app-main"><header className="topbar"><div className="breadcrumb"><button className="icon-btn mobile-menu" aria-label="Mở menu" onClick={()=>setMobile(true)}><Menu size={20}/></button><span>Workspace</span><ChevronRight size={14}/><b>{current?.label||'Chi tiết'}</b></div><div className="top-actions"><button className="command-search" onClick={()=>setPalette(true)}><Search size={17}/><span>Tìm kiếm nhanh…</span><kbd>⌘ K</kbd></button>{(user.demo_mode||user.sample_data)&&<span className="demo-label">{user.demo_mode?"Demo Mode":"Dữ liệu mẫu · AI thật"}</span>}<button className="icon-btn" aria-label="Chuyển giao diện sáng tối" onClick={()=>savePreferences(theme==='light'?'dark':'light',collapsed)}>{theme==='light'?<Moon size={19}/>:<Sun size={19}/>}</button><Link className="notification icon-btn" aria-label="Thông báo" to="/notifications"><Bell size={19}/>{!!notifications.data?.unread&&<i/>}</Link><span className="role">{user.role}</span><button className="avatar" aria-label="Menu tài khoản" onClick={()=>setAccount(!account)}>{user.name.split(' ').slice(-1)[0].slice(0,1)}</button>{account&&<div className="account-menu"><b>{user.name}</b><small>{user.email}</small><span className="role">{user.role}</span><Link to="/account">Hồ sơ cá nhân</Link><button onClick={async()=>{try{await post('/auth/logout');setUser(null);client.clear()}catch(e:any){toast(e.message)}}}><LogOut size={16}/>Đăng xuất</button></div>}</div></header>
 <main><motion.div key={location.pathname} initial={{opacity:0,y:8}} animate={{opacity:1,y:0}} transition={{duration:.2}}><Routes><Route path="/" element={<Dashboard/>}/><Route path="/workspace" element={<Workspace/>}/><Route path="/models" element={permitted('settings.manage',<ModelCenter/>)}/><Route path="/connections" element={<Connections/>}/><Route path="/connections/excel" element={<ExcelConnection/>}/><Route path="/mail" element={permitted('mail.connect',<GmailPage/>)}/><Route path="/mail/employees" element={permitted('mail.send',<EmployeeMail/>)}/><Route path="/mail/campaigns/:id" element={permitted('mail.send',<MailCampaign/>)}/><Route path="/mail/callback" element={permitted('mail.connect',<GmailCallback/>)}/><Route path="/agents" element={permitted('agents.run',<AgentList/>)}/><Route path="/agents/new" element={permitted('agents.manage',<AgentEditor/>)}/><Route path="/agents/:id/edit" element={permitted('agents.manage',<AgentEditor/>)}/><Route path="/agents/:id/playground" element={permitted('agents.run',<AgentPlayground/>)}/><Route path="/agents/:id/versions" element={permitted('agents.manage',<AgentVersions/>)}/><Route path="/workflows" element={<WorkflowList/>}/><Route path="/workflows/:id" element={<WorkflowDetail/>}/><Route path="/reports" element={permitted('sales.read',<Reports/>)}/><Route path="/reports/:id" element={permitted('sales.read',<ReportDetail/>)}/><Route path="/reports/nova-sales/:month" element={permitted('sales.read',<NovaSalesDetail/>)}/><Route path="/knowledge" element={permitted('documents.read',<Knowledge/>)}/><Route path="/knowledge/:id" element={permitted('documents.read',<DocumentDetail/>)}/><Route path="/data" element={permitted('inventory.read',<Business/>)}/><Route path="/approvals" element={permitted('inventory.read',<Approvals/>)}/><Route path="/approvals/:id" element={permitted('inventory.read',<ApprovalDetail/>)}/><Route path="/audit" element={permitted('audit.read',<Audit/>)}/><Route path="/admin" element={permitted('users.manage',<Admin/>)}/><Route path="/account" element={<Account/>}/><Route path="/notifications" element={<Notifications/>}/><Route path="/403" element={<NotFound forbidden/>}/><Route path="*" element={<NotFound/>}/></Routes></motion.div></main><footer className="app-footer"><span>APBWAS · AI-Powered Business Workflow Automation</span><span>{user.demo_mode?'Dữ liệu mô phỏng':user.sample_data?'Dữ liệu mẫu · AI kết nối':'Connected Mode'} <i/> Asia/Ho_Chi_Minh</span></footer></div>
 {palette&&<Modal title="Điều hướng nhanh" onClose={()=>setPalette(false)}><div className="search-field"><Search size={18}/><input autoFocus placeholder="Tìm màn hình…" value={search} onChange={e=>setSearch(e.target.value)}/></div><div className="palette-list">{allowed.filter(n=>n.label.toLowerCase().includes(search.toLowerCase())).map(n=><button key={n.to} onClick={()=>{navigate(n.to);setPalette(false);setSearch('')}}><n.icon size={19}/>{n.label}<ChevronRight size={17}/></button>)}</div></Modal>}
 </div></AuthContext.Provider>
}
function NotFound({forbidden=false}:{forbidden?:boolean}){return <div className="not-found"><span>{forbidden?'403':'404'}</span><h1>{forbidden?'Quyền truy cập bị giới hạn':'Không tìm thấy trang'}</h1><p>{forbidden?'Tài khoản của bạn chưa được cấp quyền cho màn hình này.':'Đường dẫn không tồn tại hoặc tài nguyên đã được chuyển.'}</p><Link className="btn primary" to="/">Trở về tổng quan</Link></div>}
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><QueryClientProvider client={client}><BrowserRouter><MotionConfig reducedMotion="user"><ToastProvider><Shell/></ToastProvider></MotionConfig></BrowserRouter></QueryClientProvider></React.StrictMode>);
