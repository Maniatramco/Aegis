import {test,expect,type Page} from '@playwright/test';
import applicationVersion from '../../ags_frontend/app/application-version.json';

const models=[{id:'preview-chat',name:'Preview chat model',enabled:true,capabilities:['chat'],provider:'mock'}];
const datasets=[{id:'finance',name:'Finance',description:'Synthetic finance knowledge',active:true,models,default_chat_model_id:'preview-chat'},{id:'policy',name:'Policies',description:'Synthetic policy knowledge',active:true,models,default_chat_model_id:'preview-chat'},{id:'inactive',name:'Archived',active:false,models}];
const documents=[...Array.from({length:24},(_,i)=>({id:'finance-'+i,parent_id:'finance',dataset_id:'finance',name:i===0?'term-sheet.txt':`finance-evidence-${String(i+1).padStart(2,'0')}.txt`,status:'ready'})),{id:'policy-1',parent_id:'policy',dataset_id:'policy',name:'retention-policy.txt',status:'ready'},{id:'stale',dataset_id:'policy',name:'old-policy.txt',status:'ready',requires_reindex:true},{id:'private',dataset_id:'unassigned',name:'unassigned.txt',status:'ready'}];
async function preview(page:Page){
 const sent:any[]=[];
 page.on('pageerror',error=>console.error('Dashboard preview error:',error.message));
 await page.route('**/api/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  const json=(value:any)=>route.fulfill({json:value});
  if(path==='/api/auth/me')return json({user:{id:'preview',username:'Preview user',is_admin:true,role:'administrator'},csrf_token:'synthetic-preview',chat_session_id:'synthetic-dashboard-preview'});
  if(path==='/api/auth/status')return json({setup_required:false});
  if(path==='/api/datasets')return json(datasets);
  if(path==='/api/documents')return json(documents);
  if(path==='/api/models')return json(models);
  if(path==='/api/storage/status')return json({files:{provider:'local',name:'Synthetic files'},database:{provider:'local',name:'Synthetic database'},knowledge:{provider:'local',name:'Synthetic knowledge'}});
  if(path==='/api/settings')return json({max_upload_mb:25,storage_provider:'local',search_provider:'local'});
  if(path==='/api/dataset-chat/catalog')return json({datasets,documents,models});
  if(path==='/api/dataset-chat/conversations')return json([]);
  if(path==='/api/dataset-chat/reply'){
   sent.push(route.request().postDataJSON());
   return route.fulfill({contentType:'text/event-stream',body:'event: done\ndata: '+JSON.stringify({conversation_id:'synthetic-scope-proof',message:{id:'answer',role:'assistant',text:'Synthetic UI scope verification only.',status:'completed',citations:[],source_summary:{checked_count:2,cited_count:0,dataset_count:2,documents:2}}})+'\n\n'});
  }
  if(path==='/api/runtime-connections')return json({});
  return json([]);
 });
 await page.goto('/#Dashboard');await expect(page.getByRole('heading',{level:1,name:'Dashboard',exact:true})).toBeVisible();await expect(page.getByLabel('Refresh workspace',{exact:true})).toBeEnabled();
 return sent;
}

async function overview(page:Page){await page.getByRole('button',{name:'Restore Dashboard layout',exact:true}).click();}

