type Usage={input_tokens?:unknown;output_tokens?:unknown;complete?:boolean;source?:string;model_calls?:number;reported_calls?:number};
const count=(value:unknown)=>typeof value==='number'&&Number.isSafeInteger(value)&&value>=0?value.toLocaleString('en-US'):null;
export function agentTokenUsage(usage:Usage|undefined,status:string){
 if(status==='streaming')return {text:'Input — · Output — tokens',title:'Provider token usage is available when the answer completes.'};
 if(!usage)return {text:'Token usage unavailable',title:'Token counts were not recorded for this answer.'};
 const input=count(usage.input_tokens),output=count(usage.output_tokens);
 if(input===null&&output===null)return {text:'Token usage unavailable',title:'The model provider did not report token counts.'};
 return {text:`Input ${input??'—'} · Output ${output??'—'} tokens${usage.complete?'':' · partial'}`,
  title:usage.source==='no_model_calls'?'No model calls were needed for this response.':`Provider-reported totals for this answer turn, including routing and answer generation. ${usage.reported_calls??0} of ${usage.model_calls??0} calls reported both counts. Embedding requests are excluded.`};
}
