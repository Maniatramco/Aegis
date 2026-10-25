const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const ts=require('typescript');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');

test('sign-in task precedes supporting artwork and exposes the product identity as live text',()=>{
 const filename=path.resolve(__dirname,'../../ags_frontend/app/sign-in-layout.tsx');
 const mod=new Module(filename,module);mod.filename=filename;mod.paths=module.paths;
 const base=mod.require.bind(mod);
 mod.require=id=>id==='next/image'?({priority,...props})=>React.createElement('img',props):base(id);
 mod._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,filename);
 const html=renderToStaticMarkup(React.createElement(mod.exports.SignInLayout,null,
  React.createElement('h1',{id:'login-heading'},'Welcome back'),
  React.createElement('form',null,React.createElement('label',{htmlFor:'username'},'Username'),React.createElement('input',{id:'username',autoComplete:'username'}))));
 assert.ok(html.indexOf('id="login-heading"')<html.indexOf('aria-label="Aegis platform artwork"'));
 assert.match(html,/<p class="login-brand-name">Aegis<\/p>/);
 assert.match(html,/<p class="login-brand-tagline">Secure Data Lakehouse and AI Platform<\/p>/);
 assert.match(html,/aria-labelledby="login-heading"/);
 assert.match(html,/alt="Aegis shield and network artwork"/);
 assert.match(html,/autoComplete="username"/i);
});
