const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const file=path.resolve(__dirname,'../../ags_frontend/app/dataset-knowledge-scope.ts'),mod=new Module(file,module);mod.filename=file;mod.paths=module.paths;
mod._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,file);
const {addDatasetKnowledge,removeDatasetKnowledge,droppedDatasetIds,DATASET_DRAG_TYPE}=mod.exports;
const datasets=[{id:'a'},{id:'b'},{id:'inactive',active:false}],documents=[{id:'one',dataset_id:'a',status:'ready'},{id:'excluded',parent_id:'a',status:'ready'},{id:'two',kb_id:'b',status:'ready'},{id:'stale',dataset_id:'b',status:'ready',requires_reindex:true},{id:'pending',dataset_id:'b',status:'queued'},{id:'private',dataset_id:'unassigned',status:'ready'},{id:'off',dataset_id:'inactive',status:'ready'}];
test('adding datasets preserves file exclusions and cannot include inaccessible, stale or inactive sources',()=>{
 const current={datasetIds:['a'],documentIds:['one']};assert.deepEqual(addDatasetKnowledge(current,['a','b','unassigned','inactive'],datasets,documents),{datasetIds:['a','b'],documentIds:['one','two']});assert.deepEqual(current,{datasetIds:['a'],documentIds:['one']});
});
test('removing the final dataset stays explicitly empty and add operations deduplicate',()=>{
 assert.deepEqual(removeDatasetKnowledge({datasetIds:['a'],documentIds:null},'a',datasets,documents),{datasetIds:[],documentIds:[]});
 assert.deepEqual(addDatasetKnowledge({datasetIds:[],documentIds:[]},['b','b'],datasets,documents),{datasetIds:['b'],documentIds:['two']});
});
test('drag payload accepts only internal dataset ids with current access',()=>{
 assert.equal(DATASET_DRAG_TYPE,'application/x-aegis-dataset-ids');for(const input of ['', 'https://external.example','{"id":"a"}','[42]'])assert.deepEqual(droppedDatasetIds(input,datasets),[]);
 assert.deepEqual(droppedDatasetIds('["a","a","unassigned","inactive"]',datasets),['a']);
});
