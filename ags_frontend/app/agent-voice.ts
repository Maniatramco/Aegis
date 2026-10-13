export type SpeechEnvironment={SpeechRecognition?:new()=>any;webkitSpeechRecognition?:new()=>any};
export function speechCapabilities(environment:SpeechEnvironment){return {input:Boolean(environment.SpeechRecognition||environment.webkitSpeechRecognition)};}
export function startSpeechInput(environment:SpeechEnvironment,callbacks:{text:(text:string)=>void;listening:(value:boolean)=>void;error:(message:string)=>void},language:string){
 const Constructor=environment.SpeechRecognition||environment.webkitSpeechRecognition;
 if(!Constructor)throw new Error('Speech recognition is unavailable in this browser. You can type the request.');
 const recognition=new Constructor();recognition.lang=language;recognition.interimResults=false;recognition.continuous=false;
 recognition.onresult=(event:any)=>{const transcript=event.results?.[0]?.[0]?.transcript;if(typeof transcript==='string'&&transcript.trim())callbacks.text(transcript);};
 recognition.onerror=(event:any)=>{callbacks.listening(false);callbacks.error(event.error==='not-allowed'?'Microphone permission was denied. You can still type your request.':`Speech input could not finish (${event.error||'unavailable'}). You can type instead.`);};
 recognition.onend=()=>callbacks.listening(false);recognition.start();callbacks.listening(true);return recognition;
}
