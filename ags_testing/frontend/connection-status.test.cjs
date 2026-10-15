const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
function load(name,overrides={}){
 const filename=path.resolve(__dirname,'../../ags_frontend/app',name),compiled=new Module(filename,module);compiled.paths=module.paths;
 const original=compiled.require.bind(compiled);compiled.require=id=>Object.hasOwn(overrides,id)?overrides[id]:id.endsWith('.css')?{}:original(id);
 compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,filename);return compiled.exports;
}
test('footer reports configured OCI/local services, keeps unknown hosts explicit and strips endpoint credentials',()=>{
 const {runtimeConnections}=load('runtime-connections.ts');
 const services=runtimeConnections('http://private-user:private-password@api:8000/?token=private-token',{AEGIS_DEPLOYMENT_TARGET:'oci',AEGIS_API_LOCATION:'oci',AEGIS_WORKER_LOCATION:'oci',AEGIS_MODEL_LOCATION:'local',SECRET_KEY:'never-expose'});
 assert.equal(services.api.endpoint,'http://api:8000');assert.equal(services.web.provider,'oci');assert.equal(services.models.provider,'local');
 assert.ok(!JSON.stringify(services).includes('private-password'));assert.ok(!JSON.stringify(services).includes('private-token'));assert.ok(!JSON.stringify(services).includes('never-expose'));
 assert.equal(runtimeConnections('https://different-host.example',{}).api.provider,'unknown');
 assert.equal(runtimeConnections('http://api:8000',{AEGIS_DEPLOYMENT_TARGET:'local'}).api.provider,'local');
 let index=0;const connections={files:{provider:'oci',name:'mk-aegis',region:'ap-mumbai-1'},database:{provider:'oci',name:'agsora'},knowledge:{provider:'oci',name:'Oracle vectors'},services};
 const react={...React,useEffect(){},useState(initial){return [index++===0?connections:initial,()=>{}];}};
 const {ConnectionStatus}=load('connection-status.tsx',{react});
 const html=renderToStaticMarkup(React.createElement(ConnectionStatus,{api:async()=>assert.fail('Rendering should not probe connections'),revision:0}));
 for(const label of ['Storage: OCI','Database: OCI','Vector DB: OCI','FastAPI: OCI','WebApp: OCI','Worker: OCI','AI models: Local'])assert.ok(html.includes(label),label);
 assert.equal((html.match(/Show connection details/g)||[]).length,7);
});
