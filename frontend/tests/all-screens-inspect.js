// Opt-in inspection of the real Docker UI. Private QA credentials arrive on stdin.
const {chromium,expect}=require('@playwright/test');const fs=require('node:fs');
(async()=>{
 let auth;try{auth=JSON.parse(fs.readFileSync(0,'utf8'));}catch{throw Error('Invalid QA credential input.');}
 const browser=await chromium.launch({executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,args:['--no-sandbox','--disable-dev-shm-usage','--unsafely-treat-insecure-origin-as-secure=http://web:3000']});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});page.setDefaultTimeout(30000);
 const report={screens:[],errors:[]};page.on('pageerror',e=>report.errors.push(e.message));
 try{
  await page.goto('http://web:3000/');await page.locator('#login-username').fill(auth.username);await page.locator('#login-password').fill(auth.password);await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await expect(page.locator('main h1').first()).toBeVisible();
  for(const name of ['Home','Aegis Agent','Datasets','Document Chat','Extraction Review','Re-extract','Prompt templates','Model Registration','Model Mapping','Dashboard','Jobs & activity','Connections','Services & migration','Users & passwords']){
   const nav=page.getByRole('navigation');const button=nav.getByRole('button',{name,exact:true});
   if(!await button.isVisible())await nav.getByRole('button',{name:'Manage workspace',exact:true}).click();
   await button.click();await expect(page.locator('main h1').first()).toBeVisible();
   report.screens.push({name,text:(await page.locator('main').innerText()).slice(0,3300),controls:await page.locator('main input,main select,main textarea,main button').evaluateAll(els=>els.map(el=>({tag:el.tagName,type:el.type,id:el.id,aria:el.getAttribute('aria-label'),text:el.tagName==='BUTTON'?el.textContent.trim():undefined,options:el.tagName==='SELECT'?[...el.options].map(o=>({value:o.value,label:o.label})):undefined}))) });
  }
 }catch(e){report.failure=e.message;process.exitCode=1;}
 finally{fs.writeFileSync('/results/all-screens-inspect.json',JSON.stringify(report,null,2));console.log(JSON.stringify({screens:report.screens.map(s=>s.name),failure:report.failure,errors:report.errors}));await browser.close();}
})();
