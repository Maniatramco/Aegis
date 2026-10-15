const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
function load(name){const file=path.resolve(__dirname,'../../ags_frontend/app',name),m=new Module(file,module);m.paths=module.paths;m._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,file);return m.exports;}
test('onboard-only preserves supplied details, chooses real defaults and keeps extraction separate',()=>{
 const {onboardingDraft,onboardingModelSelection}=load('onboarding-draft.ts');const {agentOperation}=load('agent-commands.ts');
 const request='can you onboard a dataset for me with the name of "TermSheet Dataset" and Description : "Sample Termsheet Extraction Dataset"';
 assert.equal(agentOperation(request),'onboard');
 assert.deepEqual(onboardingDraft(request,{name:'',description:''}),{name:'TermSheet Dataset',description:'Sample Termsheet Extraction Dataset',process_documents:false});
 assert.equal(onboardingDraft('@Onboard dataset named “Contracts” and then extract documents').process_documents,true);
 assert.equal(onboardingDraft('Onboard dataset called "Contracts" only, do not extract').process_documents,false);
 assert.equal(agentOperation('extract'),'extract');assert.equal(agentOperation('@Extract extract fields'),'extract');assert.equal(agentOperation('How can I onboard a dataset?'),undefined);
 const roles=[['embedding_model_id','embedding'],['default_chat_model_id','chat'],['default_extraction_model_id','extraction']];
 const models=[{id:'bad',enabled:false,credential_configured:true,capabilities:['embedding']},{id:'emb',enabled:true,credential_configured:true,capabilities:['embedding']},{id:'one',enabled:true,credential_configured:true,capabilities:['chat','extraction']},{id:'two',enabled:true,credential_configured:true,capabilities:['chat','extraction']}];
 assert.deepEqual(onboardingModelSelection(models,roles,{default_chat_model_id:'two'}),{embedding_model_id:'emb',default_chat_model_id:'two',default_extraction_model_id:'one'});
 assert.equal(onboardingModelSelection(models,roles,{default_chat_model_id:'two'},{default_chat_model_id:'one'}).default_chat_model_id,'one');
});
