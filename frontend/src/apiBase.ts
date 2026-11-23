export function resolveApiBase(value?: string): string {
 const configured=value?.trim();
 if(!configured)return '/api';
 const url=new URL(configured);
 if(!['https:','http:'].includes(url.protocol)||url.username||url.password||url.search||url.hash){
  throw new Error('Configure VITE_API_BASE_URL as the public backend URL.');
 }
 return url.href.replace(/\/+$/,'');
}
