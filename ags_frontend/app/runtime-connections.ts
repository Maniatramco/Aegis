type Location='local'|'oci'|'unknown';
type Environment=Record<string,string|undefined>;
const location=(value:string|undefined):Location=>value==='local'||value==='oci'?value:'unknown';

// Deployment metadata describes configured hosting, without probing providers.
// Keep credentials, query strings and private key paths out of the response.
export function runtimeConnections(base:string,env:Environment){
 const target=location(env.AEGIS_DEPLOYMENT_TARGET||'local');
 let endpoint='Configured internal API',internal=false;
 try{const url=new URL(base);endpoint=url.origin;internal=['api','localhost','127.0.0.1','::1','[::1]','host.docker.internal'].includes(url.hostname);}catch{}
 const api=location(env.AEGIS_API_LOCATION||(internal?target:undefined));
 return {
  web:{provider:target,name:'Next.js',detail:target==='oci'?'Hosted on OCI OKE.':'Serves this WebApp from its configured application host.'},
  api:{provider:api,name:'FastAPI',endpoint,detail:'WebApp requests reach FastAPI through the /api proxy. This successful status response confirms the API is reachable.'},
  worker:{provider:location(env.AEGIS_WORKER_LOCATION),name:'Processing worker',detail:'Configured host for indexing, extraction and recovery. This footer does not probe worker health.'},
  models:{provider:location(env.AEGIS_MODEL_LOCATION),name:env.AEGIS_MODEL_LOCATION==='local'?'Laptop models':'Configured models',detail:env.AEGIS_MODEL_LOCATION==='local'&&target==='oci'?'Default Qwen, embedding and OCR models run on your laptop through the private SSH tunnel. Keep the laptop and Docker online.':'Configured default model host. A request-specific model selection may use a different provider.'},
 };
}
