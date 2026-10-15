const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const filename=path.resolve(__dirname,'../app/extraction-name.ts'),compiled=new Module(filename,module);compiled.paths=module.paths;
compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,filename);
const {suggestedExtractionName,withExtractionName}=compiled.exports;
test('names end with sortable local date/time, strip document extensions and fit the API limit',()=>{
 const when=new Date('2026-10-15T16:00:04Z');
 assert.equal(suggestedExtractionName(['Aegis_Sample_Credit_Term_Sheet.pdf'],when,'Asia/Kolkata'),'Aegis_Sample_Credit_Term_Sheet_2026-10-15_21-30-04');
 assert.equal(suggestedExtractionName(['old_2026-10-14_00-00-01'],when,'UTC'),'old_2026-10-15_16-00-04');
 assert.equal(suggestedExtractionName(['x'.repeat(240)],when,'UTC').length,200);
 assert.match(suggestedExtractionName(['one.txt','two.txt'],when,'UTC'),/^Merged extraction - 2 documents_2026-10-15_16-00-04$/);
});
test('proposal timestamps stay stable, existing documents supply names, custom names and chat are retained',()=>{
 const plan={created_at:1792080004,calls:[{tool:'extract'}],document_ids:['doc']};
 const first=withExtractionName(plan,[{id:'doc',name:'invoice.pdf'}]);
 assert.match(first.display_name,/^invoice_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$/);
 assert.equal(first.display_name,withExtractionName(plan,[{id:'doc',name:'invoice.pdf'}]).display_name);
 assert.equal(withExtractionName({...plan,display_name:'My custom name'},[]).display_name,'My custom name');
 assert.equal(withExtractionName({calls:[]},[]).display_name,undefined);
 assert.match(withExtractionName({...plan,attached_filenames:['attached.txt']},[]).display_name,/^attached_/);
});
