import {test,expect,type Page} from '@playwright/test';
import applicationVersion from '../../ags_frontend/app/application-version.json';

const models=[{id:'preview-chat',name:'Preview chat model',enabled:true,capabilities:['chat'],provider:'mock'}];
const datasets=[{id:'finance',name:'Finance',description:'Synthetic finance knowledge',active:true,models,default_chat_model_id:'preview-chat'},{id:'policy',name:'Policies',description:'Synthetic policy knowledge',active:true,models,default_chat_model_id:'preview-chat'},{id:'inactive',name:'Archived',active:false,models}];
const documents=[...Array.from({length:24},(_,i)=>({id:'finance-'+i,parent_id:'finance',dataset_id:'finance',name:i===0?'term-sheet.txt':`finance-evidence-${String(i+1).padStart(2,'0')}.txt`,status:'ready'})),{id:'policy-1',parent_id:'policy',dataset_id:'policy',name:'retention-policy.txt',status:'ready'},{id:'stale',dataset_id:'policy',name:'old-policy.txt',status:'ready',requires_reindex:true},{id:'private',dataset_id:'unassigned',name:'unassigned.txt',status:'ready'}];
let fixtureRevision=0;
async function preview(page:Page,options:{datasets?:any[];documents?:any[];datasetsError?:boolean;holdDatasets?:Promise<void>;onDatasetsRequested?:()=>void}={}){
 const fixtureDatasets=options.datasets??datasets,fixtureDocuments=options.documents??documents;
 const sent:any[]=[];
 page.on('pageerror',error=>console.error('Dashboard preview error:',error.message));
 await page.route('**/api/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  const json=(value:any)=>route.fulfill({json:value});
  if(path==='/api/auth/me')return json({user:{id:'preview',username:'Preview user',is_admin:true,role:'administrator'},csrf_token:'synthetic-preview',chat_session_id:'synthetic-dashboard-preview'});
  if(path==='/api/auth/status')return json({setup_required:false});
  if(path==='/api/datasets'){options.onDatasetsRequested?.();if(options.holdDatasets)await options.holdDatasets;return options.datasetsError?route.fulfill({status:503,json:{detail:'Synthetic dataset service unavailable'}}):json(fixtureDatasets);}
  if(path==='/api/documents')return json(fixtureDocuments);
  if(path==='/api/models')return json(models);
  if(path==='/api/storage/status')return json({files:{provider:'local',name:'Synthetic files'},database:{provider:'local',name:'Synthetic database'},knowledge:{provider:'local',name:'Synthetic knowledge'}});
  if(path==='/api/settings')return json({max_upload_mb:25,storage_provider:'local',search_provider:'local'});
  if(path==='/api/dataset-chat/catalog')return json({datasets:fixtureDatasets,documents:fixtureDocuments,models});
  if(path==='/api/dataset-chat/conversations')return json([]);
  if(path==='/api/dataset-chat/reply'){
   sent.push(route.request().postDataJSON());
   return route.fulfill({contentType:'text/event-stream',body:'event: done\ndata: '+JSON.stringify({conversation_id:'synthetic-scope-proof',message:{id:'answer',role:'assistant',text:'Synthetic UI scope verification only.',status:'completed',citations:[],source_summary:{checked_count:2,cited_count:0,dataset_count:2,documents:2}}})+'\n\n'});
  }
  if(path==='/api/runtime-connections')return json({});
  return json([]);
 });
 await page.goto(`/?dashboard-fixture=${++fixtureRevision}#Dashboard`);await expect(page.getByRole('heading',{level:1,name:'Dashboard',exact:true})).toBeVisible();await expect(page.getByLabel('Refresh workspace',{exact:true})).toBeEnabled();
 return sent;
}

async function openReadiness(page:Page){const summary=page.locator('.dashboard-readiness-summary');if(await summary.getAttribute('open')===null)await summary.locator('summary').click();}

