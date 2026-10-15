const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
function view(isAdmin=true,reply=async()=>({user:{is_admin:true},sessions_revoked:true}),self=false){
 let index=0,root;const hooks=[],calls=[],notices=[];
 const react={useState(initial){const slot=index++;if(!(slot in hooks))hooks[slot]=initial;return [hooks[slot],value=>hooks[slot]=typeof value==='function'?value(hooks[slot]):value];},useRef(initial){const slot=index++;if(!(slot in hooks))hooks[slot]={current:initial};return hooks[slot];},useEffect(){}};
 const filename=path.resolve(__dirname,'../app/user-management.tsx'),compiled=new Module(filename,module);compiled.filename=filename;compiled.paths=module.paths;const original=compiled.require.bind(compiled);
 compiled.require=id=>id==='react'?react:id==='./action-button'?{ActionButton:'button'}:id==='./user-management.css'?{}:id==='lucide-react'||id==='./dataset-assignments'?new Proxy({},{get:()=>()=>null}):original(id);
 compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,filename);
 const account={id:self?'acting':'target',username:self?'Acting':'Target',role:'user',is_admin:false,created_at:1,updated_at:1};hooks[0]=[account];
 const props={user:{id:'acting',username:'Acting',is_admin:isAdmin},api:async(...args)=>{calls.push(args);return args[0]==='/users'?[account]:reply(...args);},onRoleChanged:()=>notices.push('role'),onPasswordChanged:()=>notices.push('password')};
 function elements(node){if(!node||typeof node!=='object')return [];if(Array.isArray(node))return node.flatMap(elements);return [node,...elements(node.props?.children)];}
 const render=()=>{index=0;root=compiled.exports.UserManagement(props);return root;};const find=(key,value)=>elements(root).find(n=>n.props?.[key]===value);render();return {render,find,calls,notices};
}
test('ordinary user cannot see role actions even when their account ID is acting',()=>{const v=view(false);assert.equal(v.find('aria-label','Change role for Target'),undefined);assert.equal(v.find('className','card account-directory'),undefined);});
test('role form submits selected persisted role with acting password without new-password fields',async()=>{const v=view();v.find('aria-label','Change role for Target').props.onClick();v.render();assert.equal(v.find('id','account-new-password'),undefined);assert.equal(v.find('id','account-role').props.value,'administrator');v.find('id','account-role').props.onChange({target:{value:'user'}});v.render();v.find('id','account-current-password').props.onChange({target:{value:'Synthetic acting password'}});v.render();await v.find('aria-label','Change user role').props.onSubmit({preventDefault(){}});assert.deepEqual(v.calls[0],['/users/target/role','PATCH',{role:'user',current_password:'Synthetic acting password'}]);v.render();assert.equal(v.find('id','account-current-password'),undefined);assert.deepEqual(v.notices,[]);});
test('self role change uses role sign-out callback and clears its form',async()=>{const v=view(true,undefined,true);v.find('aria-label','Change role for Acting').props.onClick();v.render();v.find('id','account-current-password').props.onChange({target:{value:'Synthetic acting password'}});v.render();await v.find('aria-label','Change user role').props.onSubmit({preventDefault(){}});v.render();assert.deepEqual(v.notices,['role']);assert.equal(v.find('id','account-current-password'),undefined);});
test('last-administrator error remains visible with no false success or sign-out',async()=>{const v=view(true,async()=>{throw Error('Keep at least one administrator.');});v.find('aria-label','Change role for Target').props.onClick();v.render();v.find('id','account-current-password').props.onChange({target:{value:'Synthetic acting password'}});v.render();await v.find('aria-label','Change user role').props.onSubmit({preventDefault(){}});v.render();assert.equal(v.find('role','alert').props.children,'Keep at least one administrator.');assert.deepEqual(v.notices,[]);assert.ok(v.find('aria-label','Change user role'));});

test('delete requires exact username and administrator password and submits only deletion fields',async()=>{
 const v=view();v.find('label','Delete user Target').props.onClick();v.render();
 assert.equal(v.find('id','account-new-password'),undefined);
 v.find('id','account-current-password').props.onChange({target:{value:'Synthetic acting password'}});v.render();
 await v.find('aria-label','Delete user').props.onSubmit({preventDefault(){}});v.render();
 assert.equal(v.calls.length,0);assert.match(v.find('role','alert').props.children,/exact username/);
 v.find('id','account-delete-username').props.onChange({target:{value:'Target'}});v.render();
 await v.find('aria-label','Delete user').props.onSubmit({preventDefault(){}});v.render();
 assert.deepEqual(v.calls[0],['/users/target','DELETE',{username:'Target',current_password:'Synthetic acting password'}]);
 assert.equal(v.find('id','account-current-password'),undefined);assert.match(v.find('role','status').props.children,/dataset access were removed/);
});
test('delete is hidden from ordinary users, disabled for self, and cancel makes no request',()=>{
 assert.equal(view(false).find('label','Delete user Target'),undefined);
 assert.equal(view(true,undefined,true).find('label','Delete user Acting').props.disabled,true);
 const v=view();v.find('label','Delete user Target').props.onClick();v.render();
 v.find('type','button').props.onClick();v.render();
 assert.equal(v.find('aria-label','Delete user'),undefined);assert.equal(v.calls.length,0);
});
test('failed delete keeps its form and error without a success notice',async()=>{
 const v=view(true,async()=>{throw Error('Ownership must be transferred.');});
 v.find('label','Delete user Target').props.onClick();v.render();
 v.find('id','account-current-password').props.onChange({target:{value:'Synthetic acting password'}});v.render();
 v.find('id','account-delete-username').props.onChange({target:{value:'Target'}});v.render();
 await v.find('aria-label','Delete user').props.onSubmit({preventDefault(){}});v.render();
 assert.ok(v.find('aria-label','Delete user'));assert.equal(v.find('role','status'),undefined);
 assert.equal(v.find('role','alert').props.children,'Ownership must be transferred.');
});
