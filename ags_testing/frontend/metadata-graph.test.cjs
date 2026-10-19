const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript');
const file=path.resolve(__dirname,'../../ags_frontend/app/metadata-graph.ts'),compiled=new Module(file,module);compiled.filename=file;compiled.paths=module.paths;compiled._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,file);
const {mergeScene,neighborhood,networkLayout,lineageLayout,expansionPositions,fitGraph,relationshipBends,relationshipGeometry,SCENE_LIMIT}=compiled.exports;
const scene=(ids,edges=[])=>({nodes:ids.map(id=>({id})),edges:edges.map(([id,source,target])=>({id,source,target})),truncated:false,related_total:ids.length,totals:{nodes:500,edges:900}});
const positioned=()=>['Dataset','Document','Prompt','Model','Extraction','Review'].map((type,i)=>({id:type,type,x:100+i*100,y:100+i%2*200,r:43}));

test('expansions merge by stable identifiers, retain shared nodes and preserve complete catalog totals',()=>{
 const base=scene(['a','shared'],[['base','a','shared']]),parts={a:scene(['a','b','shared'],[['ab','a','b']]),b:scene(['b','c'],[['bc','b','c']]),shared:scene(['shared','c'],[['sc','shared','c']])};
 const merged=mergeScene(base,parts);assert.deepEqual(merged.nodes.map(n=>n.id),['a','shared','b','c']);assert.deepEqual(merged.totals,base.totals);assert.equal(merged.edges.length,4);
 delete parts.a;const collapsed=mergeScene(base,parts);assert.deepEqual(collapsed.nodes.map(n=>n.id),['a','shared','c']);assert.ok(!collapsed.edges.some(e=>e.id==='bc'));
});
test('unreachable expansions never resurrect a collapsed branch; scene limits are explicit',()=>{
 const base=scene(['a']);assert.deepEqual(mergeScene(base,{orphan:scene(['orphan','private'])}).nodes,[{id:'a'}]);
 const merged=mergeScene(base,{a:scene(['a',...Array.from({length:200},(_,i)=>'n'+i)])});assert.equal(merged.nodes.length,SCENE_LIMIT);assert.equal(merged.truncated,true);assert.equal(merged.related_total,201);assert.deepEqual(merged.totals,base.totals);
});
test('neighborhood selection highlights only the displayed adjacent records or selected edge',()=>{
 const base=scene(['a','b','c','d'],[['ab','a','b'],['bc','b','c']]);
 const focus=neighborhood(base.nodes,base.edges,{kind:'node',id:'a'});assert.deepEqual([...focus.nodes],['a','b']);assert.deepEqual([...focus.edges],['ab']);
 const edge=neighborhood(base.nodes,base.edges,{kind:'edge',id:'bc'});assert.deepEqual([...edge.nodes],['b','c']);assert.equal(neighborhood(base.nodes,base.edges,null).nodes.size,0);
});
test('network arrangement is deterministic, does not mutate catalog records and respects pins',()=>{
 const nodes=positioned(),edges=[{id:'one',source:'Dataset',target:'Document'},{id:'two',source:'Document',target:'Extraction'}],original=JSON.stringify({nodes,edges});
 const first=networkLayout(nodes,edges,1000,690,new Set(['Dataset'])),second=networkLayout(nodes,edges,1000,690,new Set(['Dataset']));assert.deepEqual(first,second);assert.deepEqual(first.Dataset,{x:100,y:100});assert.equal(JSON.stringify({nodes,edges}),original);
 for(const point of Object.values(first))assert.ok(Number.isFinite(point.x)&&Number.isFinite(point.y));assert.notDeepEqual(first.Document,{x:200,y:300});
});
test('lineage columns and fit preserve pinned positions and bring freely arranged records into view',()=>{
 const nodes=positioned(),points=lineageLayout(nodes,1000,new Set(['Dataset']));assert.deepEqual(points.Dataset,{x:100,y:100});assert.ok(points.Extraction.x>points.Document.x);assert.ok(points.Review.x>points.Extraction.x);
 const arranged=nodes.map(n=>({...n,...points[n.id]})),camera=fitGraph(arranged,540,805);for(const n of arranged){assert.ok((n.x-n.r)*camera.zoom+camera.x>=0);assert.ok((n.x+n.r)*camera.zoom+camera.x<=540);assert.ok((n.y+n.r)*camera.zoom+camera.y<=805);}assert.deepEqual(fitGraph([],1000,690),{zoom:1,x:0,y:0});
});
test('expansion placement keeps existing coordinates and avoids the occupied source and siblings',()=>{
 const existing=positioned(),incoming=[...existing,{id:'new',type:'Document',x:0,y:0,r:43},{id:'another',type:'Review',x:0,y:0,r:43}],positions=expansionPositions(existing,incoming,'Document');
 for(const node of existing)assert.deepEqual(positions[node.id],{x:node.x,y:node.y});for(const id of ['new','another'])for(const node of existing)assert.ok(Math.hypot(positions[id].x-node.x,positions[id].y-node.y)>node.r+43+17);
});
test('parallel and mobile relationship paths have independent labels that follow both endpoints',()=>{
 const [a,b]=positioned(),first=relationshipGeometry(a,b,-24),second=relationshipGeometry(a,b,24);assert.notEqual(first.path,second.path);assert.notEqual(first.y,second.y);
 const mobile=relationshipGeometry(a,b,0,true),moved=relationshipGeometry({...a,x:a.x+30},{...b,x:b.x+30},0,true);assert.equal(moved.x,mobile.x+30);assert.ok(!relationshipGeometry(a,{...b,x:a.x,y:a.y}).path.includes('NaN'));
});


test('parallel bend grouping is stable across edge order and separates reversed directions',()=>{
 const edges=[{id:'two',source:'b',target:'a'},{id:'one',source:'a',target:'b'},{id:'single',source:'c',target:'d'}],first=relationshipBends(edges),second=relationshipBends([...edges].reverse());for(const edge of edges)assert.equal(first.get(edge.id),second.get(edge.id));assert.equal(first.get('single'),0);const a={id:'a',type:'Document',x:0,y:0,r:43},b={id:'b',type:'Extraction',x:200,y:0,r:43};assert.notEqual(relationshipGeometry(a,b,first.get('one')).y,relationshipGeometry(b,a,first.get('two')).y);
});
