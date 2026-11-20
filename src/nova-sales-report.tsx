import {useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {ArrowUpRight} from 'lucide-react';
import {Link,useParams} from 'react-router-dom';
import {api,date,money} from './api';
import {Empty,ErrorBox,Loading,PageHeader,Pagination} from './ui';

type NovaSales = {
 synced_at:string|null;
 sync_failed:boolean;
 periods:{month:string;revenue:number;orders_created:number}[];
};

type NovaSalesDetailData = {
 month:string;
 synced_at:string;
 sync_failed:boolean;
 revenue:number;
 orders_created:number;
 sales_amount:number;
 refund_amount:number;
 cost_of_goods:number|null;
 expenses:number|null;
 operating_profit:number|null;
 categories:{category:string;revenue:number}[];
 products:{sku:string;name:string;category:string;sold:number;returned:number;sales_amount:number;refund_amount:number;revenue:number}[];
};

function monthLabel(month:string){
 const [year,number]=month.split('-');
 return number+'/'+year;
}

function askAI(month:string){
 return '/workspace?prompt='+encodeURIComponent('Phân tích doanh thu website Nova Commerce tháng '+month+'.');
}

export function NovaSalesReport(){
 const {data,isLoading,error,refetch}=useQuery({
  queryKey:['nova-sales-report'],
  queryFn:()=>api<NovaSales>('/reports/nova-sales'),
  refetchInterval:60_000,
 });
 if(isLoading)return <Loading/>;
 if(!data)return <ErrorBox error={error} retry={()=>refetch()}/>;
 if(!data.synced_at)return null;

 return <section className="card" aria-labelledby="nova-sales-heading">
  <div className="card-head">
   <div>
    <h3 id="nova-sales-heading">Doanh số từ website Nova Commerce</h3>
    <p>Đồng bộ lúc {date(data.synced_at)} · Doanh thu đã trừ các khoản hoàn hàng</p>
   </div>
   <Link className="text-link" to="/connections">Quản lý kết nối <ArrowUpRight size={15}/></Link>
  </div>
  {data.sync_failed&&<p className="padded subtle" role="status">Lượt đồng bộ gần nhất lỗi. Đang hiển thị số liệu từ lần đồng bộ thành công ở trên.</p>}
  {data.periods.length?<div className="table-wrap"><table aria-label="Doanh số theo tháng từ Nova Commerce">
   <thead><tr><th scope="col">Tháng</th><th scope="col">Doanh thu ghi nhận</th><th scope="col">Đơn được tạo</th><th scope="col">Thao tác</th></tr></thead>
   <tbody>{data.periods.map(({month,revenue,orders_created})=>{
    const label=monthLabel(month);
    return <tr key={month}>
     <td>{label}</td><td>{money(revenue)}</td><td>{orders_created.toLocaleString('vi-VN')}</td>
     <td><div className="flex flex-wrap">
      <Link className="text-link" to={'/reports/nova-sales/'+month} aria-label={'Xem chi tiết doanh số tháng '+label}>Xem chi tiết</Link>
      <Link className="text-link" to={askAI(month)} aria-label={'Hỏi AI về doanh thu tháng '+label}>Hỏi AI <ArrowUpRight size={14}/></Link>
     </div></td>
    </tr>;
   })}</tbody>
  </table></div>:<p className="padded subtle">Website chưa có kỳ doanh số đã đồng bộ.</p>}
 </section>;
}

const amount=(value:number|null)=>value===null?'Chưa đủ dữ liệu':money(value);
const quantity=(value:number)=>value.toLocaleString('vi-VN');
const pageSize=10;

export function NovaSalesDetail(){
 const {month=''}=useParams();
 const [search,setSearch]=useState(''),[page,setPage]=useState(1);
 const {data,isLoading,error,refetch}=useQuery({
  queryKey:['nova-sales-detail',month],
  queryFn:()=>api<NovaSalesDetailData>('/reports/nova-sales/'+encodeURIComponent(month)),
 });
 const back=<Link className="back-link" to="/reports">← Báo cáo</Link>;
 if(isLoading)return <>{back}<Loading/></>;
 if(!data)return <>{back}<ErrorBox error={error} retry={()=>refetch()}/></>;

 const query=search.trim().toLocaleLowerCase('vi-VN');
 const products=data.products.filter(p=>[p.sku,p.name,p.category].some(value=>value.toLocaleLowerCase('vi-VN').includes(query)));
 const activePage=Math.min(page,Math.max(1,Math.ceil(products.length/pageSize)));
 const metrics=[
  ['Doanh thu thuần',money(data.revenue)],
  ['Doanh số trước hoàn',money(data.sales_amount)],
  ['Giá trị hoàn hàng',money(data.refund_amount)],
  ['Số đơn được tạo',quantity(data.orders_created)],
  ['Giá vốn',amount(data.cost_of_goods)],
  ['Chi phí đã ghi nhận',amount(data.expenses)],
 ];
 return <>
  {back}
  <PageHeader title={'Doanh số tháng '+monthLabel(data.month)}
   description={'Nova Commerce · Đồng bộ lúc '+date(data.synced_at)}
   action={<Link className="btn primary" to={askAI(data.month)}>Hỏi AI <ArrowUpRight size={16}/></Link>}/>
  {data.sync_failed&&<p className="padded subtle" role="status">Lượt đồng bộ gần nhất lỗi. Đang hiển thị dữ liệu từ lần đồng bộ thành công gần nhất.</p>}
  <div className="metric-grid three">{metrics.map(([label,value])=><div className="metric-card" key={label}>
   <span>{label}</span><strong className="money-value">{value}</strong>
  </div>)}</div>
  <section className="card padded note">
   <p><b>Lợi nhuận vận hành</b> {amount(data.operating_profit)}</p>
   <p>Đơn được đếm theo ngày đặt. Doanh số và hoàn hàng được ghi nhận theo ngày phát sinh, theo giờ Việt Nam.</p>
  </section>
  <section className="card">
   <div className="card-head"><h3>Doanh thu theo danh mục</h3></div>
   {data.categories.length?<div className="table-wrap"><table aria-label="Doanh thu theo danh mục">
    <thead><tr><th scope="col">Danh mục</th><th scope="col">Doanh thu thuần</th></tr></thead>
    <tbody>{data.categories.map(row=><tr key={row.category}><td>{row.category}</td><td>{money(row.revenue)}</td></tr>)}</tbody>
   </table></div>:<Empty text="Chưa có giao dịch ghi nhận trong kỳ này."/>}
  </section>
  <section className="card">
   <div className="card-head"><h3>Chi tiết theo sản phẩm</h3></div>
   {!!data.products.length&&<div className="filters"><input aria-label="Tìm sản phẩm trong báo cáo" placeholder="Tìm theo SKU, tên hoặc danh mục" value={search} onChange={e=>{setSearch(e.target.value);setPage(1)}}/></div>}
   {products.length?<><div className="table-wrap"><table aria-label="Doanh số theo sản phẩm">
    <thead><tr><th scope="col">SKU</th><th scope="col">Sản phẩm</th><th scope="col">Danh mục</th><th scope="col">Đã bán</th><th scope="col">Đã hoàn</th><th scope="col">Doanh số trước hoàn</th><th scope="col">Giá trị hoàn hàng</th><th scope="col">Doanh thu thuần</th></tr></thead>
    <tbody>{products.slice((activePage-1)*pageSize,activePage*pageSize).map(p=><tr key={p.sku}>
     <td>{p.sku}</td><td>{p.name}</td><td>{p.category}</td><td>{quantity(p.sold)}</td><td>{quantity(p.returned)}</td><td>{money(p.sales_amount)}</td><td>{money(p.refund_amount)}</td><td>{money(p.revenue)}</td>
    </tr>)}</tbody>
   </table></div><Pagination page={activePage} total={products.length} size={pageSize} onChange={setPage}/></>:<Empty text={query?'Thử một SKU, tên hoặc danh mục khác.':'Chưa có sản phẩm phát sinh doanh số hoặc hoàn hàng trong kỳ.'}/>}
  </section>
 </>;
}
