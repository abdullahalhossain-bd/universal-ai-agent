// Thin fetch wrapper. In dev, Vite proxies /v1/* to the FastAPI backend (see vite.config.js); in prod, set VITE_API_BASE_URL to the deployed API origin at build time.
const API_BASE = import.meta.env.VITE_API_BASE_URL || ''
const TOKEN_KEY = 'merchant_console_token'
const ADMIN_TOKEN_KEY = 'platform_admin_token'
export function getToken() { return localStorage.getItem(TOKEN_KEY) }
export function setToken(token) { if (token) localStorage.setItem(TOKEN_KEY, token); else localStorage.removeItem(TOKEN_KEY) }
export function getAdminToken() { return localStorage.getItem(ADMIN_TOKEN_KEY) }
export function setAdminToken(token) { if (token) localStorage.setItem(ADMIN_TOKEN_KEY, token); else localStorage.removeItem(ADMIN_TOKEN_KEY) }
export class ApiError extends Error { constructor(status, detail) { super(typeof detail === 'string' ? detail : 'Request failed'); this.status = status; this.detail = detail } }
async function request(path, { method='GET', body, auth=true, headers={}, token=null }={}) {
  const finalHeaders={...headers}; if(body!==undefined) finalHeaders['Content-Type']='application/json';
  if(auth){const resolvedToken=token??getToken();if(resolvedToken) finalHeaders['Authorization']=`Bearer ${resolvedToken}`}
  const res=await fetch(`${API_BASE}${path}`,{method,headers:finalHeaders,body:body!==undefined?JSON.stringify(body):undefined});
  let data=null; const text=await res.text(); if(text){try{data=JSON.parse(text)}catch{data=text}}
  if(!res.ok){const detail=data&&typeof data==='object'&&'detail' in data?data.detail:data;throw new ApiError(res.status,detail||`Request failed (${res.status})`)} return data
}
export const api={get:(path,opts)=>request(path,{...opts,method:'GET'}),post:(path,body,opts)=>request(path,{...opts,method:'POST',body}),put:(path,body,opts)=>request(path,{...opts,method:'PUT',body}),patch:(path,body,opts)=>request(path,{...opts,method:'PATCH',body}),del:(path,opts)=>request(path,{...opts,method:'DELETE'})}
export const adminApi={get:(path,opts)=>request(path,{...opts,method:'GET',token:getAdminToken()}),post:(path,body,opts)=>request(path,{...opts,method:'POST',body,token:getAdminToken()}),patch:(path,body,opts)=>request(path,{...opts,method:'PATCH',body,token:getAdminToken()})}
