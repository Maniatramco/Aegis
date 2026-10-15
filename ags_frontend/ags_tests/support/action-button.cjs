// Load the production action component in the lightweight JSX test harnesses.
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const filename=path.resolve(__dirname,'../../app/action-button.tsx');
const mod=new Module(filename,module);mod.filename=filename;mod.paths=Module._nodeModulePaths(path.dirname(filename));
mod._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,filename);
const actionButton=mod.exports;
function expandActions(node){
 if(!node||typeof node!=='object')return node;
 if(Array.isArray(node))return node.map(expandActions);
 if(node.type===actionButton.ActionButton)return expandActions(node.type(node.props));
 return node.props?{...node,props:{...node.props,children:expandActions(node.props.children)}}:node;
}
module.exports={actionButton,expandActions};
