import './agent-logo.css';

/** Shared Aegis Agent identity; keep the platform brand and workflow status icons separate. */
export function AgentLogo({size=24,label=''}:{size?:number;label?:string}){
 return <img className="aegis-agent-logo" src="/aegis-agent-logo-v2.webp" width={size} height={size} alt={label} aria-hidden={label?undefined:true}/>;
}
