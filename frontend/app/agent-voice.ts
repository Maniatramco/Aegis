export type SpeechEnvironment={SpeechRecognition?:new()=>any;webkitSpeechRecognition?:new()=>any;SpeechSynthesisUtterance?:new(text:string)=>any;speechSynthesis?:{cancel:()=>void;speak:(utterance:any)=>void}};
export function speechCapabilities(environment:SpeechEnvironment){return {input:Boolean(environment.SpeechRecognition||environment.webkitSpeechRecognition),output:Boolean(environment.speechSynthesis&&environment.SpeechSynthesisUtterance)};}
export function startSpeechInput(environment:SpeechEnvironment,callbacks:{text:(text:string)=>void;listening:(value:boolean)=>void;error:(message:string)=>void},language:string){
 const Constructor=environment.SpeechRecognition||environment.webkitSpeechRecognition;
 if(!Constructor)throw new Error('Speech recognition is unavailable in this browser. You can type the request.');
 const recognition=new Constructor();recognition.lang=language;recognition.interimResults=false;recognition.continuous=false;
 recognition.onresult=(event:any)=>{const transcript=event.results?.[0]?.[0]?.transcript;if(typeof transcript==='string'&&transcript.trim())callbacks.text(transcript);};
 recognition.onerror=(event:any)=>{callbacks.listening(false);callbacks.error(event.error==='not-allowed'?'Microphone permission was denied. You can still type your request.':`Speech input could not finish (${event.error||'unavailable'}). You can type instead.`);};
 recognition.onend=()=>callbacks.listening(false);recognition.start();callbacks.listening(true);return recognition;
}
export function speakResponse(environment:SpeechEnvironment,text:string,onError:(message:string)=>void){
 if(!speechCapabilities(environment).output){onError('Speech playback is unavailable in this browser.');return;}
 try{environment.speechSynthesis!.cancel();const utterance=new environment.SpeechSynthesisUtterance!(text);utterance.rate=1;utterance.onerror=()=>onError('The browser could not play the spoken response. The text response is still available.');environment.speechSynthesis!.speak(utterance);}catch{onError('The browser could not play the spoken response. The text response is still available.');}
}
