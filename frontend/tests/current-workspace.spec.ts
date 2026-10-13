import {test,expect,type Page} from '@playwright/test';
import {checked,seedMockCatalog,seedDataset,seedTemplate,sessionHeaders,uploadReady} from './fixtures';

const password=process.env.AEGIS_SMOKE_PASSWORD;
const schema={type:'object',properties:{reference:{type:'string'}},required:['reference'],additionalProperties:false};
const source='SYNTHETIC browser fixture. Source reference SYN-2026. Original documents must remain unchanged.';
test.beforeEach(async({page})=>{
 if(!password)throw new Error('Run against an isolated mock deployment with AEGIS_SMOKE_PASSWORD set.');
 await checked(await page.request.post('/api/auth/login',{data:{username:process.env.AEGIS_SMOKE_USERNAME||'smoke',password}}));
 await page.goto('/#Home');await expect(page.getByRole('heading',{name:'Home',exact:true})).toBeVisible();
});
async function setup(page:Page){
 const headers=await sessionHeaders(page.request),models=await seedMockCatalog(page.request,headers,'Browser regression');
 const dataset=await seedDataset(page.request,headers,'Browser dataset '+Date.now(),[models.fast,models.careful],models.embedding);
 const template=await checked(await page.request.post('/api/templates',{headers,data:{name:'browser-prompt.json',dataset_id:dataset.id,schema}}));
 await page.reload();await expect(page.getByLabel('Refresh workspace',{exact:true})).toBeEnabled();
 return {headers,models,dataset,template};
}
async function agent(page:Page,dataset:string){
 await page.goto('/#Aegis%20Agent');await expect(page.getByLabel('Agent dataset')).toBeEnabled();await page.getByLabel('Agent dataset').selectOption(dataset);
 await expect(page.getByLabel('Agent Model')).toBeEnabled();
}
async function send(page:Page,text:string){
 await page.getByLabel('Message Aegis Agent').fill(text);await page.keyboard.press('Escape');await page.getByLabel('Send agent request').click();
}
async function extractionReady(page:Page,id:string){
 await expect.poll(async()=> (await checked(await page.request.get('/api/extractions/'+id))).status,{timeout:90000}).toBe('ready');
 return checked(await page.request.get('/api/extractions/'+id));
}

