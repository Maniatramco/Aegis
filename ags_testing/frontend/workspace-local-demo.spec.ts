import {test,expect,type Page} from '@playwright/test';

// Explicit opt-in: this suite only runs against the disposable synthetic gateway.
test.skip(process.env.AEGIS_SYNTHETIC_PREVIEW!=='1','Requires the isolated synthetic local preview, never a live workspace.');
async function info(page:Page){await expect.poll(async()=>{try{return(await page.request.get('/api/_demo/info')).ok();}catch{return false;}},{timeout:45000}).toBe(true);return(await page.request.get('/api/_demo/info')).json();}
async function goto(page:Page,route:string){await page.goto('/#'+encodeURIComponent(route));await expect(page.locator('main')).toBeVisible();await expect(page.getByRole('button',{name:'Sign out',exact:true})).toBeVisible();}
async function fits(page:Page){expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await expect(page.getByLabel('Local demo using synthetic data. Open demo controls',{exact:true})).toBeVisible();}

test('synthetic Dashboard, direct navigation, keyboard skip and responsive jobs remain usable',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));await info(page);
 await goto(page,'Dashboard');await expect(page.getByText('Local demo · synthetic data',{exact:true})).toBeVisible();
 await page.keyboard.press('Tab');await expect(page.getByRole('link',{name:'Skip to workspace',exact:true})).toBeFocused();await page.keyboard.press('Enter');await expect(page.locator('main')).toBeFocused();
 await page.getByRole('button',{name:'Open navigation',exact:true}).click();await page.getByRole('navigation',{name:'Workspace pages'}).getByRole('button',{name:'Jobs & activity',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Processing history'})).toBeVisible();await expect(page.locator('.job-row').first()).toBeVisible();
 for(const width of [320,390,768,1440]){await page.setViewportSize({width,height:900});await fits(page);await expect(page.getByRole('group',{name:'Filter jobs'})).toBeVisible();}
 await page.emulateMedia({reducedMotion:'reduce'});await page.locator('.job-details summary').first().click();
 expect(await page.locator('.workflow-stepper *').evaluateAll(nodes=>nodes.every(node=>getComputedStyle(node).animationDuration==='0s'||getComputedStyle(node).animationName==='none'))).toBe(true);
 expect(errors).toEqual([]);
});

