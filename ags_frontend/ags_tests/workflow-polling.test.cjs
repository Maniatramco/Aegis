const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const file=path.resolve(__dirname,'../app/workflow-polling.ts'),compiled=new Module(file,module);
compiled._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2017}}).outputText,file);
const {pendingJobIds,mergeJobUpdates}=compiled.exports;

test('idle and completed history produce no job polling references',()=>{
 assert.equal(pendingJobIds([]),'');
 assert.equal(pendingJobIds(['completed','failed','cancelled'].map((status,i)=>({id:String(i),status}))), '');
});
test('poll only active references, then stop once their terminal updates arrive',()=>{
 const jobs=[{id:'old',status:'completed'},{id:'a',status:'queued'},{id:'b',status:'running'}];
 assert.equal(pendingJobIds(jobs),'a,b');
 const updated=mergeJobUpdates(jobs,[{id:'a',status:'completed'},{id:'b',status:'failed'}]);
 assert.equal(pendingJobIds(updated),'');assert.equal(updated.length,3);
});
test('an in-flight poll cannot drop new uploads or unrelated history',()=>{
 const updated=mergeJobUpdates([{id:'a',status:'running'},{id:'new',status:'queued'},{id:'old',status:'completed'}],[{id:'a',status:'completed'}]);
 assert.equal(pendingJobIds(updated),'new');assert.equal(updated.length,3);
 assert.equal(pendingJobIds(Array.from({length:130},(_,i)=>({id:String(i),status:'held'}))).split(',').length,120);
});
