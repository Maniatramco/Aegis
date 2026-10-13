// Verify the real colleague accounts can access their password screen over HTTPS.
// No account password is changed. Private credentials arrive on stdin only.
const {chromium,expect}=require('@playwright/test'),fs=require('node:fs');
(async()=>{
 const accounts=JSON.parse(fs.readFileSync(0,'utf8')),base=process.env.AEGIS_FORWARDED_URL;
 if(!base||new URL(base).protocol!=='https:')throw Error('Shared HTTPS URL required.');
 const out=process.env.ACCOUNT_RESULTS_DIR||'/results',report={url:base,checks:[],passwords_changed:false};
 const browser=await chromium.launch({executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,args:['--no-sandbox','--disable-dev-shm-usage']});
 try{
  for(const account of accounts){
   const context=await browser.newContext(),page=await context.newPage();page.setDefaultTimeout(30000);
   await page.goto(base);const next=page.getByRole('button',{name:'Continue',exact:true});if(await next.isVisible())await next.click();
   await page.locator('#login-username').fill(account.username);await page.locator('#login-password').fill(account.password);await page.getByRole('button',{name:'Sign in',exact:true}).click();await expect(page.locator('#login-password')).toHaveCount(0);
   await page.getByRole('button',{name:'Manage workspace',exact:true}).click();await page.getByRole('button',{name:'Users & passwords',exact:true}).click();await expect(page.getByRole('heading',{name:'My password',exact:true})).toBeVisible();await expect(page.locator('.account-summary')).toContainText(account.username);await expect(page.locator('.account-directory')).toHaveCount(0);
   if((await page.request.get(base+'/api/users')).status()!==403)throw Error('Ordinary account can list users.');
   if(process.env.AEGIS_EXPECT_UNASSIGNED==='true'){
    const datasets=await page.request.get(base+'/api/datasets');if(!datasets.ok()||(await datasets.json()).length)throw Error('Unexpected implicit dataset assignment');
    await page.getByRole('button',{name:'Datasets',exact:true}).click();await expect(page.getByRole('button',{name:'New dataset',exact:true})).toHaveCount(0);await expect(page.locator('main')).toContainText('No datasets assigned');
    await page.goto(base+'/#Users%20%26%20passwords');await expect(page.getByRole('heading',{name:'My password',exact:true})).toBeVisible();
   }
   await page.getByRole('button',{name:'Change my password',exact:true}).click();await expect(page.locator('#account-current-password')).toBeVisible();await expect(page.locator('#account-new-password')).toHaveValue('');await page.getByRole('button',{name:'Cancel',exact:true}).click();
   await page.getByRole('button',{name:'Sign out',exact:true}).click();await expect(page.locator('#login-password')).toBeVisible();
   report.checks.push({username:account.username,login:true,password_screen:true,admin_actions_blocked:true,unassigned_catalog_verified:process.env.AEGIS_EXPECT_UNASSIGNED==='true',logout:true});await context.close();
  }
  report.passed=true;console.log('Both colleague accounts passed HTTPS password-screen and administrator-access checks. No passwords changed.');
 }catch(error){report.passed=false;report.error=String(error.message).split('\n')[0];throw error;}finally{fs.writeFileSync(out+'/user-management-shared.json',JSON.stringify(report,null,2));await browser.close();}
})().catch(error=>{console.error(String(error.message).split('\n')[0]);process.exit(1);});