test('chat owns the first viewport while genuine dataset cards retain details and keyboard selection',async({page})=>{
 await page.setViewportSize({width:1440,height:1000});const sent=await preview(page);
 await openReadiness(page);const metrics=page.getByLabel('Active dataset overview',{exact:true});await expect(metrics).toBeVisible();
 await expect(metrics.locator('dd')).toHaveText(['2','25','1','0']);
 await page.locator('.dashboard-readiness-summary > summary').click();
 const card=page.getByRole('button',{name:'Ask Aegis about Finance',exact:true});
 await expect(card.locator('.dashboard-card-description')).toBeVisible();await expect(card).toContainText('Synthetic finance knowledge');await expect(card).toContainText('24 sources');
 const chat=await page.getByLabel('Dataset knowledge workspace chat',{exact:true}).boundingBox(),workspace=await page.locator('.notebook-workspace').boundingBox();
 expect(chat!.width/workspace!.width).toBeGreaterThan(.70);expect(chat!.width/workspace!.width).toBeLessThan(.79);expect(chat!.y).toBeLessThan(180);
 await card.focus();await expect(card).toBeFocused();await page.keyboard.press('Enter');
 const composer=page.getByLabel('Message Dataset Knowledge Chat',{exact:true});await expect(composer).toBeFocused();
 await expect(page.getByLabel('Included indexed source count',{exact:true})).toHaveText('24 indexed sources');
 await page.getByRole('button',{name:'Summarize the key themes',exact:true}).click();await expect(composer).toBeFocused();await expect(composer).toHaveValue('Summarize the key themes');expect(sent).toEqual([]);
 await composer.fill('Retain my overview draft');
 await page.getByRole('button',{name:'Datasets (3)',exact:true}).click();await expect(card).toContainText('Selected');
 await expect(composer).toHaveValue('Retain my overview draft');expect(sent).toEqual([]);
 await page.getByRole('button',{name:'Expand Dataset Knowledge Chat',exact:true}).click();await expect(composer).toHaveValue('Retain my overview draft');
 await overview(page);expect(sent).toEqual([]);
});

