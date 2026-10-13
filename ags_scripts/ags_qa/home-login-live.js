// Verify successful sign-ins land on Home using isolated Oracle QA accounts.
const {chromium,expect}=require('@playwright/test');const fs=require('node:fs'),crypto=require('node:crypto');
(async()=>{
 const auth=JSON.parse(fs.readFileSync(0,'utf8')),base=process.env.AEGIS_ACCOUNT_TEST_URL,out=process.env.ACCOUNT_RESULTS_DIR||'/results';
 if(auth.username!=='AccountUiAdmin'||!base)throw Error('Isolated QA credentials and URL required');
 const report={started_at:new Date().toISOString(),checks:[],page_errors:[]};
 const browser=await chromium.launch({executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,args:['--no-sandbox','--disable-dev-shm-usage','--unsafely-treat-insecure-origin-as-secure='+base]});
 const context=await browser.newContext({viewport:{width:1280,height:900}}),page=await context.newPage();page.setDefaultTimeout(30000);page.on('pageerror',e=>report.page_errors.push(e.message));
 const check=async(name,fn)=>{const t=Date.now();await fn();const result={name,passed:true,seconds:(Date.now()-t)/1000};report.checks.push(result);console.log(JSON.stringify(result));};
 const signIn=async(p,name,password,url=base)=>{await p.goto(url);await p.waitForLoadState('networkidle');await p.locator('#login-username').fill(name);await p.locator('#login-password').fill(password);await p.getByRole('button',{name:'Sign in',exact:true}).click();await expect(p.getByRole('heading',{name:'Home',exact:true})).toBeVisible();await expect(p.getByRole('button',{name:'Home',exact:true})).toHaveAttribute('aria-current','page');await expect(p).toHaveURL(/#Home$/);};
 try{
  await check('Administrator signs in from an old Assistant URL and lands on Home',()=>signIn(page,auth.username,auth.password,base+'/#Aegis%20Assistant'));
  await check('Authenticated root URL restores Home without overriding explicit navigation',async()=>{await page.goto(base);await expect(page.getByRole('heading',{name:'Home',exact:true})).toBeVisible();await page.getByRole('button',{name:'Aegis Agent',exact:true}).click();await expect(page.getByRole('heading',{name:'Aegis Agent',exact:true})).toBeVisible();await page.reload();await expect(page.getByRole('heading',{name:'Aegis Agent',exact:true})).toBeVisible();});
  await check('Signing out from another screen and signing back in lands on Home',async()=>{await page.getByRole('button',{name:'Sign out',exact:true}).click();await expect(page.locator('#login-password')).toBeVisible();await signIn(page,auth.username,auth.password,base+'/#Extraction%20Review');});
  await check('Ordinary user signs in from an old Review URL and lands on Home',async()=>{
   const me=await (await page.request.get(base+'/api/auth/me')).json(),users=await (await page.request.get(base+'/api/users')).json(),account=users.find(u=>u.username==='AccountUiOther');if(!account||account.is_admin)throw Error('Expected existing ordinary isolated QA account');
   const password=crypto.randomBytes(24).toString('base64'),reset=await page.request.post(base+'/api/users/'+account.id+'/password',{headers:{'X-CSRF-Token':me.csrf_token},data:{current_password:auth.password,password,confirmation:password}});if(!reset.ok())throw Error('Isolated QA password preparation failed');
   const ordinaryContext=await browser.newContext(),ordinary=await ordinaryContext.newPage();ordinary.on('pageerror',e=>report.page_errors.push(e.message));await signIn(ordinary,account.username,password,base+'/#Extraction%20Review');if((await (await ordinary.request.get(base+'/api/auth/me')).json()).user.is_admin)throw Error('Expected ordinary user');await ordinaryContext.close();
  });
  await page.screenshot({path:out+'/home-login.png'});if(report.page_errors.length)throw Error('Browser JavaScript errors');report.passed=true;
 }catch(error){report.passed=false;report.error=String(error.message).split('\n')[0];throw error;}
 finally{report.finished_at=new Date().toISOString();fs.mkdirSync(out,{recursive:true});fs.writeFileSync(out+'/home-login.json',JSON.stringify(report,null,2));await browser.close();}
})().catch(error=>{console.error(String(error.message).split('\n')[0]);process.exit(1);});
