const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');const Module=require('node:module');const ts=require('typescript');
const file=path.resolve(__dirname,'../../ags_frontend/app/agent-commands.ts');const compiled=new Module(file,module);compiled._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,file);const {agentCommands,agentMention,agentOperation,insertAgentCommand}=compiled.exports;
test('four registered direct shortcuts are offered',()=>{assert.deepEqual(agentCommands.map(c=>c.label),['/Onboard','/Upload','/Extract','/ReExtract']);assert.deepEqual(agentMention('/',1),{start:0,end:1,query:''});assert.equal(agentMention('/Ex',3).query,'Ex');assert.deepEqual(agentMention('  /up',5),{start:2,end:5,query:'up'});assert.deepEqual(agentMention('@',1),{start:0,end:1,query:''});assert.equal(agentMention('@Ex',3).query,'Ex');assert.equal(agentMention('@on',3).query,'on');});
test('only a leading complete user command selects a route',()=>{assert.equal(agentOperation('@Upload documents'),'upload');assert.equal(agentOperation('  @EXTRACT\n'),'extract');assert.equal(agentOperation('  @onBOARD\n'),'onboard');assert.equal(agentOperation(' @reEXTRACT saved documents'),'reextract');assert.equal(agentMention('@re',3).query,'re');for(const text of ['email@Upload','Describe @Extract','"@Upload"','@Uploader','@Reextractor','@Onboarded','Describe @Onboard'])assert.equal(agentOperation(text),undefined);for(const text of ['email@Upload','Describe @Extract','@Extract #file'])assert.equal(agentMention(text,text.length),null);});
test('choosing a command preserves text following the caret',()=>{assert.equal(insertAgentCommand('@Ex then details',{start:0,end:3},'@Extract'),'@Extract  then details');assert.equal(agentOperation(insertAgentCommand('@',{start:0,end:1},'@Upload')),'upload');});
test('a standalone re-extract request opens the direct workflow, while explanations remain questions',()=>{for(const text of ['re-extract','Reextract.','RE EXTRACT!'])assert.equal(agentOperation(text),'reextract');for(const text of ['what is re-extract','re-extract?','how do I re-extract'])assert.equal(agentOperation(text),undefined);});
test('malformed shortcuts reopen choices and cannot be sent as knowledge questions',()=>{
 const {agentInputIssue}=compiled.exports;
 for(const text of ['@\\','@@','@Uplaod','@Ex','@Uploader','@Onb','@Onboarded']){assert.ok(agentInputIssue(text));assert.equal(agentMention(text,text.length)?.start,0);}
 assert.equal(agentMention('@\\',2).query,'');
 assert.equal(insertAgentCommand('@\\',{start:0,end:2},'@Upload'),'@Upload ');
 for(const text of ['?','...','\\'])assert.ok(agentInputIssue(text));
 for(const text of ['@Onboard','@onboard new dataset','@Upload files','@Extract','@ReExtract','email upload@example.com','Describe @Extract','can you list douccments names','8192?'])assert.equal(agentInputIssue(text),'');
});
test('slash is the command key and earlier @ commands keep working',()=>{
 const {agentInputIssue}=compiled.exports;
 assert.equal(agentOperation('/Extract fields from invoices'),'extract');assert.equal(agentOperation(' /reextract'),'reextract');assert.equal(agentOperation('@Upload files'),'upload');
 assert.equal(insertAgentCommand('/Ex then details',{start:0,end:3},'/Extract'),'/Extract  then details');
 for(const text of ['/Uplaod','/','/Onboarded','/ex'])assert.match(agentInputIssue(text),/Choose \/Onboard, \/Upload, \/Extract or \/ReExtract/);
 for(const text of ['/docs/handbook.pdf what does it say','and/or questions','Summarize /Upload'])assert.equal(agentInputIssue(text),'');
 for(const text of ['Summarize /Upload','a/Extract'])assert.equal(agentOperation(text),undefined);
});
