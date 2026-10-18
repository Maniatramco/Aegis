"use client";
import {useState,useRef,useEffect, type FormEvent} from 'react';
import {ShieldCheck, X} from 'lucide-react';

export type FeatureAccount = {id:string;username:string;features?:{data_governance?:boolean};feature_access_version?:number|null;feature_access_available?:boolean};
type Props = {account:FeatureAccount;api:(path:string,method?:string,body?:any)=>Promise<any>;onSaved:(account:any)=>void;onClose:()=>void;onBusy?:(busy:boolean)=>void};

export function UserFeatureAccess({account,api,onSaved,onClose,onBusy}:Props){
 const [enabled,setEnabled]=useState(account.features?.data_governance===true);
 const [password,setPassword]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const panel=useRef<HTMLElement>(null);
 useEffect(()=>{panel.current?.scrollIntoView({block:'nearest'});panel.current?.querySelector<HTMLInputElement>('input[role=switch]')?.focus();},[]);
 const available=account.feature_access_available!==false;
 const dirty=available&&enabled!==(account.features?.data_governance===true);
 async function submit(event:FormEvent){
  event.preventDefault();if(busy||!dirty)return;
  if(!password){setError('Enter your administrator password to save feature access.');return;}
  setBusy(true);onBusy?.(true);setError('');setNotice('');
  try{
   const result=await api('/users/'+encodeURIComponent(account.id)+'/features','PUT',{
    features:{data_governance:enabled},expected_version:account.feature_access_version??0,current_password:password});
   setPassword('');onSaved(result.user);setNotice(`Data Governance ${result.user.features.data_governance?'enabled':'disabled'} for ${result.user.username}.`);
  }catch(reason){setError(reason instanceof Error?reason.message:'Feature access could not be saved. Refresh the user and try again.');}
  finally{setBusy(false);onBusy?.(false);}
 }
 return <section ref={panel} className="card user-feature-access" aria-labelledby="user-feature-title">
  <div className="account-summary"><div><h2 id="user-feature-title"><ShieldCheck size={19}/>Feature access — {account.username}</h2><p className="muted small">Control which features this account can open. User roles and dataset assignments are managed separately.</p></div><button type="button" className="btn icon" aria-label="Close feature access" disabled={busy} onClick={onClose}><X size={17}/></button></div>
  <form onSubmit={submit} aria-label={`Feature access for ${account.username}`}>
   <fieldset disabled={busy||!available}>
    <label className="feature-access-option"><span><strong>Data Governance</strong><small>Catalog, policies, quality reports and governance operations.</small><small>Editing and publication still require an administrator role. Operational policies still require two enabled administrators.</small></span><input type="checkbox" role="switch" aria-label={`Enable Data Governance for ${account.username}`} checked={enabled} onChange={event=>{setEnabled(event.target.checked);setNotice('');}}/></label>
    <p className="feature-access-help">Initially enabled only for the exact username <strong>mani</strong>. Every other account, including other administrators, starts disabled. You can grant or revoke access here.</p>
    <label className="feature-access-password">Your administrator password<input type="password" aria-label="Administrator password for feature access" autoComplete="current-password" maxLength={200} required disabled={!dirty||busy} value={password} onChange={event=>setPassword(event.target.value)}/></label>
    <div className="row"><button type="submit" className="btn primary" disabled={!dirty||!password||busy}>{busy?'Saving…':'Save feature access'}</button><button type="button" className="btn" onClick={onClose}>Close</button><small className="muted">{dirty?'Unsaved change':`Saved setting · version ${account.feature_access_version??0}`}</small></div>
   </fieldset>
  </form>
  {!available&&<p role="alert" className="notice error">Saved feature access is unavailable. Data Governance is blocked for this account. Restore its saved access snapshot before changing the setting; sign-in and other account controls remain available.</p>}
  <p className="feature-access-help">Changes apply to existing sessions. Approved masking and legal holds continue to protect datasets when module access is disabled.</p>
  {error&&<p role="alert" className="notice error">{error}</p>}{notice&&<p role="status" className="notice">{notice}</p>}
 </section>;
}
