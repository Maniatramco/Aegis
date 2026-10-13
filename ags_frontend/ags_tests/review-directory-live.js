// Real Docker browser regression for opening saved results; no mocked responses.
// Private QA credentials arrive through stdin and are never written to the report.
const {chromium,expect}=require('@playwright/test');
const fs=require('node:fs');
(async()=>{
 const auth=JSON.parse(fs.readFileSync(0,'utf8'));
 const out=process.env.REVIEW_RESULTS_DIR||'/results';fs.mkdirSync(out,{recursive:true});
 const report={started_at:new Date().toISOString(),checks:[],page_errors:[]};
 const browser=await chromium.launch({executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,args:['--no-sandbox','--disable-dev-shm-usage','--unsafely-treat-insecure-origin-as-secure=http://web:3000']});
 const page=await browser.newPage({viewport:{width:1294,height:582}});page.setDefaultTimeout(30000);
 page.on('pageerror',error=>report.page_errors.push(error.message));
 const persist=()=>fs.writeFileSync(out+'/review-button-regression.json',JSON.stringify(report,null,2));
 const check=async(name,fn)=>{const start=Date.now();try{await fn();report.checks.push({name,passed:true,seconds:(Date.now()-start)/1000});}catch(error){report.checks.push({name,passed:false,error:String(error.message).split('\n')[0]});throw error;}finally{persist();console.log(JSON.stringify(report.checks.at(-1)));}};
 const endpoint=id=>'http://web:3000/api/extractions/'+id;
 const heading=page.getByRole('heading',{name:'Review extraction',exact:true});
 async function open(id,kind='Review'){
  const response=page.waitForResponse(r=>r.url()===endpoint(id)&&r.request().method()==='GET');
  await page.getByRole('button',{name:kind+' extraction '+id,exact:true}).click();
  const res=await response;if(res.status()!==200)throw Error('Saved result HTTP '+res.status());
  await expect(heading).toBeInViewport();await expect(heading).toBeFocused();
  await expect(page.locator('.review-identity')).toContainText(id);
  const rect=await heading.boundingBox();if(rect.y<0||rect.y+rect.height>page.viewportSize().height)throw Error('Heading is outside viewport: '+JSON.stringify(rect));
  return res.json();
 }
 try{
  await page.goto('http://web:3000/');await page.locator('#login-username').fill(auth.username);await page.locator('#login-password').fill(auth.password);
  const login=page.waitForResponse(r=>r.url().endsWith('/api/auth/login')&&r.request().method()==='POST');await page.getByRole('button',{name:'Sign in',exact:true}).click();if((await login).status()!==200)throw Error('QA login failed');await expect(page.getByRole('navigation')).toBeVisible();
  const datasets=await (await page.request.get('http://web:3000/api/datasets')).json();
  const dataset=datasets.find(d=>d.id===process.env.REVIEW_DATASET)||datasets.find(d=>d.name.startsWith('All screens QA '));if(!dataset)throw Error('Saved QA dataset missing');
  const all=await (await page.request.get('http://web:3000/api/extractions')).json();
  const runs=(Array.isArray(all)?all:all.extractions).filter(e=>(e.dataset_id||e.parent_id||e.kb_id)===dataset.id&&e.status==='ready');
  const independent=runs.find(e=>!e.merge),merged=runs.find(e=>e.merge);if(!independent||!merged)throw Error('Independent and merged QA results required');
  report.dataset_id=dataset.id;report.extraction_ids=[independent.id,merged.id];
  await page.getByRole('navigation').getByRole('button',{name:'Extraction Review',exact:true}).click();await page.getByLabel('Review dataset filter').selectOption(dataset.id);
  for(const viewport of [{width:1294,height:582},{width:390,height:844}]){
   await page.setViewportSize(viewport);
   await check(`Arrow opens independent result in viewport ${viewport.width}x${viewport.height}`,async()=>{await open(independent.id);await expect(page.locator('.review-field input').first()).toBeVisible();});
   await check(`ID opens merged result in viewport ${viewport.width}x${viewport.height}`,async()=>{await open(merged.id,'Open');await expect(page.getByLabel('Review profile')).toBeVisible();});
   await check(`Arrow reopens same merged result in viewport ${viewport.width}x${viewport.height}`,async()=>{await open(merged.id);});
   await check(`Unsaved changes guard preserves review in viewport ${viewport.width}x${viewport.height}`,async()=>{
    const field=page.locator('.review-field input').first();const saved=await field.inputValue();await field.fill('Unsaved QA test');
    const requestCount=[];const listener=req=>{if(req.url()===endpoint(independent.id))requestCount.push(req.url());};page.on('request',listener);
    page.once('dialog',dialog=>dialog.dismiss());await page.getByRole('button',{name:'Review extraction '+independent.id,exact:true}).click();
    await expect(page.locator('.review-identity')).toContainText(merged.id);await expect(field).toHaveValue('Unsaved QA test');if(requestCount.length)throw Error('Dismissed guard still fetched another extraction');page.off('request',listener);
    await page.getByRole('button',{name:'Cancel',exact:true}).click();await expect(field).toHaveValue(saved);
   });
   await check(`Confirmed discard restores the same extraction in viewport ${viewport.width}x${viewport.height}`,async()=>{
    const field=page.locator('.review-field input').first();const saved=await field.inputValue();await field.fill('Discard this QA draft');page.once('dialog',dialog=>dialog.accept());await open(merged.id);await expect(field).toHaveValue(saved);
   });
   await open(independent.id);
   await page.screenshot({path:out+`/review-button-fixed-${viewport.width}.png`,fullPage:false});
   if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Horizontal overflow');
  }
  await check('Refresh retains saved results and Review still reveals the selection',async()=>{
   await page.getByLabel('Refresh workspace',{exact:true}).click();await expect(page.getByLabel('Refresh workspace',{exact:true})).toBeEnabled();await open(merged.id);
  });
  if(report.page_errors.length)throw Error('Browser page errors');report.passed=true;
 }finally{report.finished_at=new Date().toISOString();persist();await browser.close();}
})().catch(error=>{console.error(String(error.message).split('\n')[0]);process.exit(1);});
