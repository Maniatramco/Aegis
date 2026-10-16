type Location='local'|'oci'|'gcp'|'aws'|'azure'|'openai'|'unknown';
type Environment=Record<string,string|undefined>;
const location=(value:string|undefined):Location=>['local','oci','gcp','aws','azure','openai'].includes(value||'')?value as Location:'unknown';
const LOCATION_LABELS:Record<Location,string>={local:'Local',oci:'OCI',gcp:'GCP',aws:'AWS',azure:'Azure',openai:'OpenAI',unknown:'Unknown'};
export const connectionLocation=(provider:string)=>Object.hasOwn(LOCATION_LABELS,provider)?LOCATION_LABELS[provider as Location]:'Unknown';

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
  models:{provider:location(env.AEGIS_MODEL_LOCATION),name:env.AEGIS_MODEL_LOCATION==='local'?'Laptop models':'Configured models',detail:env.AEGIS_MODEL_LOCATION==='local'&&target==='oci'?'Configured local model service through the private relay. Dataset defaults may use a cloud provider instead.':'Configured default model host. A request-specific model selection may use a different provider.'},
 };
}

export type ModelConnection={id?:string;provider?:string;provider_model?:string;enabled?:boolean;mapping_enabled?:boolean;connection?:{protocol?:string;endpoint?:string;region?:string}};
export type ModelDataset={id?:string;active?:boolean;models?:ModelConnection[];default_chat_model_id?:string;default_extraction_model_id?:string;embedding_model_id?:string};

// Use already-authorized dataset metadata, not model names or a stale deployment
// hint. Reading this summary never calls a model provider or exposes credentials.
export function modelConnectionSummary(datasets:ModelDataset[],datasetId?:string){
 const scope=datasetId?datasets.filter(dataset=>dataset.id===datasetId):datasets.filter(dataset=>dataset.active!==false);
 const models:ModelConnection[]=scope.flatMap(dataset=>{
  const defaults=new Set([dataset.default_chat_model_id,dataset.default_extraction_model_id,dataset.embedding_model_id].filter(Boolean));
  return (dataset.models||[]).filter(model=>model.enabled!==false&&model.mapping_enabled!==false&&(!defaults.size||defaults.has(model.id)));
 });
 const hosts=new Set<Location>(),names=new Set<string>(),endpoints=new Set<string>(),regions=new Set<string>();
 const labels=new Set<string>();
 for(const model of models){
  const protocol=model.connection?.protocol||model.provider||'';
  let host='',endpoint='';
  try{const url=new URL(model.connection?.endpoint||'');if(['http:','https:'].includes(url.protocol)){host=url.hostname.toLowerCase();endpoint=url.origin;}}catch{}
  let provider:Location='unknown',label='Unreported provider';
  if(protocol==='vertex'||protocol==='gemini'||host==='generativelanguage.googleapis.com'||host==='aiplatform.googleapis.com'||host.endsWith('-aiplatform.googleapis.com')){provider='gcp';label=protocol==='vertex'||host.includes('aiplatform')?'Google Vertex AI':'Google Gemini';}
  else if(protocol==='ollama'){provider='local';label='Ollama';}
  else if(protocol==='oci'){provider='oci';label='OCI Generative AI';}
  else if(protocol==='bedrock'){provider='aws';label='AWS Bedrock';}
  else if(protocol==='azure-openai'){provider='azure';label='Azure OpenAI';}
  else if(protocol==='openai'||host==='api.openai.com'){provider='openai';label='OpenAI';}
  hosts.add(provider);labels.add(label);
  if(model.provider_model)names.add(model.provider_model);
  if(endpoint)endpoints.add(endpoint);
  if(model.connection?.region)regions.add(model.connection.region);
 }
 const locations=(['local','gcp','oci','aws','azure','openai','unknown'] as Location[]).filter(host=>hosts.has(host));
 return {
  provider:locations.length===1?locations[0]:locations.length?'mixed':'unknown',locations,
  name:labels.size?[...labels].join(' / '):'No enabled mapped models reported',
  detail:models.length?`${datasetId?'Selected dataset':'Accessible active datasets'}: ${names.size?[...names].join(', '):'configured models'}. Uses saved default model connections; an individual request may select a different mapped model. This is not a provider health check.`:'No enabled model connection metadata is available for this scope.',
  endpoint:[...endpoints].join(', '),region:[...regions].join(', '),
 };
}