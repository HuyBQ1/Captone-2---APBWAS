export type Row = Record<string, any>;
export async function api<T = Row>(path: string, options: RequestInit = {}): Promise<T> {
  const result = await fetch('/api'+path, {credentials:'include',...options,headers:{...(!(options.body instanceof FormData) ? {'Content-Type':'application/json'} : {}),...options.headers}});
  if (!result.ok) {
    if(result.status===401 && !path.includes('/auth/')) window.dispatchEvent(new Event('session-expired'));
    const body = await result.json().catch(()=>({}));
    const error = new Error(body.error?.message || 'Không thể kết nối máy chủ. Vui lòng thử lại.') as Error & {status:number};
    error.status = result.status; throw error;
  }
  return result.json();
}
export const post = (path:string,body:Row={}) => api(path,{method:'POST',body:JSON.stringify(body)});
export const money = (value:number) => new Intl.NumberFormat('vi-VN',{style:'currency',currency:'VND',maximumFractionDigits:0}).format(value||0);
export const date = (value:string) => new Intl.DateTimeFormat('vi-VN',{dateStyle:'medium',timeStyle:'short',timeZone:'Asia/Ho_Chi_Minh'}).format(new Date(value));
export const statusLabels: Record<string,string> = {queued:'Trong hàng đợi',planning:'Lập kế hoạch',running:'Đang thực thi',waiting_approval:'Chờ phê duyệt',completed:'Hoàn tất',failed:'Thất bại',cancelled:'Đã hủy',pending:'Chờ xử lý',approved:'Đã duyệt',rejected:'Từ chối',expired:'Hết hạn',uploaded:'Đã tải lên',processing:'Đang indexing',indexed:'Đã lập chỉ mục'};
