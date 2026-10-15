// Smoke the real HTTPS forwarded application, with private credentials on stdin.
const {chromium,expect}=require('@playwright/test');const fs=require('node:fs');
(async()=>{
 const auth=JSON.parse(fs.readFileSync(0,'utf8')),base=process.env.AEGIS_FORWARDED_URL;
 if(!base||new URL(base).protocol!=='https:')throw Error('HTTPS forwarded URL required.');
 const out=process.env.FORWARDED_RESULTS_DIR||'/results';fs.mkdirSync(out,{recursive:true});
 const report={url:base,started_at:new Date().toISOString(),checks:[],page_errors:[]};
 const browser=await chromium.launch({executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,args:['--no-sandbox','--disable-dev-shm-usage']});
 const page=await browser.newPage({viewport:{width:1280,height:900}});page.setDefaultTimeout(30000);page.on('pageerror',e=>report.page_errors.push(e.message));
 const check=async(name,fn)=>{const start=Date.now();await fn();report.checks.push({name,passed:true,seconds:(Date.now()-start)/1000});fs.writeFileSync(out+'/forwarded-access.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report.checks.at(-1)));};
 try{
  await check('HTTPS browser entry and secure context',async()=>{
   await page.goto(base,{waitUntil:'domcontentloaded'});
   const continueButton=page.getByRole('button',{name:'Continue',exact:true});
   if(await continueButton.isVisible())await continueButton.click();
   await expect(page.locator('#login-username')).toBeVisible();
   const context=await page.evaluate(()=>({secure:window.isSecureContext,uuid:typeof crypto.randomUUID}));if(!context.secure||context.uuid!=='function')throw Error('Forwarded browser lacks required secure context');report.browser_context=context;
  });
  await check('Unauthenticated workspace API remains protected',async()=>{
   const res=await page.request.get(base+'/api/auth/me');if(res.status()!==401)throw Error('Expected unauthenticated HTTP 401, got '+res.status());
  });
  await check('Real sign-in through forwarded URL',async()=>{
   await page.locator('#login-username').fill(auth.username);await page.locator('#login-password').fill(auth.password);
   const wait=page.waitForResponse(r=>r.url()===base+'/api/auth/login'&&r.request().method()==='POST');await page.getByRole('button',{name:'Sign in',exact:true}).click();const res=await wait;if(res.status()!==200)throw Error('Forwarded login HTTP '+res.status());await expect(page.getByRole('navigation')).toBeVisible();
   const me=await page.request.get(base+'/api/auth/me');if(me.status()!==200)throw Error('Forwarded authenticated session failed');
  });
  await check('Saved results load and Review button reveals selected result',async()=>{
   const datasets=await (await page.request.get(base+'/api/datasets')).json();const ds=datasets.find(d=>d.name.startsWith('All screens QA '));if(!ds)throw Error('Saved QA dataset missing');
   const runs=await (await page.request.get(base+'/api/extractions')).json();const run=runs.find(e=>e.kb_id===ds.id&&e.status==='ready'&&e.merge);if(!run)throw Error('Saved merged QA extraction missing');
   await page.getByRole('navigation').getByRole('button',{name:'Extraction Review',exact:true}).click();await page.getByLabel('Review dataset filter').selectOption(ds.id);
   await page.getByRole('button',{name:'Review extraction '+run.id,exact:true}).click();const heading=page.getByRole('heading',{name:'Review extraction',exact:true});await expect(heading).toBeInViewport();await expect(heading).toBeFocused();await expect(page.locator('.review-identity')).toContainText(run.id);await expect(page.getByLabel('Review profile')).toBeVisible();
   report.extraction_id=run.id;await page.screenshot({path:out+'/forwarded-review.png',fullPage:false});
  });
  await check('Logout invalidates the forwarded session',async()=>{
   await page.getByRole('button',{name:'Sign out',exact:true}).click();await expect(page.locator('#login-password')).toBeVisible();const me=await page.request.get(base+'/api/auth/me');if(me.status()!==401)throw Error('Session still authorized after logout');
  });
  if(report.page_errors.length)throw Error('Browser JavaScript errors');report.passed=true;
 }catch(error){report.passed=false;report.error=String(error.message).split('\n')[0];throw error;}finally{report.finished_at=new Date().toISOString();fs.writeFileSync(out+'/forwarded-access.json',JSON.stringify(report,null,2));await browser.close();}
})().catch(e=>{console.error(String(e.message).split('\n')[0]);process.exit(1);});
