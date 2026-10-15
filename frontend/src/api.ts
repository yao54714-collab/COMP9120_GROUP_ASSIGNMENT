export type Row = Record<string, any>;
export type Boot = {user:Row; customers:Row[];pets:Row[];services:Row[];employees:Row[];stations:Row[];skills:Row[];consumables:Row[];recipes:Row[]};
export class ApiError extends Error { constructor(message:string,public status:number){super(message)} }
export async function api<T=any>(path:string,method='GET',body?:unknown):Promise<T> {
  const response=await fetch('/api'+path,{method,credentials:'same-origin',headers:{'Content-Type':'application/json','X-PawCare-Client':'web'},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await response.json();
  if(!response.ok)throw new ApiError(typeof data.detail==='string'?data.detail:'The request failed. Please try again.',response.status);
  return data;
}
export const money=(value:any)=>new Intl.NumberFormat('en-AU',{style:'currency',currency:'AUD'}).format(Number(value||0)).replace('$','A$');
export const dateTime=(value:any)=>value?new Intl.DateTimeFormat('en-AU',{timeZone:'Australia/Sydney',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value)):'Unscheduled';
export function localDate(value:Date|string=new Date()) {
  const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Australia/Sydney',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date(value));
  const v=(key:string)=>parts.find(p=>p.type===key)!.value;
  return `${v('year')}-${v('month')}-${v('day')}`;
}
export function dateOffset(days:number){const d=new Date(localDate()+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+days);return d.toISOString().slice(0,10);}
export function inputTime(value:string){const p=new Intl.DateTimeFormat('sv-SE',{timeZone:'Australia/Sydney',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value));return p.replace(' ','T');}
export const labels:Row={requested:'Requested',confirmed:'Confirmed',scheduled:'Scheduled',in_progress:'In progress',in_service:'In service',completed:'Completed',cancelled:'Cancelled',no_show:'No-show',manager:'Manager',receptionist:'Receptionist',groomer:'Groomer',customer:'Customer',dog:'Dog',cat:'Cat',wash:'Bathing',groom:'Grooming',ml:'mL',g:'g',unit:'units',cash:'Cash',card:'Card',transfer:'Bank transfer',receipt:'Receipt',use:'Care usage',waste:'Waste',adjustment:'Adjustment',female:'Female',male:'Male',unknown:'Unknown'};
