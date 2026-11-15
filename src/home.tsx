import {useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {ArrowRight,ArrowUpRight,Layers,Sparkles,Database,GitBranch,FileText,FileSpreadsheet,Mail,ShieldCheck,Check,ChevronRight,Menu,X,BookOpen,ChartNoAxesCombined,Command} from 'lucide-react';
import './home.css';

const examples=[
 {name:'Báo cáo',icon:ChartNoAxesCombined,prompt:'Phân tích doanh thu tháng này và tạo báo cáo Excel.',steps:['Đọc dữ liệu bán hàng','Tổng hợp doanh thu và chi phí','Tạo báo cáo Excel'],file:'Báo cáo doanh thu.xlsx',kind:'Excel'},
 {name:'Kho hàng',icon:Database,prompt:'Kiểm tra những sản phẩm sắp hết hàng.',steps:['Tra cứu dữ liệu tồn kho','Đối chiếu ngưỡng cảnh báo','Tổng hợp sản phẩm cần kiểm tra'],file:'Danh sách tồn kho',kind:'Dữ liệu'},
 {name:'Tri thức',icon:BookOpen,prompt:'Tìm quy định nghỉ phép và dẫn nguồn tài liệu.',steps:['Tìm tài liệu được cấp quyền','Đọc các đoạn liên quan','Trả lời kèm nguồn tham khảo'],file:'Chính sách nội bộ',kind:'Tài liệu'},
];
const features=[
 {icon:Database,title:'Hiểu dữ liệu doanh nghiệp',text:'Tra cứu sản phẩm, tồn kho và giao dịch từ nguồn dữ liệu được cấp quyền.',label:'DỮ LIỆU'},
 {icon:FileSpreadsheet,title:'Từ câu hỏi đến báo cáo',text:'Tổng hợp số liệu, tạo Word và Excel. Xem trước nội dung rồi tải tệp ngay trong hội thoại.',label:'BÁO CÁO'},
 {icon:BookOpen,title:'Kiến thức luôn có nguồn',text:'Tìm thông tin trong tài liệu nội bộ và kiểm tra lại nguồn của câu trả lời.',label:'TRI THỨC'},
 {icon:Mail,title:'Kết nối với công việc',text:'Kết nối Gmail, soạn email cho nhân viên và xem lại nội dung trước khi xác nhận gửi.',label:'KẾT NỐI'},
];
export function Home({signedIn=false}:{signedIn?:boolean}){
 useEffect(()=>{const previous=document.title;document.title='APBWAS · Trợ lý AI cho doanh nghiệp';return()=>{document.title=previous}},[]);
 const [menu,setMenu]=useState(false),[example,setExample]=useState(0);const selected=examples[example];
 const entry=signedIn?'/workspace':'/login';
 return <div className="ap-home">
  <a className="home-skip" href="#home-main">Đến nội dung chính</a>
  <header className="home-header"><div className="home-container home-nav">
   <Link to="/home" className="home-brand" aria-label="APBWAS trang chủ"><span><Layers size={24}/></span>APBWAS<span className="home-brand-dot">.</span></Link>
   <nav aria-label="Điều hướng trang chủ" className={menu?'home-links is-open':'home-links'}>
    <a href="#home-features" onClick={()=>setMenu(false)}>Tính năng</a><a href="#home-how" onClick={()=>setMenu(false)}>Cách hoạt động</a><a href="#home-control" onClick={()=>setMenu(false)}>Kiểm soát & bảo mật</a>
   </nav>
   <div className="home-nav-actions">{!signedIn&&<Link className="home-signin" to="/login">Đăng nhập</Link>}<Link className="home-button home-button-small" to={signedIn?'/workspace':'/register'}>{signedIn?'Vào workspace':'Bắt đầu'}<ArrowUpRight size={16}/></Link><button type="button" className="home-menu" aria-label={menu?'Đóng điều hướng':'Mở điều hướng'} aria-expanded={menu} onClick={()=>setMenu(!menu)}>{menu?<X/>:<Menu/>}</button></div>
  </div></header>
  <main id="home-main">
   <section className="home-hero home-container">
    <div className="home-hero-copy"><div className="home-kicker"><span/>TRỢ LÝ AI CHO DOANH NGHIỆP</div>
     <h1>Giao việc cho AI.<br/>Dành thời gian cho<br/><em>điều quan trọng.</em></h1>
     <p>Kết nối dữ liệu, tìm câu trả lời và tạo báo cáo trong một không gian. Bạn đưa ra yêu cầu, AI Agent giúp thực hiện từng bước.</p>
     <div className="home-hero-actions"><Link className="home-button" to={entry}>{signedIn?'Mở AI Workspace':'Khám phá workspace'}<ArrowRight size={18}/></Link><a className="home-text-button" href="#home-how">Xem cách hoạt động<ChevronRight size={17}/></a></div>
     <div className="home-hero-note"><ShieldCheck size={16}/><span>Dữ liệu có phân quyền. Hành động có kiểm soát.</span></div>
    </div>
    <div className="home-product" aria-label="Minh họa giao diện AI Workspace">
     <div className="home-product-top"><span><span className="home-live-dot"/>AI Workspace</span><span>APBWAS<Command size={13}/></span></div>
     <div className="home-product-body"><div className="home-product-heading"><span className="home-ai-mark"><Sparkles size={23}/></span><div><b>Trợ lý của bạn, sẵn sàng.</b><small>Một yêu cầu. Từng bước rõ ràng.</small></div></div>
      <div className="home-example-tabs" role="tablist" aria-label="Tình huống minh họa">{examples.map((e,i)=><button role="tab" id={'home-tab-'+i} aria-controls="home-example-panel" aria-selected={example===i} key={e.name} type="button" onClick={()=>setExample(i)}><e.icon size={14}/>{e.name}</button>)}</div>
      <div role="tabpanel" id="home-example-panel" aria-labelledby={'home-tab-'+example} className="home-example-panel"><div className="home-question">{selected.prompt}<span>Bạn</span></div>
       <div className="home-preview-plan"><div className="home-plan-label"><GitBranch size={15}/>KẾ HOẠCH THỰC HIỆN</div>{selected.steps.map((s,i)=><div className="home-preview-step" key={s}><span><Check size={13}/></span><b>{s}</b><small>0{i+1}</small></div>)}</div>
       <div className="home-preview-file"><span>{example===0?<FileSpreadsheet size={21}/>:example===1?<Database size={21}/>:<FileText size={21}/>}</span><div><b>{selected.file}</b><small>{selected.kind} · Kết quả từ công cụ</small></div><ArrowUpRight size={18}/></div>
      </div>
      <div className="home-preview-composer"><Sparkles size={15}/><span>Bạn muốn hoàn thành công việc gì?</span><span className="home-preview-send"><ArrowRight size={17}/></span></div>
     </div><div className="home-product-caption">Minh họa luồng xử lý · Không phải dữ liệu đang chạy</div>
     <div className="home-floating"><span><ShieldCheck size={21}/></span><div><b>Bạn luôn nắm quyền</b><small>Kiểm tra trước khi xác nhận</small></div></div>
    </div>
   </section>
   <div className="home-capabilities home-container"><span>MỘT KHÔNG GIAN CHO</span><b><Database size={17}/>Dữ liệu doanh nghiệp</b><b><FileText size={17}/>Word & Excel</b><b><BookOpen size={17}/>Tài liệu nội bộ</b><b><Mail size={17}/>Gmail</b></div>
   <section className="home-section home-container" id="home-features"><div className="home-section-heading"><div><span className="home-section-label">LÀM VIỆC CÙNG AI</span><h2>Bớt thao tác lặp lại.<br/>Thêm thời gian để quyết định.</h2></div><p>Từ câu hỏi đầu tiên đến tệp báo cáo cuối cùng, công việc được kết nối trong cùng một quy trình.</p></div>
    <div className="home-feature-grid">{features.map(f=><article className="home-feature" key={f.title}><span className="home-feature-icon"><f.icon size={24}/></span><small>{f.label}</small><h3>{f.title}</h3><p>{f.text}</p></article>)}</div>
   </section>
   <section className="home-process" id="home-how"><div className="home-container"><span className="home-section-label">TỪ YÊU CẦU ĐẾN KẾT QUẢ</span><h2>Bạn giao việc.<br/>Agent kết nối các bước.</h2><div className="home-process-grid">{[{n:'01',icon:Sparkles,title:'Nói điều bạn cần',text:'Đặt câu hỏi hoặc yêu cầu bằng tiếng Việt. Chọn Agent và model phù hợp với công việc.'},{n:'02',icon:GitBranch,title:'Theo dõi kế hoạch',text:'Agent lựa chọn công cụ. Hệ thống kiểm tra quyền và thực hiện trên nguồn dữ liệu được phép.'},{n:'03',icon:ShieldCheck,title:'Kiểm tra kết quả',text:'Đọc câu trả lời, xem nguồn và tải báo cáo. Xem lại nội dung trước khi xác nhận thao tác gửi.'}].map(s=><article key={s.n}><div><span>{s.n}</span><s.icon size={22}/></div><h3>{s.title}</h3><p>{s.text}</p></article>)}</div></div></section>
   <section className="home-control home-container" id="home-control"><div className="home-control-art" aria-hidden="true"><div className="home-orbit home-orbit-outer"/><div className="home-orbit home-orbit-inner"/><div className="home-shield"><ShieldCheck size={60} strokeWidth={1.3}/></div><span className="home-control-tag home-tag-first"><Database size={16}/>Đúng dữ liệu</span><span className="home-control-tag home-tag-second"><Check size={16}/>Đúng quyền hạn</span><span className="home-control-tag home-tag-third"><GitBranch size={16}/>Có lịch sử thực thi</span></div><div><span className="home-section-label">AI HỖ TRỢ VÀ BẠN KIỂM SOÁT</span><h2>Công việc tự động.<br/>Quyền quyết định vẫn ở bạn.</h2><p>Mỗi tài khoản có phạm vi truy cập riêng. Các bước thực thi được lưu lại để kiểm tra, cùng cơ chế phê duyệt cho thao tác quan trọng.</p><ul><li><Check size={17}/>Phân quyền theo vai trò người dùng</li><li><Check size={17}/>Câu trả lời gắn với nguồn dữ liệu</li><li><Check size={17}/>Theo dõi workflow và lịch sử hoạt động</li></ul><Link className="home-text-button" to={entry}>Khám phá trong workspace<ArrowUpRight size={17}/></Link></div></section>
   <section className="home-cta home-container"><span className="home-ai-mark"><Sparkles size={25}/></span><h2>Công việc tiếp theo của bạn là gì?</h2><p>Bắt đầu từ một câu hỏi. Để APBWAS giúp bạn kết nối phần còn lại.</p><Link className="home-button" to={entry}>{signedIn?'Vào AI Workspace':'Đăng nhập và bắt đầu'}<ArrowRight size={18}/></Link></section>
  </main>
  <footer className="home-footer home-container"><Link to="/home" className="home-brand"><span><Layers size={19}/></span>APBWAS<span className="home-brand-dot">.</span></Link><p>AI Powered Business Workflow Automation System</p><a href="#home-main">Về đầu trang ↑</a></footer>
 </div>
}