test('Extract review preserves drafts on source retry, cancel, saved versions and original file',async({page})=>{
 const ids=await info(page);const original=await(await page.request.get(`/api/documents/${ids.documents.policy}/download`)).body();
 const created=await page.request.post('/api/extractions',{data:{dataset_id:ids.datasets.operations,document_ids:[ids.documents.policy],template_id:ids.template,allow_external:true}});expect(created.ok()).toBeTruthy();const result=await created.json();
 await expect.poll(async()=> (await(await page.request.get(`/api/extractions/${result.id}`)).json()).status).toBe('ready');
 let fail=true;await page.route(`**/api/documents/${ids.documents.policy}/preview*`,route=>fail?route.fulfill({status:503,json:{detail:'Synthetic interrupted source preview'}}):route.continue());
 await goto(page,'Review/'+result.id);const value=page.getByLabel('Value /reference',{exact:true});await expect(value).toBeVisible();const saved=await value.inputValue();
 await value.fill('Synthetic draft preserved');await expect(page.getByRole('button',{name:'Retry source preview',exact:true})).toBeVisible();fail=false;await page.getByRole('button',{name:'Retry source preview',exact:true}).click();await expect(value).toHaveValue('Synthetic draft preserved');await expect(page.getByRole('button',{name:'Retry source preview',exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'Cancel',exact:true}).click();await expect(value).toHaveValue(saved);
 await value.fill('SYN-reviewed-2026');await page.getByRole('button',{name:'Reviewed',exact:true}).click();await expect(value).toHaveAttribute('readonly','');
 const latest=await(await page.request.get(`/api/extractions/${result.id}`)).json();expect(latest.version).toBe(2);expect(latest.result.reference).toBe('SYN-reviewed-2026');expect((await(await page.request.get(`/api/extractions/${result.id}/versions`)).json())).toHaveLength(2);
 expect(await(await page.request.get(`/api/documents/${ids.documents.policy}/download`)).body()).toEqual(original);
 for(const width of [320,390,768,1440]){await page.setViewportSize({width,height:900});await fits(page);await expect(value).toBeVisible();}
 await goto(page,'Extract Data');await page.getByLabel('Extract dataset',{exact:true}).selectOption(ids.datasets.operations);await expect(page.getByRole('button',{name:new RegExp('Review extraction '+result.id)})).toBeVisible();await fits(page);
});

test('scoped Aegis Agent uses the actual mock workflow and exposes source citations',async({page})=>{
 const ids=await info(page);await goto(page,'Aegis Agent');await page.getByLabel('Agent dataset',{exact:true}).selectOption(ids.datasets.operations);
 await page.getByLabel('Message Aegis Agent',{exact:true}).fill('What is the project reference?');await page.getByRole('button',{name:'Send agent request',exact:true}).click();
 await expect(page.locator('.agent-v2-thread')).toContainText(/MOCK|SYN-2026/,{timeout:60000});
 await expect(page.getByRole('button',{name:'Speak your request',exact:true})).toBeDisabled();
 const sources=page.getByRole('button',{name:/Open citation/});await expect(sources.first()).toBeVisible();await sources.first().click();await expect(page.getByRole('dialog')).toBeVisible();
 await page.keyboard.press('Escape');for(const width of [320,390,768,1440]){await page.setViewportSize({width,height:900});await fits(page);}
});

test('stopping delayed answer waiting permits a fresh draft without duplicate submission',async({page})=>{
 const ids=await info(page);let replies=0,release!:()=>void;const held=new Promise<void>(resolve=>{release=resolve;});
 await page.route('**/api/agent-v2/plans/*/reply',async route=>{replies++;const response=await route.fetch();await held;try{await route.fulfill({response});}catch{/* Stop may already have closed the browser request. */}});
 await goto(page,'Aegis Agent');await page.getByLabel('Agent dataset',{exact:true}).selectOption(ids.datasets.operations);const composer=page.getByLabel('Message Aegis Agent',{exact:true});await composer.fill('Summarize the key points');await page.getByRole('button',{name:'Send agent request',exact:true}).click();
 await expect.poll(()=>replies).toBe(1);await page.getByRole('button',{name:'Stop answer',exact:true}).click();release();
 await expect(page.getByRole('button',{name:'Stop answer',exact:true})).toHaveCount(0);await composer.fill('A fresh synthetic draft');await expect(composer).toHaveValue('A fresh synthetic draft');expect(replies).toBe(1);
});

test('demo refuses real account/provider configuration and arbitrary document uploads',async({page})=>{
 const ids=await info(page);expect((await page.request.post('/api/auth/login',{data:{username:'synthetic-probe',password:'not-a-real-password'}})).status()).toBe(403);
 expect((await page.request.patch('/api/settings',{data:{model_provider:'openai'}})).status()).toBe(403);
 expect((await page.request.post('/api/documents/upload',{multipart:{dataset_id:ids.datasets.operations,files:{name:'synthetic-rejected.txt',mimeType:'text/plain',buffer:Buffer.from('Synthetic bytes outside the allowlisted sample.')}}})).status()).toBe(403);
});

test('failed file retry is explicit and cancellation preserves the original synthetic file',async({page})=>{
 const ids=await info(page);await goto(page,'Jobs & activity');const retry=page.getByRole('button',{name:'Retry index document for quarterly-summary.txt',exact:true});await expect(retry).toBeVisible();
 const retryResponse=page.waitForResponse(r=>r.url().includes('/api/jobs/')&&r.url().endsWith('/retry'));await retry.click();expect((await retryResponse).ok()).toBeTruthy();await expect(retry).toHaveCount(0);
 await expect.poll(async()=> (await(await page.request.get(`/api/documents/${ids.documents.failed}`)).json()).status,{timeout:45000}).toBe('ready');
 const original=await(await page.request.get(`/api/documents/${ids.documents.failed}/download`)).body();const started=await page.request.post('/api/_demo/start-index');expect(started.ok()).toBeTruthy();
 const refreshed=page.waitForResponse(r=>r.url().endsWith('/api/jobs'));await page.getByLabel('Refresh workspace',{exact:true}).click();await refreshed;const cancel=page.getByRole('button',{name:'Cancel index document for quarterly-summary.txt',exact:true});await expect(cancel).toBeVisible();await cancel.click();const dialog=page.getByRole('dialog');await expect(dialog).toContainText('Cancellation is best-effort');const cancelled=page.waitForResponse(r=>r.url().endsWith('/cancel')&&r.request().method()==='POST');await dialog.getByRole('button',{name:/Confirm/}).click();expect((await cancelled).ok()).toBeTruthy();await expect(dialog).toHaveCount(0);
 await expect.poll(async()=> (await(await page.request.get('/api/jobs')).json()).filter((j:any)=>j.target_id===ids.documents.failed).some((j:any)=>j.status==='cancelled'),{timeout:45000}).toBe(true);
 expect(await(await page.request.get(`/api/documents/${ids.documents.failed}/download`)).body()).toEqual(original);
});