test('grouped navigation, route aliases and agent drawer work on desktop and mobile',async({page})=>{
 if(await page.getByLabel('Open navigation').isVisible())await page.getByLabel('Open navigation').click();
 const nav=page.getByRole('navigation',{name:'Workspace pages'});
 await nav.getByRole('button',{name:'Onboard',exact:true}).click();
 expect(await page.locator('#onboard-navigation .nav-item').allTextContents()).toEqual(['Dataset','Prompt','Extract','Review']);
 await nav.getByRole('button',{name:'Aegis Agent',exact:true}).click();
 await expect(page.locator('.sidebar')).not.toHaveClass(/open/);await expect(page.getByLabel('Message Aegis Agent')).toBeVisible();
 await expect(page.locator('.agent-shortcut')).toHaveCount(0);
 for(const [hash,title] of [['Datasets','Datasets'],['Prompt templates','Prompt templates'],['Extract Data','Extract'],['Review','Review'],['Model Registration','Model Registration'],['Model Mapping','Model Mapping'],['Home','Home']]){
  await page.goto('/#'+encodeURIComponent(hash));await expect(page.locator('main h1')).toHaveText(title);
 }
 await page.setViewportSize({width:390,height:844});await agent(page,'');await page.getByLabel('Open navigation').click();
 await expect(nav).toBeVisible();await nav.getByRole('button',{name:'Home',exact:true}).click();await expect(page.locator('.sidebar')).not.toHaveClass(/open/);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('model registration and mapping use tables and persist selected roles',async({page})=>{
 const w=await setup(page);await page.goto('/#Model%20Registration');await expect(page.getByRole('table')).toBeVisible();
 await expect(page.getByRole('row').filter({hasText:w.models.fast.name})).toBeVisible();
 await page.goto('/#Model%20Mapping');await page.getByRole('combobox',{name:'Dataset',exact:true}).selectOption(w.dataset.id);
 await expect(page.getByRole('table')).toBeVisible();await page.getByLabel('Chat model',{exact:true}).selectOption(w.models.careful.id);
 await page.getByRole('button',{name:'Save & Apply',exact:true}).click();
 await expect.poll(async()=> (await checked(await page.request.get(`/api/datasets/${w.dataset.id}/models`))).default_chat_model_id).toBe(w.models.careful.id);
 await page.reload();await page.getByRole('combobox',{name:'Dataset',exact:true}).selectOption(w.dataset.id);await expect(page.getByLabel('Chat model',{exact:true})).toHaveValue(w.models.careful.id);
});

test('Home dataset search is optional and filters matching cards',async({page})=>{
 const w=await setup(page);await page.reload();await page.getByLabel('Search datasets').click();
 await page.getByRole('textbox',{name:'Search datasets',exact:true}).fill(w.dataset.name);
 await expect(page.getByRole('article',{name:'Dataset '+w.dataset.name})).toBeVisible();
 await page.getByLabel('Clear and close dataset search').click();await expect(page.getByRole('textbox',{name:'Search datasets',exact:true})).toHaveCount(0);
});

test('agent command picker rejects malformed commands before API calls',async({page})=>{
 const w=await setup(page);await agent(page,w.dataset.id);
 await page.getByLabel('Message Aegis Agent').fill('@');await expect(page.getByRole('listbox',{name:'Agent shortcuts'})).toBeVisible();
 for(const command of ['@Onboard','@Upload','@Extract','@ReExtract'])await expect(page.getByRole('option').filter({hasText:command})).toBeVisible();
 let plans=0;page.on('request',request=>{if(request.method()==='POST'&&request.url().endsWith('/api/agent-v2/plans'))plans++;});
 await page.getByLabel('Message Aegis Agent').fill('@\\');await expect(page.getByLabel('Send agent request')).toBeDisabled();expect(plans).toBe(0);
});

test('onboards models, prompt and document through the Agent and publishes a saved extraction',async({page})=>{
 const w=await setup(page);await agent(page,'');await send(page,'@Onboard');
 const flow=page.getByRole('region',{name:'Dataset onboarding workflow'});await expect(flow).toBeVisible();
 await page.getByLabel('Onboarding dataset name').fill('Full onboarding '+Date.now());
 await page.getByLabel('Onboarding embedding model').selectOption(w.models.embedding.id);
 await page.getByLabel('Onboarding chat model').selectOption(w.models.fast.id);
 await page.getByLabel('Onboarding extraction model').selectOption(w.models.fast.id);
 await page.getByLabel('Upload documents and run extraction').check();
 await page.getByLabel('Onboarding documents').setInputFiles({name:'onboard.txt',mimeType:'text/plain',buffer:Buffer.from(source)});
 await page.getByLabel('Onboarding prompt JSON file').setInputFiles({name:'onboard-prompt.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({schema}))});
 const created=page.waitForResponse(r=>r.url().endsWith('/api/agent-v2/onboarding')&&r.request().method()==='POST');await page.getByRole('button',{name:'Confirm dataset onboarding',exact:true}).click();const workflow=await checked(await created);
 await expect.poll(async()=>{const saved=await checked(await page.request.get(`/api/agent-v2/onboarding/${workflow.id}`));if(saved.status==='failed')throw new Error('Synthetic onboarding failed: '+saved.error);return saved.status;},{timeout:90000}).toBe('completed');
 await expect(page.getByRole('button',{name:'Use dataset in Aegis Agent',exact:true})).toBeVisible({timeout:90000});
 await expect(flow.getByText(/Ready for review/).last()).toBeVisible();
 await page.getByRole('button',{name:'Use dataset in Aegis Agent',exact:true}).click();
 await expect(page.getByLabel('Agent dataset')).not.toHaveValue('');
});

test('confirmed upload and extraction save originals and Parquet; independent mode creates one result per file',async({page})=>{
 const w=await setup(page);await agent(page,w.dataset.id);
 const before=await checked(await page.request.get('/api/documents'));
 await page.locator('.agent-v2-compose-box input[type=file]').setInputFiles([
  {name:'first.txt',mimeType:'text/plain',buffer:Buffer.from(source)},
  {name:'second.txt',mimeType:'text/plain',buffer:Buffer.from(source+' Second original.')},
 ]);
 const proposed=page.waitForResponse(r=>r.url().endsWith('/api/agent-v2/plans')&&r.request().method()==='POST');await send(page,'@Extract');const plan=await checked(await proposed);await page.getByLabel('Workflow prompt template').selectOption(w.template.id);
 await expect(page.getByRole('button',{name:'Confirm upload and extraction',exact:true})).toBeDisabled();
 expect((await checked(await page.request.get('/api/documents'))).length).toBe(before.length);
 await page.getByLabel('Extraction mode').selectOption('independent');await page.getByRole('button',{name:'Confirm upload and extraction',exact:true}).click();
 await expect(page.getByRole('button',{name:'Review result and evidence'})).toHaveCount(2,{timeout:90000});
 const all=await checked(await page.request.get('/api/extractions')),runs=all.filter((item:any)=>(item.dataset_id||item.kb_id||item.parent_id)===w.dataset.id);expect(runs).toHaveLength(2);
 for(const run of runs){const saved=await extractionReady(page,run.id);expect(saved.output_reference).toMatch(/\.parquet$/);expect(saved.result.reference).toBe('MOCK TEST VALUE');}
 const docs=(await checked(await page.request.get('/api/documents'))).filter((item:any)=>(item.dataset_id||item.kb_id||item.parent_id)===w.dataset.id);expect(docs).toHaveLength(2);
 expect(await (await page.request.get(`/api/documents/${docs[0].id}/download`)).text()).toContain('SYN-2026');
 await expect.poll(async()=>{const saved=await checked(await page.request.get(`/api/agent-v2/plans/${plan.id}`));if(saved.calls.some((c:any)=>c.publication_error))throw new Error('Synthetic publication failed: '+JSON.stringify(saved.calls.map((c:any)=>({status:c.status,error:c.error}))));return saved.goal.status;},{timeout:90000}).toBe('completed');
 await expect(page.getByText('Goal steps',{exact:true})).toHaveCount(0);await expect(page.getByText('Pause goal answer',{exact:true})).toHaveCount(0);
});

test('ReExtract uses the chosen prompt and keeps the original saved extraction',async({page})=>{
 const w=await setup(page),doc=await uploadReady(page.request,w.headers,w.dataset,'rerun.txt',source);
 const first=await checked(await page.request.post('/api/extractions',{headers:w.headers,data:{dataset_id:w.dataset.id,document_ids:[doc.id],template_id:w.template.id}}));await extractionReady(page,first.id);
 await agent(page,w.dataset.id);const proposed=page.waitForResponse(r=>r.url().endsWith('/api/agent-v2/plans')&&r.request().method()==='POST');await send(page,'@ReExtract');const plan=await checked(await proposed);await page.getByLabel('Workflow documents').selectOption(doc.id);await page.getByLabel('Workflow prompt template').selectOption(w.template.id);
 await page.getByRole('button',{name:'Confirm re-extraction',exact:true}).click();await expect(page.getByRole('button',{name:'Review result and evidence'})).toBeVisible({timeout:90000});
 const runs=(await checked(await page.request.get('/api/extractions'))).filter((item:any)=>(item.dataset_id||item.kb_id||item.parent_id)===w.dataset.id);expect(runs).toHaveLength(2);expect(runs.some((item:any)=>item.id===first.id)).toBe(true);
 const old=await extractionReady(page,first.id);expect(old.version).toBe(1);expect(await (await page.request.get(`/api/documents/${doc.id}/download`)).text()).toBe(source);
 await expect.poll(async()=>{const saved=await checked(await page.request.get(`/api/agent-v2/plans/${plan.id}`));if(saved.calls.some((c:any)=>c.publication_error))throw new Error('Synthetic re-extract publication failed: '+JSON.stringify(saved.calls.map((c:any)=>({status:c.status,error:c.error}))));return saved.goal.status;},{timeout:90000}).toBe('completed');
});

test('chat cites published knowledge and opens and closes source evidence',async({page})=>{
 const w=await setup(page);await uploadReady(page.request,w.headers,w.dataset,'cited-source.txt',source);await agent(page,w.dataset.id);
 await send(page,'Summarize the key points');await expect(page.getByLabel('Copy agent answer')).toBeVisible({timeout:90000});
 await page.getByLabel('Open citation 1').click();const panel=page.getByRole('dialog',{name:'Source evidence'});await expect(panel).toBeVisible();await expect(panel).toContainText('cited-source.txt');await expect(panel).toContainText('SYN-2026');
 await page.getByLabel('Close citation source').click();await expect(panel).not.toBeVisible();await expect(page.getByLabel('Helpful agent answer')).toHaveCount(0);
 await page.getByLabel('Clear agent chat').click();await expect(page.getByLabel('Copy agent answer')).toHaveCount(0);
 await send(page,'List document filenames');await expect(page.getByLabel('Copy agent answer')).toBeVisible({timeout:90000});await expect(page.locator('.agent-v2-reply')).toContainText('cited-source.txt');
 await page.getByLabel('Sign out').click();await page.getByLabel('Username',{exact:true}).fill(process.env.AEGIS_SMOKE_USERNAME||'smoke');await page.getByLabel('Password',{exact:true}).fill(password!);await page.getByRole('button',{name:'Sign in',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Home',exact:true})).toBeVisible();await expect(page.getByLabel('Refresh workspace')).toBeEnabled();await agent(page,w.dataset.id);await expect(page.getByLabel('Copy agent answer')).toHaveCount(0);
});

test('a failed request restores its draft and retry completes against the real API',async({page})=>{
 const w=await setup(page);await uploadReady(page.request,w.headers,w.dataset,'retry-source.txt',source);await agent(page,w.dataset.id);
 await page.route('**/api/agent-v2/plans',route=>route.fulfill({status:503,json:{detail:'Synthetic temporary outage'}}),{times:1});
 await send(page,'List document filenames');await expect(page.getByRole('alert').filter({hasText:'Synthetic temporary outage'})).toBeVisible();
 await expect(page.getByLabel('Message Aegis Agent')).toHaveValue('List document filenames');await page.getByLabel('Send agent request').click();await expect(page.getByLabel('Copy agent answer')).toBeVisible({timeout:90000});
});

test('external-processing approval appears immediately and cancellation does not execute a plan',async({page})=>{
 const w=await setup(page);await agent(page,w.dataset.id);
 await page.route('**/api/agent-v2/consent',route=>route.fulfill({json:{dataset_id:w.dataset.id,required:true,destinations:[{key:'synthetic-external',title:'Synthetic external destination',description:'Test-only consent notice'}]}}));
 let plans=0;page.on('request',request=>{if(request.method()==='POST'&&request.url().endsWith('/api/agent-v2/plans'))plans++;});
 await send(page,'@Upload');const popup=page.getByRole('dialog',{name:'Allow external processing?'});await expect(popup).toBeVisible();expect(plans).toBe(0);
 await popup.getByRole('button',{name:'Cancel',exact:true}).click();await expect(popup).not.toBeVisible();expect(plans).toBe(0);
 await page.getByLabel('Send agent request').click();await popup.getByRole('button',{name:'Agree and continue',exact:true}).click();await expect(page.getByLabel('Workflow dataset')).toBeVisible();expect(plans).toBe(1);
});

test('composer grows with content and stays within the full chat width',async({page})=>{
 const w=await setup(page);await agent(page,w.dataset.id);const input=page.getByLabel('Message Aegis Agent'),before=(await input.boundingBox())!;
 await input.fill(Array.from({length:12},(_,i)=>'Long draft line '+i).join('\n'));await expect.poll(async()=> (await input.boundingBox())!.height).toBeGreaterThan(before.height);
 const composer=(await page.locator('.agent-v2-compose-box').boundingBox())!,area=(await page.locator('.agent-v2').boundingBox())!;expect(composer.width/area.width).toBeGreaterThan(.9);
 await input.fill('Short');await expect.poll(async()=> (await input.boundingBox())!.height).toBeLessThanOrEqual(before.height+2);
});

test('reselecting the current Extract dataset and prompt preserves rows and CSV export',async({page})=>{
 const w=await setup(page),doc=await uploadReady(page.request,w.headers,w.dataset,'table-export.txt',source);
 const run=await checked(await page.request.post('/api/extractions',{headers:w.headers,data:{dataset_id:w.dataset.id,document_ids:[doc.id],template_id:w.template.id}}));await extractionReady(page,run.id);
 await page.goto('/#Extract%20Data');await page.getByLabel('Extract dataset').selectOption(w.dataset.id);await page.getByLabel('Extract prompt template').selectOption(w.template.id);
 await expect(page.getByRole('table')).toContainText('MOCK TEST VALUE');
 await page.getByLabel('Extract dataset').selectOption(w.dataset.id);await page.getByLabel('Extract prompt template').selectOption(w.template.id);await expect(page.getByRole('table')).toContainText('MOCK TEST VALUE');
 await page.getByLabel('Export Extract results').click();const downloading=page.waitForEvent('download');await page.getByRole('button',{name:'CSV (.csv)',exact:true}).click();expect((await downloading).suggestedFilename()).toMatch(/\.csv$/);
 const exported=await page.request.get(`/api/extract-data/export?dataset_id=${w.dataset.id}&template_id=${w.template.id}&format=csv`);expect(await exported.text()).toContain('MOCK TEST VALUE');
});

test('current screens fit phone, tablet and desktop and retain shared blue progress styles',async({page})=>{
 test.setTimeout(180000);const w=await setup(page);
 const doc=await uploadReady(page.request,w.headers,w.dataset,'Responsive-'+('LongName'.repeat(8))+'.txt',source);
 const run=await checked(await page.request.post('/api/extractions',{headers:w.headers,data:{dataset_id:w.dataset.id,document_ids:[doc.id],template_id:w.template.id}}));await extractionReady(page,run.id);
 for(const width of [390,768,1440]){await page.setViewportSize({width,height:900});for(const hash of ['Home','Datasets','Model Registration','Model Mapping','Extract Data','Review','Aegis Agent']){
  await page.goto('/#'+encodeURIComponent(hash));await expect(page.locator('main h1')).toBeVisible();await expect(page.getByLabel('Refresh workspace')).toBeEnabled();
  if(hash==='Model Registration')await expect(page.getByRole('table',{name:'Registered models'})).toBeVisible();
  if(hash==='Model Mapping'){await page.getByRole('combobox',{name:'Dataset',exact:true}).selectOption(w.dataset.id);await expect(page.getByLabel('Chat model',{exact:true})).toBeEnabled();}
  if(hash==='Extract Data'){await page.getByLabel('Extract dataset').selectOption(w.dataset.id);await page.getByLabel('Extract prompt template').selectOption(w.template.id);await expect(page.getByRole('table')).toContainText('MOCK TEST VALUE');}
  if(hash==='Review'){await page.getByLabel('Extraction dataset filter').selectOption(w.dataset.id);await expect(page.getByRole('button',{name:'Review extraction '+run.id,exact:true})).toBeVisible();}
  if(hash==='Aegis Agent'){await page.getByLabel('Agent dataset').selectOption(w.dataset.id);await expect(page.getByLabel('Agent Model')).toBeEnabled();await expect(page.getByRole('heading',{name:'How can I help?',exact:true})).toBeVisible();}
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width+1);
  if(process.env.AEGIS_CAPTURE_SCREENSHOTS==='true')await page.screenshot({path:`screenshots/current-${hash.replaceAll(' ','-')}-${width}.png`,fullPage:true});
 }}
});
