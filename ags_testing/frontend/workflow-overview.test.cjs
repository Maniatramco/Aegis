const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
function mount(isAdmin=false){
 let cursor=0,root;const hooks=[],calls=[];
 const react={useState(initial){const slot=cursor++;if(!(slot in hooks))hooks[slot]=initial;return [hooks[slot],value=>hooks[slot]=typeof value==='function'?value(hooks[slot]):value];},useRef(value){const slot=cursor++;if(!(slot in hooks))hooks[slot]={current:value};return hooks[slot];},useId(){return 'overview-'+cursor++;},useEffect(){}};
 const filename=path.resolve(__dirname,'../../ags_frontend/app/workflow-overview.tsx'),compiled=new Module(filename,module);compiled.filename=filename;compiled.paths=module.paths;const original=compiled.require.bind(compiled);
 compiled.require=id=>id==='react'?react:id.endsWith('.css')?{}:id==='lucide-react'||id==='./agent-logo'?new Proxy({},{get:()=>()=>null}):original(id);
 compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,filename);
 function elements(node){if(!node||typeof node!=='object')return [];if(Array.isArray(node))return node.flatMap(elements);if(typeof node.type==='function')return elements(node.type(node.props));return [node,...elements(node.props?.children)];}
 const render=()=>{cursor=0;root=compiled.exports.WorkflowOverview({isAdmin,onNavigate:value=>calls.push(value)});return root;};
 const all=()=>elements(root),text=node=>!node?'':typeof node==='string'?node:Array.isArray(node)?node.map(text).join(''):text(node.props?.children);
 render();return {render,all,calls,text};
}
test('Home workflow exposes tools without administrator controls or automatic actions',()=>{
 const v=mount();assert.equal(v.all().filter(node=>node.props?.className==='aegis-flow-phase').length,4);assert.equal(v.all().filter(node=>node.props?.className==='aegis-flow-node').length,12);
 const cards=v.all().filter(node=>node.props?.className==='aegis-flow-feature-link');assert.equal(cards.length,6);
 assert.equal(v.all().some(node=>node.type==='details'),false);assert.deepEqual(v.calls,[]);
 cards.find(node=>v.text(node).includes('Aegis Agent')).props.onClick();assert.deepEqual(v.calls,['Aegis agent V2']);
});
test('stage exploration changes its explanation and navigates only after an explicit action',()=>{
 const v=mount();v.all().filter(node=>node.props?.className==='aegis-flow-phase')[3].props.onClick();v.render();
 const detail=v.all().find(node=>node.props?.['aria-label']==='Ask grounded questions details');assert.ok(detail);
 assert.match(v.text(detail),/hybrid retrieval.*CPU rerank.*generation.*validation/);assert.equal(v.all().filter(node=>node.props?.className==='aegis-flow-node').length,12);assert.deepEqual(v.calls,[]);
 v.all().find(node=>node.props?.className==='btn aegis-guide-action').props.onClick();assert.deepEqual(v.calls,['Aegis agent V2']);
});
test('administrator tools are role gated and stage details can be expanded and collapsed',()=>{
 const v=mount(true);assert.equal(v.all().filter(node=>node.props?.className==='aegis-flow-feature-link').length,10);
 const model=v.all().find(node=>node.props?.className==='aegis-flow-feature-link'&&v.text(node).startsWith('Model registration'));model.props.onClick();assert.deepEqual(v.calls,['Model Registration']);
 v.all().find(node=>node.props?.className==='btn aegis-feature-toggle').props.onClick();v.render();
 const toggle=v.all().find(node=>node.props?.className==='btn aegis-feature-toggle');assert.equal(toggle.props['aria-expanded'],true);
 const target=v.all().find(node=>node.props?.id===toggle.props['aria-controls']);assert.equal(target.props.hidden,false);
 toggle.props.onClick();v.render();assert.equal(v.all().find(node=>node.props?.className==='btn aegis-feature-toggle').props['aria-expanded'],false);
});