test('including knowledge expands chat without sending, and layout changes preserve drafts and conversation',async({page})=>{
 await page.setViewportSize({width:1440,height:1000});const sent=await preview(page);
 const chat=page.getByRole('region',{name:'Dataset knowledge workspace chat',exact:true});
 const before=await chat.boundingBox();
 await page.getByRole('button',{name:'Add Dataset Knowledge',exact:true}).click();
 await page.getByRole('button',{name:'Include selected knowledge',exact:true}).click();
 await expect(page.getByRole('region',{name:'Onboarded datasets',exact:true})).toBeHidden();
 await expect(page.getByLabel('Dataset sources',{exact:true})).toBeHidden();
 await expect(page.getByLabel('Message Dataset Knowledge Chat',{exact:true})).toBeFocused();
 expect((await chat.boundingBox())!.height).toBeGreaterThan(before!.height+100);expect(sent).toEqual([]);
 const composer=page.getByLabel('Message Dataset Knowledge Chat',{exact:true});await composer.fill('Preserve this draft');
 await page.getByRole('button',{name:'Show sources',exact:true}).click();await expect(page.getByLabel('Dataset sources',{exact:true})).toBeVisible();
 await expect(composer).toHaveValue('Preserve this draft');await page.getByRole('button',{name:'Hide sources',exact:true}).click();
 await overview(page);await expect(page.getByRole('region',{name:'Onboarded datasets',exact:true})).toBeVisible();await expect(composer).toHaveValue('Preserve this draft');
 await page.getByRole('button',{name:'Expand Dataset Knowledge Chat',exact:true}).click();await expect(composer).toHaveValue('Preserve this draft');
 await page.getByLabel('Send dataset chat question',{exact:true}).click();await expect.poll(()=>sent.length).toBe(1);
 expect(sent[0].dataset_ids).toEqual(['finance','policy']);expect(sent[0].document_ids).toHaveLength(25);
 await expect(page.getByText('Synthetic UI scope verification only.',{exact:true})).toBeVisible();
 await overview(page);await page.getByRole('button',{name:'Expand Dataset Knowledge Chat',exact:true}).click();
 await expect(page.getByText('Synthetic UI scope verification only.',{exact:true})).toBeVisible();expect(sent).toHaveLength(1);
 await page.setViewportSize({width:390,height:844});await expect(composer).toBeInViewport();
 const bounds=await page.locator('.dataset-knowledge-chat .agent-v2-composer').boundingBox(),footer=await page.getByRole('contentinfo',{name:'Application status',exact:true}).boundingBox();
 expect(bounds!.y+bounds!.height).toBeLessThanOrEqual(footer!.y);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('sticky knowledge action survives source scrolling, source collapse and page scrolling',async({page})=>{
 await preview(page);await page.setViewportSize({width:1440,height:1000});
 const action=page.getByRole('button',{name:'Add Dataset Knowledge',exact:true});
 await page.getByRole('button',{name:'Ask Aegis about Finance',exact:true}).click();await overview(page);
 const sourceContent=page.locator('#notebook-source-content');await sourceContent.evaluate(element=>element.scrollTop=element.scrollHeight);
 const composer=await page.locator('.dataset-knowledge-chat .agent-v2-composer').boundingBox(),footer=await page.getByRole('contentinfo',{name:'Application status',exact:true}).boundingBox();expect(composer!.y+composer!.height).toBeLessThanOrEqual(footer!.y);
 await expect(action).toBeInViewport();await action.click();await expect(page.getByRole('dialog')).toBeVisible();await page.getByRole('button',{name:'Cancel',exact:true}).click();
 await page.getByRole('button',{name:'Collapse sources',exact:true}).click();await expect(action).toBeInViewport();await action.click();await expect(page.getByRole('dialog')).toBeVisible();await page.getByRole('button',{name:'Cancel',exact:true}).click();
 await page.getByRole('button',{name:'Expand sources',exact:true}).click();
 await page.locator('.dashboard-guide > summary').click();await page.evaluate(()=>window.scrollTo(0,300));await expect(action).toBeInViewport();
});

test('multi-select and drag/drop preserve exclusions and send the exact combined chat scope',async({page})=>{
 await page.setViewportSize({width:1440,height:1000});const sent=await preview(page);
 await page.getByRole('button',{name:'Ask Aegis about Policies',exact:true}).click();await overview(page);
 await page.getByRole('checkbox',{name:'Include dataset Finance in knowledge',exact:true}).check();await overview(page);
 await expect(page.getByRole('checkbox',{name:'Include dataset Policies in knowledge',exact:true})).toBeChecked();
 await expect(page.getByRole('checkbox',{name:'Include dataset Finance in knowledge',exact:true})).toBeChecked();
 await page.getByRole('checkbox',{name:'Include source finance-evidence-02.txt',exact:true}).uncheck();
 await page.getByRole('button',{name:'Ask Aegis about Finance',exact:true}).click();await overview(page);
 await page.getByRole('checkbox',{name:'Include source finance-evidence-02.txt',exact:true}).uncheck();
 const tile=page.locator('.dashboard-dataset-tile').filter({has:page.getByRole('button',{name:'Ask Aegis about Policies',exact:true})});
 await tile.dragTo(page.getByLabel('Dataset sources',{exact:true}));await overview(page);
 await expect(page.getByRole('checkbox',{name:'Include dataset Policies in knowledge',exact:true})).toBeChecked();
 await expect(page.getByRole('checkbox',{name:'Include source finance-evidence-02.txt',exact:true})).toHaveCount(0);
 await expect(page.getByRole('checkbox',{name:'Include source retention-policy.txt',exact:true})).toBeChecked();
 await expect(page.getByRole('checkbox',{name:'Include source old-policy.txt',exact:true})).toHaveCount(0);
 await expect(page.getByRole('checkbox',{name:'Include source unassigned.txt',exact:true})).toHaveCount(0);
 await expect(page.getByLabel('Dataset chat model',{exact:true})).toBeEnabled();
 await page.getByLabel('Message Dataset Knowledge Chat',{exact:true}).fill('Compare the included knowledge');await page.getByLabel('Send dataset chat question',{exact:true}).click();
 await expect.poll(()=>sent.length).toBe(1);expect(sent[0].dataset_ids).toEqual(['finance','policy']);expect(sent[0].document_ids).toHaveLength(24);expect(sent[0].document_ids).toContain('policy-1');expect(sent[0].document_ids).not.toContain('finance-1');expect(sent[0].document_ids).not.toContain('private');expect(sent[0].document_ids).not.toContain('stale');
 await expect(page.getByText('Synthetic UI scope verification only.',{exact:true})).toBeVisible();
 await expect(page.getByLabel('New dataset chat',{exact:true})).toBeEnabled();await page.getByLabel('New dataset chat',{exact:true}).click();
 if(process.env.AEGIS_KNOWLEDGE_DESKTOP_SCREENSHOT)await page.screenshot({path:process.env.AEGIS_KNOWLEDGE_DESKTOP_SCREENSHOT,fullPage:true});
});

test('picker supports multiple datasets and empty selection never broadens scope',async({page})=>{
 await preview(page);await page.getByRole('button',{name:'Ask Aegis about Policies',exact:true}).click();await overview(page);
 await page.getByRole('button',{name:'Add Dataset Knowledge',exact:true}).click();
 const dialog=page.getByRole('dialog');await dialog.getByRole('checkbox',{name:'Include dataset Finance',exact:true}).check();
 await dialog.getByRole('button',{name:'Include selected knowledge',exact:true}).click();await overview(page);
 await expect(page.getByRole('checkbox',{name:'Include dataset Finance in knowledge',exact:true})).toBeChecked();
 await page.getByRole('checkbox',{name:'Include dataset Finance in knowledge',exact:true}).uncheck();await overview(page);await page.getByRole('checkbox',{name:'Include dataset Policies in knowledge',exact:true}).uncheck();
 await expect(page.getByRole('heading',{name:'Choose knowledge for this chat',exact:true})).toBeVisible();await expect(page.getByLabel('Message Dataset Knowledge Chat',{exact:true})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Add Dataset Knowledge',exact:true})).toBeEnabled();
});

test('About and footer show the same version and prior feature history; mobile controls fit',async({page})=>{
 await page.setViewportSize({width:1440,height:1100});await preview(page);await page.getByRole('link',{name:`About Aegis, application version v${applicationVersion.version}`,exact:true}).click();
 await expect(page.getByRole('heading',{level:1,name:'About',exact:true})).toBeVisible();await expect(page.getByLabel(`Current application version v${applicationVersion.version}`,{exact:true})).toBeVisible();
 await expect(page.getByRole('heading',{name:'v26.1.0.0',exact:true})).toBeVisible();await expect(page.getByText('Drag dataset cards into Sources to include their accessible indexed files, preserving other selected sources.',{exact:true})).toBeVisible();
 if(process.env.AEGIS_ABOUT_SCREENSHOT)await page.screenshot({path:process.env.AEGIS_ABOUT_SCREENSHOT,fullPage:true});
 await page.setViewportSize({width:390,height:844});await page.goto('/#Dashboard');await page.getByRole('button',{name:'Ask Aegis about Policies',exact:true}).click();await overview(page);
 await page.getByRole('checkbox',{name:'Include dataset Finance in knowledge',exact:true}).check();await overview(page);
 await expect(page.getByRole('button',{name:'Add Dataset Knowledge',exact:true})).toBeInViewport();
 await page.getByRole('button',{name:'Add Dataset Knowledge',exact:true}).click();await expect(page.getByRole('dialog')).toBeVisible();await page.getByRole('button',{name:'Cancel',exact:true}).click();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 if(process.env.AEGIS_KNOWLEDGE_MOBILE_SCREENSHOT)await page.screenshot({path:process.env.AEGIS_KNOWLEDGE_MOBILE_SCREENSHOT,fullPage:true});
});
