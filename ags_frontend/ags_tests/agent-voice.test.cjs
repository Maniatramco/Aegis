const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const ts=require('typescript');
const filename=path.resolve(__dirname,'../app/agent-voice.ts');
const compiled=new Module(filename,module);compiled.filename=filename;compiled.paths=module.paths;
compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,filename);
const {speechCapabilities,startSpeechInput}=compiled.exports;

test('unsupported browsers keep speech input disabled',()=>{
 assert.deepEqual(speechCapabilities({}),{input:false});
 assert.throws(()=>startSpeechInput({}, {}, 'en-US'),/You can type/);
});
test('speech recognition provides editable text only and handles permission denial',()=>{
 const text=[],state=[],errors=[];
 class Recognition{start(){this.started=true;}}
 const recognition=startSpeechInput({webkitSpeechRecognition:Recognition},{text:value=>text.push(value),listening:value=>state.push(value),error:value=>errors.push(value)},'en-US');
 assert.equal(recognition.continuous,false);assert.equal(recognition.interimResults,false);
 recognition.onresult({results:[[{transcript:'Re-extract this document'}]]});
 assert.deepEqual(text,['Re-extract this document']); // No send/execute callback exists.
 recognition.onerror({error:'not-allowed'});assert.match(errors[0],/permission was denied/);assert.deepEqual(state,[true,false]);
 recognition.onend();assert.equal(state.at(-1),false);
});
