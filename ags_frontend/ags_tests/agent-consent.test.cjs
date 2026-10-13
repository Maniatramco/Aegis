const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const file=path.resolve(__dirname,'../app/agent-consent.tsx'),compiled=new Module(file,module);compiled.paths=module.paths;const original=compiled.require.bind(compiled);compiled.require=id=>id.endsWith('.css')?{}:original(id);
compiled._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,file);
const {consentCovers,ConsentPopup}=compiled.exports;
const receipt={dataset_id:'resume',required:true,destinations:[{key:'storage-v1',title:'OCI Object Storage',description:'Upload originals to OCI.'},{key:'vectors-v1',title:'OCI knowledge store',description:'Publish vectors.'}]};
test('approval carries only within the same request dataset and unchanged destinations',()=>{
 assert.equal(consentCovers(undefined,receipt),false);
 assert.equal(consentCovers(receipt,{...receipt,destinations:[receipt.destinations[0]]}),true);
 assert.equal(consentCovers(receipt,{...receipt,dataset_id:'other'}),false);
 assert.equal(consentCovers(receipt,{...receipt,destinations:[{...receipt.destinations[0],key:'storage-v2'}]}),false);
});
test('small approval dialog identifies destinations and explicit cancel/agree actions',()=>{
 const html=renderToStaticMarkup(React.createElement(ConsentPopup,{scope:receipt,onResolve(){}}));
 for(const value of ['<dialog','Allow external processing?','OCI Object Storage','OCI knowledge store','Cancel','Agree and continue','aria-describedby','Close external processing approval'])assert.ok(html.includes(value),value);
 assert.ok(!html.includes('type="checkbox"'));
});