test('mobile opens on chat with its composer visible, while long dataset names and source controls remain accessible',async({page})=>{
 const longName='Research '+ 'exceptionallylongdatasetname'.repeat(5);
 await preview(page,{datasets:[{...datasets[0],name:longName},datasets[1],datasets[2]]});
 for(const width of [320,390,768]){
  await page.setViewportSize({width,height:844});
  const composer=page.getByLabel('Message Dataset Knowledge Chat',{exact:true});await expect(composer).toBeInViewport();
  const bounds=await page.locator('.dataset-knowledge-chat .agent-v2-composer').boundingBox(),footer=await page.getByRole('contentinfo',{name:'Application status',exact:true}).boundingBox();expect(bounds!.y+bounds!.height).toBeLessThanOrEqual(footer!.y);
  await page.getByRole('button',{name:'Datasets (3)',exact:true}).click();
  await expect(page.getByRole('button',{name:`Ask Aegis about ${longName}`,exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.getByRole('button',{name:`Ask Aegis about ${longName}`,exact:true}).click();
  await page.getByRole('button',{name:'Sources (24)',exact:true}).click();await expect(page.getByLabel('Search dataset sources',{exact:true})).toBeVisible();
  await page.getByRole('checkbox',{name:'Include source term-sheet.txt',exact:true}).uncheck();
  await page.getByRole('button',{name:'Knowledge Chat',exact:true}).click();
  await expect(page.getByLabel('Message Dataset Knowledge Chat',{exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 }
});

test('empty, filtered, loading and failed dataset reads have honest states and no automatic model request',async({page})=>{
 const sent=await preview(page,{datasets:[],documents:[]});
 await expect(page.getByText('No datasets available',{exact:true})).toBeVisible();
 await openReadiness(page);await expect(page.getByLabel('Active dataset overview',{exact:true}).locator('dd')).toHaveText(['0','0','0','0']);expect(sent).toEqual([]);
 await page.unrouteAll({behavior:'wait'});await preview(page,{datasetsError:true,documents:[]});
 await expect(page.getByText('Datasets could not be loaded',{exact:true})).toBeVisible();
 await expect(page.getByRole('main',{name:'Dashboard',exact:true}).getByRole('alert')).toContainText('Synthetic dataset service unavailable');
 await page.getByRole('button',{name:'Dismiss error',exact:true}).click();
 await openReadiness(page);await expect(page.getByLabel('Active dataset overview',{exact:true}).locator('dd')).toHaveText(['—','—','—','—']);
 await page.unrouteAll({behavior:'wait'});let release!:()=>void,observed!:()=>void;const held=new Promise<void>(resolve=>release=resolve),requested=new Promise<void>(resolve=>observed=resolve);
 const ready=preview(page,{holdDatasets:held,onDatasetsRequested:observed});await requested;await openReadiness(page);
 await expect(page.getByLabel('Active dataset overview',{exact:true}).locator('dd')).toHaveText(['—','—','—','—']);release();await ready;
 await page.getByRole('button',{name:'Search datasets',exact:true}).click();await page.getByRole('textbox',{name:'Search datasets',exact:true}).fill('missing synthetic dataset');
 await expect(page.getByText('No matching datasets',{exact:true})).toBeVisible();await page.getByRole('button',{name:'Clear search',exact:true}).last().click();
 await expect(page.getByRole('button',{name:'Ask Aegis about Finance',exact:true})).toBeVisible();
});

async function overview(page:Page){const restore=page.getByRole('button',{name:'Restore Dashboard layout',exact:true});if(await restore.isVisible())await restore.click();}

test('mobile card shelf is visible with chat, collapses without losing a draft, and has a non-swipe route to all cards',async({page})=>{
 await page.setViewportSize({width:390,height:844});const sent=await preview(page);
 const shelf=page.getByRole('region',{name:'Quick dataset selection',exact:true});await expect(shelf).toBeVisible();
 const card=shelf.getByRole('button',{name:'Ask Aegis about Finance',exact:true});await expect(card.locator('.dashboard-card-description')).toBeVisible();
 const shelfBounds=await shelf.boundingBox(),cardBounds=await card.boundingBox();expect(cardBounds!.width).toBeLessThan(shelfBounds!.width);expect(shelfBounds!.height).toBeLessThan(140);
 await card.focus();await page.keyboard.press('Enter');const composer=page.getByLabel('Message Dataset Knowledge Chat',{exact:true});await expect(composer).toBeFocused();await composer.fill('Keep this card-selection draft');
 await shelf.getByRole('button',{name:'Ask Aegis about Finance',exact:true}).click();await expect(composer).toHaveValue('Keep this card-selection draft');await expect(card).toContainText('Selected');
 await page.getByRole('button',{name:'Hide dataset cards',exact:true}).click();await expect(shelf).toBeHidden();await expect(composer).toHaveValue('Keep this card-selection draft');await expect(composer).toBeInViewport();
 await page.getByRole('button',{name:'Show dataset cards',exact:true}).click();await expect(shelf).toBeVisible();
 await page.getByRole('button',{name:'All datasets',exact:true}).click();await expect(page.getByLabel('Authorized datasets',{exact:true})).toBeVisible();
 await expect(page.getByLabel('Authorized datasets',{exact:true})).toBeFocused();
 await expect(page.getByRole('button',{name:'Ask Aegis about Policies',exact:true}).locator('.dashboard-card-description')).toBeVisible();
 await page.getByRole('button',{name:'Knowledge Chat',exact:true}).click();await expect(composer).toHaveValue('Keep this card-selection draft');expect(sent).toEqual([]);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth&&scrollY===0)).toBe(true);
});
// Context controls and explicit expansion retain the mounted chat.

test('including knowledge keeps compact context without sending, and expansion preserves drafts and conversation',async({page})=>{
 await page.setViewportSize({width:1440,height:1000});const sent=await preview(page);
 const chat=page.getByRole('region',{name:'Dataset knowledge workspace chat',exact:true});
 const before=await chat.boundingBox();
 await page.getByRole('button',{name:'Add Dataset Knowledge',exact:true}).click();
 await page.getByRole('button',{name:'Include selected knowledge',exact:true}).click();
 await expect(page.getByRole('region',{name:'Onboarded datasets',exact:true})).toBeVisible();
 await expect(page.getByLabel('Message Dataset Knowledge Chat',{exact:true})).toBeFocused();
 await page.getByRole('button',{name:'Sources (25)',exact:true}).click();await expect(page.getByLabel('Dataset sources',{exact:true})).toBeVisible();
 expect((await chat.boundingBox())!.height).toBeGreaterThan(500);expect(sent).toEqual([]);
 await page.getByRole('button',{name:'Expand Dataset Knowledge Chat',exact:true}).click();
 expect((await chat.boundingBox())!.width).toBeGreaterThan(before!.width+100);
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
 await page.getByRole('button',{name:'Sources (24)',exact:true}).click();
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
 await page.getByRole('checkbox',{name:'Include dataset Finance in knowledge',exact:true}).click();await overview(page);
 await expect(page.getByRole('checkbox',{name:'Include dataset Policies in knowledge',exact:true})).toBeChecked();
 await expect(page.getByRole('checkbox',{name:'Include dataset Finance in knowledge',exact:true})).toBeChecked();
 await page.getByRole('button',{name:'Sources (25)',exact:true}).click();
 await page.getByRole('checkbox',{name:'Include source finance-evidence-02.txt',exact:true}).uncheck();
 await page.getByRole('button',{name:'Datasets (3)',exact:true}).click();
 await page.getByRole('button',{name:'Ask Aegis about Finance',exact:true}).click();await overview(page);
 await page.getByRole('button',{name:'Sources (24)',exact:true}).click();
 await page.getByRole('checkbox',{name:'Include source finance-evidence-02.txt',exact:true}).uncheck();
 await page.getByRole('button',{name:'Datasets (3)',exact:true}).click();
 const tile=page.locator('.dashboard-dataset-tile').filter({has:page.getByRole('button',{name:'Ask Aegis about Policies',exact:true})});
 await tile.dragTo(page.getByRole('toolbar',{name:'Dataset knowledge actions',exact:true}));await overview(page);
 await expect(page.getByRole('checkbox',{name:'Include dataset Policies in knowledge',exact:true})).toBeChecked();
 await page.getByRole('button',{name:'Sources (24)',exact:true}).click();
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
 await page.getByRole('checkbox',{name:'Include dataset Finance in knowledge',exact:true}).click();await overview(page);await page.getByRole('checkbox',{name:'Include dataset Policies in knowledge',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Choose knowledge for this chat',exact:true})).toBeVisible();await expect(page.getByLabel('Message Dataset Knowledge Chat',{exact:true})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Add Dataset Knowledge',exact:true})).toBeEnabled();
});

test('About and footer show the same version and prior feature history; mobile controls fit',async({page})=>{
 await page.setViewportSize({width:1440,height:1100});await preview(page);await page.getByRole('link',{name:`About Aegis, application version v${applicationVersion.version}`,exact:true}).click();
 await expect(page.getByRole('heading',{level:1,name:'About',exact:true})).toBeVisible();await expect(page.getByLabel(`Current application version v${applicationVersion.version}`,{exact:true})).toBeVisible();
 await expect(page.getByRole('heading',{name:'v26.1.0.0',exact:true})).toBeVisible();await expect(page.getByText('Drag dataset cards into Sources to include their accessible indexed files, preserving other selected sources.',{exact:true})).toBeVisible();
 if(process.env.AEGIS_ABOUT_SCREENSHOT)await page.screenshot({path:process.env.AEGIS_ABOUT_SCREENSHOT,fullPage:true});
 await page.setViewportSize({width:390,height:844});await page.goto('/#Dashboard');await page.getByRole('button',{name:'Datasets (3)',exact:true}).click();await page.getByRole('button',{name:'Ask Aegis about Policies',exact:true}).click();await overview(page);
 await page.getByRole('button',{name:'Datasets (3)',exact:true}).click();
 await page.getByRole('checkbox',{name:'Include dataset Finance in knowledge',exact:true}).click();await overview(page);
 await expect(page.getByRole('button',{name:'Add Dataset Knowledge',exact:true})).toBeInViewport();
 await page.getByRole('button',{name:'Add Dataset Knowledge',exact:true}).click();await expect(page.getByRole('dialog')).toBeVisible();await page.getByRole('button',{name:'Cancel',exact:true}).click();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 if(process.env.AEGIS_KNOWLEDGE_MOBILE_SCREENSHOT)await page.screenshot({path:process.env.AEGIS_KNOWLEDGE_MOBILE_SCREENSHOT,fullPage:true});
});
