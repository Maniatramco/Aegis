const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const controls={masking_enabled:false,sensitive_fields:[],freshness_days:30,require_review:true,rules:[],auto_quality:true,quality_interval_minutes:60,auto_sync:false,sync_interval_minutes:1440,retention_action:'none',retention_days:null,purge_grace_days:30};
function view({manage=true,tab='controls',pending=null,approve=false,reply=async()=>({})}={}){
 let cursor=0,root;const hooks=[],calls=[];
 const react={useState(initial){const i=cursor++;if(!(i in hooks))hooks[i]=typeof initial==='function'?initial():initial;return[hooks[i],value=>hooks[i]=typeof value==='function'?value(hooks[i]):value];},useEffect(){}};
 const filename=path.resolve(__dirname,'../../ags_frontend/app/governance-operations.tsx'),compiled=new Module(filename,module);compiled.filename=filename;compiled.paths=module.paths;const original=compiled.require.bind(compiled);
 compiled.require=id=>id==='react'?react:id==='lucide-react'?new Proxy({},{get:()=>()=>null}):original(id);
 compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,filename);
 hooks[0]=tab;hooks[1]={active:{version:0,controls:{...controls}},hold:{active:false,version:0},pending,can_manage:manage,can_approve:approve};hooks[2]={...controls};hooks[10]=false;
 const props={datasetId:'synthetic-finance',canManage:manage,api:async(...args)=>{calls.push(args);return reply(...args);}};
 const elements=node=>!node||typeof node!=='object'?[]:Array.isArray(node)?node.flatMap(elements):[node,...elements(node.props?.children)];
 const text=node=>typeof node==='string'?node:Array.isArray(node)?node.map(text).join(''):text(node?.props?.children||'');
 const render=()=>{cursor=0;root=compiled.exports.GovernanceOperations(props);return root;};
 const find=(key,value)=>elements(root).find(n=>n.props?.[key]===value);
 const button=label=>elements(root).find(n=>n.type==='button'&&text(n)===label);
 render();return{render,find,button,calls,hooks,elements:()=>elements(root),text:()=>text(root)};
}
const settle=()=>new Promise(resolve=>setImmediate(resolve));

test('ordinary readers see active controls with disabled editing and no audit or automation actions',()=>{
 const v=view({manage:false});assert.equal(v.find('role','tabpanel').props.id,'gov-ops-synthetic-finance-panel-controls');
 assert.equal(v.elements().find(n=>n.type==='fieldset').props.disabled,true);
 assert.equal(v.button('Submit for independent approval'),undefined);assert.equal(v.button('Access audit'),undefined);assert.equal(v.button('Automation'),undefined);
 assert.deepEqual(v.calls,[]);
});

test('a control proposal sends its expected version and does not apply policy or run tasks',async()=>{
 const v=view({reply:async()=>({active:{version:0,controls},hold:{active:false,version:0},pending:{status:'pending',proposed_by_name:'Proposer',controls,reason:'Reviewed scope'}})});
 v.find('aria-label','Mask sensitive results for ordinary users').props.onChange({target:{checked:true}});v.render();
 v.find('aria-label','Additional sensitive fields').props.onChange({target:{value:'secret_code, '}});v.render();
 v.find('aria-label','Operational policy proposal reason').props.onChange({target:{value:'Protect personal fields'}});v.render();
 v.elements().find(n=>n.type==='form').props.onSubmit({preventDefault(){}});await settle();v.render();
 assert.equal(v.calls.length,1);assert.equal(v.calls[0][0],'/governance/datasets/synthetic-finance/controls/proposals');
 assert.equal(v.calls[0][2].expected_version,0);assert.equal(v.calls[0][2].controls.masking_enabled,true);
 assert.deepEqual(v.calls[0][2].controls.sensitive_fields,['secret_code']);assert.match(v.text(),/different administrator must approve/);
});

test('a proposer cannot see an approval action and cannot overwrite the pending proposal',()=>{
 const v=view({pending:{id:'pending-id',status:'pending',controls,reason:'Proposal',proposed_by_name:'Proposer',proposed_at:1}});
 assert.equal(v.button('Approve operational policy'),undefined);assert.ok(v.button('Reject proposal'));
 assert.equal(v.elements().find(n=>n.type==='fieldset').props.disabled,true);
});

test('an independent approval submits the current proposal id and a decision reason',async()=>{
 const v=view({approve:true,pending:{id:'pending-id',status:'pending',controls,reason:'Proposal',proposed_by_name:'Other administrator',proposed_at:1},
  reply:async()=>({active:{version:1,controls,approved_by_name:'Approver'},hold:{active:false,version:0},pending:null})});
 v.find('aria-label','Operational policy decision reason').props.onChange({target:{value:'Scope and retention checked'}});v.render();
 v.button('Approve operational policy').props.onClick();await settle();v.render();
 assert.deepEqual(v.calls[0],['/governance/datasets/synthetic-finance/controls/decision','POST',{proposal_id:'pending-id',approve:true,reason:'Scope and retention checked'}]);
 assert.match(v.text(),/approved and active/);
});

test('a failed scan reports the failure without displaying a successful completion',async()=>{
 const v=view({tab:'quality',reply:async()=>{throw Error('Saved output could not be checked.');}});
 v.button('Run quality & discovery scan').props.onClick();await settle();v.render();
 assert.equal(v.find('role','alert').props.children,'Saved output could not be checked.');assert.doesNotMatch(v.text(),/scan completed/);
});

test('holding a dataset sends a versioned preservation decision without invoking retention',async()=>{
 const v=view({tab:'retention',reply:async()=>({active:{version:0,controls},hold:{active:true,version:1,reason:'Preserve investigation'},can_release_hold:false})});
 v.find('aria-label','Legal hold reason').props.onChange({target:{value:'Preserve investigation'}});v.render();
 v.button('Place legal hold').props.onClick();await settle();v.render();
 assert.deepEqual(v.calls[0],['/governance/datasets/synthetic-finance/hold','PUT',{active:true,expected_version:0,reason:'Preserve investigation'}]);
 assert.equal(v.calls.length,1);assert.equal(v.button('Release legal hold').props.disabled,true);
});
