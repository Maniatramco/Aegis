import './agent-logo.css';

/** Shared Agent identity uses the supplied Aegis shield; workflow status icons stay separate. */
export function AgentLogo({size=24,label=''}:{size?:number;label?:string}){
 return <img className="aegis-agent-logo" src="/aegis-platform-logo.png" width={size} height={size} alt={label} aria-hidden={label?undefined:true}/>;
}
