const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript'),React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const file=path.resolve(__dirname,'../../ags_frontend/app/about-aegis.tsx'),mod=new Module(file,module);mod.filename=file;mod.paths=module.paths;const original=mod.require.bind(mod);mod.require=id=>id.endsWith('.css')?{}:original(id);
mod._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{esModuleInterop:true,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,file);
const release=require('../../ags_frontend/app/application-version.json');
test('About presents the current version and complete prior feature history from the shared version source',()=>{
 const html=renderToStaticMarkup(React.createElement(mod.exports.AboutAegis));assert.match(release.version,/^\d+\.\d+\.\d+\.\d+$/);assert.ok(release.releases.some(item=>item.version==='26.1.1.0'));assert.equal(release.releases[0].version,release.version);
 const escaped=text=>renderToStaticMarkup(React.createElement(React.Fragment,null,text));
 for(const entry of release.releases){assert.ok(html.includes('v'+entry.version));for(const change of entry.changes)assert.ok(html.includes(escaped(change)),change);}
 const changelog=fs.readFileSync(path.resolve(__dirname,'../../CHANGELOG.md'),'utf8');for(const entry of release.releases)assert.ok(changelog.includes(entry.version));assert.match(html,/Current version/);
});
test('About explains the workflow as a diagram with intake, both lanes and mapped models',()=>{
 const html=renderToStaticMarkup(React.createElement(mod.exports.AboutAegis));
 for(const text of ['Sources','Dataset','Unified knowledge','Ask with evidence','Extract and review','Hybrid search','Rerank evidence','Validate citations','Review and correct','Models mapped per dataset'])assert.ok(html.includes(text),text);
 assert.ok(html.indexOf('Hybrid search')<html.indexOf('Rerank evidence')&&html.indexOf('Rerank evidence')<html.indexOf('Generate answer')&&html.indexOf('Generate answer')<html.indexOf('Validate citations'));
 assert.match(html,/<figure class="about-diagram" aria-labelledby="about-flow-title">/);
});
