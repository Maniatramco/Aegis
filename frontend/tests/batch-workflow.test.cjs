const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
const source = path.resolve(__dirname, '../app/batch-workflow.ts');
const compiled = new Module(source,module);
compiled._compile(ts.transpileModule(fs.readFileSync(source,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,source);
const { summarizeUploadBatch, currentUploadStep, uploadStageStatus, readableUploadError } = compiled.exports;
const ready = {id:'ready',name:'ready.txt',status:'submitted',document:{status:'ready'},ready:true};
const indexing = {id:'indexing',name:'indexing.txt',status:'submitted',document:{status:'processing'},processing:true,job:{status:'running',workflow:{current:'index',stages:{extract:{status:'completed'},index:{status:'running'}}}}};

test('ten mixed documents share counts without implying all are ready',()=>{
 const items=[...Array.from({length:8},(_,i)=>({...ready,id:String(i)})),indexing,{id:'selected',name:'selected.txt',status:'selected'}];
 const batch=summarizeUploadBatch(items);
 assert.equal(batch.total,10);assert.equal(batch.ready,8);assert.equal(batch.active,1);assert.equal(batch.progress,85);
 assert.equal(batch.stages.find(s=>s.stage==='index').running,1);
 assert.equal(batch.stages.find(s=>s.stage==='ready').completed,8);
 assert.equal(currentUploadStep(indexing),'Building index');
});
test('a failed index retains completed reading and never reports full completion',()=>{
 const failed={...indexing,processing:false,failed:true,document:{status:'failed'},job:{...indexing.job,status:'failed',workflow:{current:'index',stages:{extract:{status:'completed'},index:{status:'failed'}}}}};
 const batch=summarizeUploadBatch([ready,failed]);
 assert.equal(batch.attention,1);assert.equal(batch.progress,75);assert.equal(batch.stages[2].failed,1);
 assert.equal(currentUploadStep(failed),'Building index failed');
});
test('unconfirmed uploads remain unknown and cannot count as stored',()=>{
 const item={id:'uncertain',name:'uncertain.txt',status:'uncertain'};
 assert.equal(summarizeUploadBatch([item]).progress,0);
 assert.equal(summarizeUploadBatch([item]).attention,1);
 assert.equal(uploadStageStatus(item,'upload'),'unknown');
 assert.equal(currentUploadStep(item),'Upload not confirmed');
});
test('a ready document overrides an older failed job from a crossed poll',()=>{
 const item={...ready,job:{status:'failed',workflow:{current:'index',stages:{index:{status:'failed'}}}}};
 assert.equal(summarizeUploadBatch([item]).progress,100);
 assert.equal(currentUploadStep(item),'Ready for questions');
});
test('a queued index requiring a rebuild is processing, not a failure needing attention',()=>{
 const queued={...indexing,document:{status:'queued',requires_reindex:true},job:{status:'queued'}};
 assert.equal(summarizeUploadBatch([queued]).attention,0);
 assert.equal(summarizeUploadBatch([queued]).active,1);
 assert.equal(currentUploadStep(queued),'Queued for processing');
 const idle={...queued,processing:false};
 assert.equal(summarizeUploadBatch([idle]).attention,1);
 assert.equal(currentUploadStep(idle),'Reindex required');
});
test('a queued retry never borrows completion or failure from the previous job',()=>{
 for(const status of ['completed','failed','cancelled']){
  const item={...indexing,document:{status:'queued'},job:{status,workflow:{current:'index',stages:{extract:{status:'completed'},index:{status:status==='completed'?'completed':'failed'}}}}};
  assert.equal(summarizeUploadBatch([item]).progress,25);
  assert.equal(currentUploadStep(item),'Queued for processing');
 }
});
test('older jobs without stage details show unavailable status instead of invented progress',()=>{
 const item={id:'old',name:'old.txt',status:'submitted',document:{status:'processing'},processing:true,job:{status:'running'}};
 assert.equal(summarizeUploadBatch([item]).progress,25);
 assert.equal(uploadStageStatus(item,'extract'),'unknown');
});
test('encoding failures explain how to fix the file, while provider errors retain their useful reason',()=>{
 assert.match(readableUploadError("'utf-8' codec can't decode byte 0xff in position 0: invalid start byte"),/Save a copy as UTF-8/);
 assert.equal(readableUploadError('Embedding provider timed out after 120 seconds'),'Embedding provider timed out after 120 seconds');
});
