const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
function view({enabled=false,username='Colleague',version=0,reply}={}){
 let cursor=0,root;const state=[],calls=[],saved=[],closed=[];
 const react={useRef(){return {current:null};},useEffect(){},useState(initial){const slot=cursor++;if(!(slot in state))state[slot]=initial;return [state[slot],value=>state[slot]=typeof value==='function'?value(state[slot]):value];}};
 const filename=path.resolve(__dirname,'../../ags_frontend/app/user-feature-access.tsx'),compiled=new Module(filename,module);compiled.filename=filename;compiled.paths=module.paths;const original=compiled.require.bind(compiled);
 compiled.require=id=>id==='react'?react:id==='lucide-react'?new Proxy({},{get:()=>()=>null}):original(id);
 compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,filename);
 const props={account:{id:'target',username,features:{data_governance:enabled},feature_access_version:version},api:async(...args)=>{calls.push(args);if(reply)return reply(...args);return {user:{...props.account,features:args[2].features,feature_access_version:version+1}};},onSaved:account=>{saved.push(account);props.account=account;},onClose:()=>closed.push(true)};
 function all(node){return !node||typeof node!=='object'?[]:Array.isArray(node)?node.flatMap(all):[node,...all(node.props?.children)];}
 const render=()=>{cursor=0;root=compiled.exports.UserFeatureAccess(props);};const nodes=()=>all(root),find=(key,value)=>nodes().find(node=>node.props?.[key]===value);render();
 return {render,find,nodes,calls,saved,closed,props,toggle(value){find('role','switch').props.onChange({target:{checked:value}});render();},password(value){find('aria-label','Administrator password for feature access').props.onChange({target:{value}});render();},async submit(){await find('aria-label',`Feature access for ${username}`).props.onSubmit({preventDefault(){}});render();}};
}
test('feature form uses server permission even for a user named mani',()=>{
 const v=view({username:'mani'});assert.equal(v.find('role','switch').props.checked,false);assert.equal(v.find('type','submit').props.disabled,true);
});
test('enable requires administrator password and submits only versioned feature access',async()=>{
 const v=view();v.toggle(true);await v.submit();assert.equal(v.calls.length,0);assert.match(v.find('role','alert').props.children,/administrator password/);
 v.password('Synthetic acting password');await v.submit();
 assert.deepEqual(v.calls[0],['/users/target/features','PUT',{features:{data_governance:true},expected_version:0,current_password:'Synthetic acting password'}]);
 assert.equal(v.saved.length,1);assert.equal(v.find('aria-label','Administrator password for feature access').props.value,'');assert.equal(v.find('type','submit').props.disabled,true);
 assert.match(v.find('role','status').props.children,/enabled for Colleague/);
});
test('administrator can explicitly disable mani using the current saved version',async()=>{
 const v=view({enabled:true,username:'mani',version:7});v.toggle(false);v.password('Synthetic acting password');await v.submit();
 assert.equal(v.calls[0][2].expected_version,7);assert.equal(v.calls[0][2].features.data_governance,false);assert.match(v.find('role','status').props.children,/disabled for mani/);
});
test('failed or stale grant keeps an error without reporting success',async()=>{
 const v=view({reply:async()=>{throw Error('Feature access changed. Refresh this user.');}});v.toggle(true);v.password('Synthetic acting password');await v.submit();
 assert.equal(v.saved.length,0);assert.equal(v.find('role','status'),undefined);assert.match(v.find('role','alert').props.children,/Refresh this user/);
});
test('unchanged setting and closing the form never submit an access change',async()=>{
 const v=view();await v.submit();v.find('aria-label','Close feature access').props.onClick();assert.equal(v.calls.length,0);assert.equal(v.closed.length,1);
});
test('unavailable saved grants deny editing and cannot be replaced by a default grant',async()=>{
 const v=view({username:'mani'});v.props.account.feature_access_available=false;v.render();
 assert.equal(v.nodes().find(node=>node.type==='fieldset').props.disabled,true);
 assert.match(v.find('role','alert').props.children,/Restore its saved access snapshot/);
 v.toggle(true);v.password('Synthetic acting password');await v.submit();assert.equal(v.calls.length,0);
});
