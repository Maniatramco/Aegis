"use client";
import {ActionButton} from "./action-button";
import {useEffect,useState} from 'react';
import {Cloud,HardDrive,CheckCircle2,Archive,Database} from 'lucide-react';
import {WorkflowStepper} from './workflow-stepper';
import './storage-configuration.css';
type Entity=Record<string,any>;
type Api=(path:string,method?:string,body?:any)=>Promise<any>;
export function DatabaseConfiguration({api,onChanged}:{api:Api;onChanged:()=>void}){
 const [form,setForm]=useState<Entity|null>(null),[info,setInfo]=useState<Entity>({}),[busy,setBusy]=useState(''),[error,setError]=useState(''),[message,setMessage]=useState(''),[receipt,setReceipt]=useState<Entity>({});
 const load=async()=>{const data=await api('/storage/database');setInfo(data);setForm({...data.form,password:'',wallet_password:''});};
 useEffect(()=>{void load().catch(e=>setError(e.message));},[]);
 const run=async(operation:string,label:string)=>{if(!form)return;setBusy(label);setError('');setMessage('');try{
  const result=await api('/storage/database'+(operation==='save'?'':'/'+operation),operation==='save'?'PUT':'POST',form);setReceipt(result);setMessage(result.message);
  if(operation==='save'||operation==='activate'){await load();if(operation==='activate')onChanged();}
 }catch(e){setError(e instanceof Error?e.message:'Database operation failed.');}finally{setBusy('');}};
 const field=(key:string,label:string,secret=false)=><label className="storage-field" key={key}><span>{label}</span><input aria-label={label} type={secret?'password':'text'} autoComplete={secret?'off':undefined} value={form?.[key]||''} disabled={!!busy} onChange={e=>{setForm({...form,[key]:e.target.value});setReceipt({});}}/>{secret&&info[key+'_saved']&&<small className="muted">Saved securely. Leave blank to reuse it for this connection.</small>}</label>;
 if(!form)return <section className="panel" role="status">{error||'Loading database configuration…'}</section>;
 return <section className="panel" aria-label="Database and knowledge storage">
   <div className="panel-head"><h2>Database &amp; knowledge</h2><span className="pill blue">Active: {info.active_provider==='oci'?'OCI Oracle 26ai':'Local database'}</span></div>
  <div className="storage-provider-options" role="group" aria-label="Database destination">
   <button className={'storage-provider'+(form.provider==='local'?' selected':'')} aria-pressed={form.provider==='local'} disabled={!!busy} onClick={()=>{setForm({...form,provider:'local'});setReceipt({});}}><HardDrive size={22}/><span><strong>Local</strong><small className="muted">Laptop database · Qdrant search</small></span></button>
   <button className={'storage-provider'+(form.provider==='oci'?' selected':'')} aria-pressed={form.provider==='oci'} disabled={!!busy} onClick={()=>{setForm({...form,provider:'oci'});setReceipt({});}}><Database size={22}/><span><strong>OCI Oracle 26ai</strong><small className="muted">Metadata · Native vector search</small></span></button>
  </div>
  {form.provider==='oci'?<>
   <div className="storage-fields">{field('name','Database name')}{field('region','Database region')}{field('username','Database username')}{field('dsn','Connection alias or TCPS string')}
    <label className="storage-field"><span>Database authentication</span><select aria-label="Database authentication" value={form.auth_mode} disabled={!!busy} onChange={e=>{setForm({...form,auth_mode:e.target.value});setReceipt({});}}><option value="mtls">Wallet (mTLS)</option><option value="tls">TLS without wallet</option></select></label>
    {field('password','Database password',true)}
    {form.auth_mode==='mtls'&&<>{field('wallet_directory','Mounted wallet directory')}{field('wallet_password','Wallet password',true)}</>}
   </div>
   <p className="small muted">{info.wallet_ready?'Wallet mount detected.':'Wallet mount not available.'} Use the password for an existing Oracle database user and the separate password chosen for the downloaded wallet. Passwords are encrypted locally and never returned by the API.</p>
  </>:<p className="small muted">Use the existing {info.local_database==='oracle'?'Oracle database':'database'} on this laptop and Qdrant. File storage keeps its independently selected destination.</p>}
  <div className="storage-actions">
   <ActionButton className="btn" disabled={!!busy} onClick={()=>run('test','Testing database connection')} label="Test database connection" action="status"/>
   <ActionButton className="btn" disabled={!!busy} onClick={()=>run('save','Saving database configuration')} label="Save database configuration" action="save"/>
   {form.provider==='oci'&&<ActionButton className="btn" disabled={!!busy||!receipt.ok} onClick={()=>run('prepare','Creating Aegis tables')} label="Create Aegis tables" action="database"/>}
   <button className="btn primary" disabled={!!busy||(form.provider==='oci'&&!receipt.schema_ready)} onClick={()=>run('activate','Copying catalog and activating database')}><CheckCircle2 size={16}/>Activate {form.provider==='oci'?'OCI database':'Local database'}</button>
  </div>
  {receipt.ok&&<p className="small muted">{receipt.tables_present} of {receipt.tables_required} Aegis tables available · Native vector search verified</p>}
  <p className="small muted">Test and Save do not switch the active database. Activation verifies the copied catalog and compatible vectors before switching both API and worker. Original files retain their saved destinations; the previous database is preserved.</p>
  {busy&&<WorkflowStepper label="Database configuration" steps={[{id:'database-operation',label:busy,status:'running'}]}/>}
  {message&&<div className="notice" role="status">{message}</div>}{error&&<div className="notice warn" role="alert">{error}</div>}
 </section>;
}
export function StorageConfiguration({api,onChanged,onFreshStart,connections}:{api:Api;onChanged:()=>void;onFreshStart?:()=>void;connections?:React.ReactNode}){
 const [form,setForm]=useState<Entity|null>(null),[current,setCurrent]=useState<Entity>({}),[workspace,setWorkspace]=useState<Entity>({}),[busy,setBusy]=useState(''),[message,setMessage]=useState(''),[error,setError]=useState(''),[confirmation,setConfirmation]=useState(''),[restore,setRestore]=useState('');
 const load=async()=>{const [data,preview]=await Promise.all([api('/storage'),api('/workspace/reset-preview')]);setCurrent(data);setWorkspace(preview);setForm({storage_provider:'local',oci_storage_prefix:'aegis',oci_storage_auth_mode:'config_file',oci_storage_profile:'DEFAULT',oci_storage_config_file:'/run/oci/config',oci_storage_key_file:'/run/oci/aegis_api_key.pem',...data.destination,local_storage_path:data.destination.local_storage_path||data.local_root});};
 useEffect(()=>{void load().catch(e=>setError(e.message));},[]);
 const run=async(label:string,action:()=>Promise<void>)=>{setBusy(label);setError('');setMessage('');try{await action();}catch(e){setError(e instanceof Error?e.message:'Storage operation failed.');}finally{setBusy('');}};
 const field=(key:string,label:string,help?:string)=><label className="storage-field" key={key}><span>{label}</span><input aria-label={label} value={form?.[key]||''} disabled={!!busy} onChange={e=>setForm({...form,[key]:e.target.value})}/>{help&&<small className="muted">{help}</small>}</label>;
 if(!form)return <section className="panel" role="status">{error||'Loading storage configuration…'}</section>;
 return <div className="storage-settings">
  <section className="panel">
   <div className="panel-head"><h2>File storage</h2><span className="pill blue">Active: {current.destination?.storage_provider==='oci'?'OCI bucket':'Local'}</span></div>
   <div className="storage-provider-options" role="group" aria-label="New file storage destination">{[['local','Local',HardDrive],['oci','OCI Object Storage',Cloud]].map(([value,label,Icon]:any)=><button key={value} className={`storage-provider${form.storage_provider===value?' selected':''}`} aria-pressed={form.storage_provider===value} disabled={!!busy} onClick={()=>setForm({...form,storage_provider:value})}><Icon size={22}/><strong>{label}</strong></button>)}</div>
   <p className="small muted">Existing files keep their saved location. Switching destination does not upload or migrate them.</p>
   {form.storage_provider==='local'?<div className="storage-fields">{field('local_storage_path','Local storage directory','A directory inside the mounted server storage root: '+current.local_root)}</div>:<>
    <div className="storage-fields">{field('oci_storage_namespace','OCI namespace')}{field('oci_storage_bucket','OCI bucket')}{field('oci_storage_region','OCI region')}{field('oci_storage_prefix','Object prefix')}
    <label className="storage-field"><span>Authentication</span><select aria-label="Storage authentication" value={form.oci_storage_auth_mode} disabled={!!busy} onChange={e=>setForm({...form,oci_storage_auth_mode:e.target.value})}><option value="config_file">API key configuration file</option><option value="instance_principal">OCI instance principal</option><option value="resource_principal">OCI resource principal</option></select></label>
    {form.oci_storage_auth_mode==='config_file'&&<>{field('oci_storage_profile','OCI profile')}{field('oci_storage_config_file','Mounted OCI config path')}{field('oci_storage_key_file','Mounted private key path')}</>}
    </div>
    {form.oci_storage_auth_mode==='config_file'&&<p className="small muted">Credential files are mounted read-only under {current.credential_mount}. Use server paths here; credentials stay outside application images. {current.credentials_mounted?'Config mount detected.':'Config mount is not available; configure the deployment mount first.'}</p>}
   </>}
   <div className="storage-actions"><ActionButton className="btn" disabled={!!busy} onClick={()=>run('Testing storage connection',async()=>{const result=await api('/storage/test','POST',form);setMessage(result.message);})} label="Test connection" action="status"/><ActionButton className="btn primary" disabled={!!busy} onClick={()=>run('Saving storage configuration',async()=>{const saved=await api('/storage','PUT',form);setMessage(saved.test.message+' New files will use this destination.');setCurrent({...current,destination:saved.destination});onChanged();})} label="Save storage configuration" action="save"/></div>
  </section>
  <DatabaseConfiguration api={api} onChanged={onChanged}/>
  {connections}
  <section className="panel">
   <div className="panel-head"><div><h2>Start fresh</h2><p className="muted">Archive the active datasets, originals, prompts, results, chats, job history and indexes locally, then clear the workspace.</p></div><Archive size={24}/></div>
   <div className="storage-counts">{[['Datasets','knowledge_base'],['Documents','document'],['Results','extraction'],['Prompts','template'],['Chats','conversation']].map(([label,key])=><div key={key}><strong>{workspace.counts?.[key]||0}</strong><span>{label}</span></div>)}<div><strong>{workspace.index_collections?.length||0}</strong><span>Index collections</span></div></div>
   <p className="small muted">Users, registered models, credentials and installed model weights stay available. Old files are not uploaded to OCI. Archives can be restored into an empty workspace.</p>
   <label className="storage-field"><span>Type START FRESH</span><input aria-label="Fresh start confirmation" value={confirmation} disabled={!!busy} onChange={e=>setConfirmation(e.target.value)}/></label>
   <ActionButton className="btn" disabled={!!busy||confirmation!=='START FRESH'||workspace.active_jobs>0} onClick={()=>run('Archiving workspace and clearing indexes',async()=>{const receipt=await api('/workspace/reset','POST',{confirmation});setConfirmation('');onFreshStart?.();await load();onChanged();setMessage('Fresh workspace ready. Recovery archive: '+receipt.id);})} label="Archive and start fresh" action="archive"/>
   {workspace.active_jobs>0&&<p role="status">Finish the {workspace.active_jobs} active jobs before starting fresh.</p>}
   {workspace.archives?.length>0&&<details className="storage-archives"><summary>Recovery archives ({workspace.archives.length})</summary><label className="storage-field"><span>Type RESTORE to restore an archive</span><input aria-label="Restore archive confirmation" value={restore} disabled={!!busy} onChange={e=>setRestore(e.target.value)}/></label>{workspace.archives.map((archive:Entity)=><div className="storage-archive" key={archive.id}><div><strong>{new Date(archive.created_at*1000).toLocaleString()}</strong><p className="small muted">{archive.counts?.knowledge_base||0} datasets · {archive.counts?.document||0} documents · {archive.status}</p><code>{archive.id}</code></div><ActionButton className="btn" disabled={!!busy||restore!=='RESTORE'||Object.values(workspace.counts||{}).some(v=>Number(v)>0)} onClick={()=>run('Restoring workspace archive',async()=>{await api(`/workspace/archives/${archive.id}/restore`,'POST',{confirmation:restore});setRestore('');await load();onChanged();setMessage('Workspace archive restored.');})} label="Restore workspace" action="restore"/></div>)}</details>}
  </section>
  {busy&&<WorkflowStepper label="Storage operation" steps={[{id:'storage-operation',label:busy,status:'running'}]}/>}
  {message&&<div className="notice" role="status">{message}</div>}{error&&<div className="notice warn" role="alert">{error}</div>}
 </div>;
}
