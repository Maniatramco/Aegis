/** Reset active chat only when a new authenticated login is established. */
export function prepareFreshLoginChat(storage:Pick<Storage,'getItem'|'setItem'|'removeItem'|'key'|'length'>,username:string,sessionId:string){
 if(!username||!sessionId)return false;
 const key=`aegis-agent-v2:${username}`,marker=key+'-login-session';
 if(storage.getItem(marker)===sessionId)return false;
 const transient=[key,key+'-conversation',key+'-prompts',key+'-onboarding',key+'-onboarding-request'];
 const keys=Array.from({length:storage.length},(_,i)=>storage.key(i)).filter((value):value is string=>!!value);
 for(const name of keys)if(transient.includes(name)||name.startsWith(key+'-onboarding-'))storage.removeItem(name);
 // An explicit empty history prevents automatic restoration of old goals.
 storage.setItem(key+'-history','[]');storage.setItem(marker,sessionId);
 return true;
}
