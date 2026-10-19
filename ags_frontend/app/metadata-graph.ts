import {forceCollide,forceLink,forceManyBody,forceSimulation,forceX,forceY,type SimulationNodeDatum} from 'd3-force';

export type Point={x:number;y:number};
export type PositionedNode=Point&{id:string;type:string;r:number};
type Link={id:string;source:string;target:string};
type Scene={nodes:{id:string}[];edges:Link[];truncated:boolean;related_total:number};
export const SCENE_LIMIT=120;

/** Merge only expansions whose source is still reachable from the original scene. */
export function mergeScene<T extends Scene>(base:T,expansions:Record<string,T>):T{
 const nodes=new Map(base.nodes.map(node=>[node.id,node])),edges=new Map(base.edges.map(edge=>[edge.id,edge]));
 const pending=new Map(Object.entries(expansions));let truncated=base.truncated,progress=true;
 while(progress){progress=false;for(const [source,part] of pending){if(!nodes.has(source))continue;pending.delete(source);progress=true;truncated||=part.truncated;for(const node of part.nodes)nodes.set(node.id,node);for(const edge of part.edges)edges.set(edge.id,edge);}}
 const displayed=[...nodes.values()].slice(0,SCENE_LIMIT),ids=new Set(displayed.map(node=>node.id));
 return{...base,nodes:displayed,edges:[...edges.values()].filter(edge=>ids.has(edge.source)&&ids.has(edge.target)),truncated:truncated||nodes.size>displayed.length,related_total:Math.max(base.related_total,nodes.size)} as T;
}

export function neighborhood(nodes:{id:string}[],edges:Link[],selected:{kind:'node'|'edge';id:string}|null){
 const nodeIds=new Set<string>(),edgeIds=new Set<string>();if(!selected)return{nodes:nodeIds,edges:edgeIds};
 if(selected.kind==='edge'){const edge=edges.find(e=>e.id===selected.id);if(edge){nodeIds.add(edge.source);nodeIds.add(edge.target);edgeIds.add(edge.id);}}
 else if(nodes.some(node=>node.id===selected.id)){nodeIds.add(selected.id);for(const edge of edges)if(edge.source===selected.id||edge.target===selected.id){nodeIds.add(edge.source);nodeIds.add(edge.target);edgeIds.add(edge.id);}}
 return{nodes:nodeIds,edges:edgeIds};
}

export function networkLayout(nodes:PositionedNode[],edges:Link[],width:number,height:number,pinned=new Set<string>()):Record<string,Point>{
 if(!nodes.length)return{};
 type Particle=PositionedNode&SimulationNodeDatum;
 const particles:Particle[]=nodes.map(node=>({...node,...(pinned.has(node.id)?{fx:node.x,fy:node.y}:{})}));
 const ids=new Set(nodes.map(node=>node.id)),links=edges.filter(e=>ids.has(e.source)&&ids.has(e.target)).map(e=>({...e}));
 // A stopped, deterministic simulation avoids continual animation and keeps manual drags stable.
 const compact=width<700;
 const simulation=forceSimulation(particles).stop().force('links',forceLink<Particle,Link>(links).id(n=>n.id).distance(compact?135:170).strength(.22)).force('charge',forceManyBody().strength(compact?-280:-600)).force('collision',forceCollide<Particle>(n=>n.r+(compact?12:20)).iterations(3)).force('x',forceX(width/2).strength(compact?.12:.035)).force('y',forceY(height/2).strength(compact?.06:.05));
 simulation.tick(240);simulation.stop();
 return Object.fromEntries(particles.map(node=>[node.id,{x:node.x,y:node.y}]));
}

export function lineageLayout(nodes:PositionedNode[],width:number,pinned=new Set<string>()):Record<string,Point>{
 const columns=['Dataset','Document','Prompt','Model','Extraction','Review'],groups=columns.map(kind=>nodes.filter(n=>n.type===kind));
 return Object.fromEntries(groups.flatMap((group,column)=>group.map((node,row)=>[node.id,pinned.has(node.id)?{x:node.x,y:node.y}:{x:100+column*Math.max(170,(width-200)/5),y:110+row*140}])));
}

export function fitGraph(nodes:(Point&{r:number})[],width:number,height:number){
 if(!nodes.length)return{zoom:1,x:0,y:0};
 const left=Math.min(...nodes.map(n=>n.x-n.r-20)),right=Math.max(...nodes.map(n=>n.x+n.r+20)),top=Math.min(...nodes.map(n=>n.y-n.r-20)),bottom=Math.max(...nodes.map(n=>n.y+n.r+20));
 const zoom=Math.min(1,(width-80)/(right-left),(height-100)/(bottom-top));
 return{zoom,x:width/2-(left+right)/2*zoom,y:height/2-(top+bottom)/2*zoom};
}

export function relationshipGeometry(a:PositionedNode,b:PositionedNode,bend=0,mobileLoop=false){
 const dx=b.x-a.x,dy=b.y-a.y,length=Math.hypot(dx,dy)||1,x1=a.x+dx/length*(a.r+4),y1=a.y+dy/length*(a.r+4),x2=b.x-dx/length*(b.r+9),y2=b.y-dy/length*(b.r+9);
 if(mobileLoop){const side=Math.min(a.x-a.r,b.x-b.r)-55;return{path:`M${a.x-a.r-3} ${a.y}C${side} ${a.y},${side} ${b.y},${b.x-b.r-8} ${b.y}`,x:(a.x-a.r-3+b.x-b.r-8)/8+side*.75+35,y:(a.y+b.y)/2};}
 const cx=(x1+x2)/2-dy/length*bend,cy=(y1+y2)/2+dx/length*bend;
 return{path:bend?`M${x1} ${y1}Q${cx} ${cy},${x2} ${y2}`:`M${x1} ${y1}L${x2} ${y2}`,x:(x1+2*cx+x2)/4,y:(y1+2*cy+y2)/4};
}

export function relationshipBends(edges:Link[]){
 const groups=new Map<string,Link[]>(),bends=new Map<string,number>();
 for(const edge of edges){const key=JSON.stringify([edge.source,edge.target].sort()),group=groups.get(key)||[];group.push(edge);groups.set(key,group);}
 for(const group of groups.values()){group.sort((a,b)=>a.id.localeCompare(b.id));group.forEach((edge,index)=>bends.set(edge.id,(index-(group.length-1)/2)*48*(edge.source<edge.target?1:-1)));}
 return bends;
}

/** Seed newly expanded records around their source without shifting existing nodes. */
export function expansionPositions(existing:PositionedNode[],incoming:PositionedNode[],source:string):Record<string,Point>{
 const positions=Object.fromEntries(existing.map(n=>[n.id,{x:n.x,y:n.y}])),anchor=positions[source]||{x:500,y:345},occupied=[...existing];
 for(const [i,node] of incoming.filter(n=>!positions[n.id]).entries()){
  let point={x:anchor.x+160,y:anchor.y};
  for(let attempt=0;attempt<80;attempt++){const angle=(i+attempt)*2.3999632297,distance=150+Math.floor((i+attempt)/8)*65;point={x:anchor.x+Math.cos(angle)*distance,y:anchor.y+Math.sin(angle)*distance};if(occupied.every(other=>Math.hypot(other.x-point.x,other.y-point.y)>other.r+node.r+18))break;}
  positions[node.id]=point;occupied.push({...node,...point});
 }
 return positions;
}
