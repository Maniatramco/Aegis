// Verify existing User1/User2 against the installed Docker web service.
const {chromium,expect}=require('@playwright/test'),fs=require('node:fs');
(async()=>{
 const accounts=JSON.parse(fs.readFileSync(0,'utf8')),base='http://localhost:3000';
 const browser=await chromium.launch({executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,args:['--no-sandbox','--disable-dev-shm-usage']});
 const report={runtime:'Installed Oracle Docker',passwords_changed:false,checks:[]};
 try{for(const account of accounts){const context=await browser.newContext();const p=await context.newPage();
  await p.goto(base);await p.locator('#login-username').fill(account.username);await p.locator('#login-password').fill(account.password);await p.getByRole('button',{name:'Sign in',exact:true}).click();await expect(p.getByRole('navigation')).toBeVisible();
  const datasets=await p.request.get(base+'/api/datasets');if(!datasets.ok()||(await datasets.json()).length)throw Error('Unexpected implicit dataset access');if((await p.request.get(base+'/api/users')).status()!==403)throw Error('User directory exposed');
  await p.getByRole('button',{name:'Datasets',exact:true}).click();await expect(p.getByRole('button',{name:'New dataset',exact:true})).toHaveCount(0);await expect(p.locator('main')).toContainText('No datasets assigned');
  await p.getByRole('button',{name:'Manage workspace',exact:true}).click();await p.getByRole('button',{name:'Users & passwords',exact:true}).click();await expect(p.getByRole('heading',{name:'My password',exact:true})).toBeVisible();await expect(p.locator('.account-directory')).toHaveCount(0);
  await p.getByRole('button',{name:'Sign out',exact:true}).click();await expect(p.locator('#login-password')).toBeVisible();report.checks.push({username:account.username,login:true,unassigned_datasets_hidden:true,administrator_controls_blocked:true,password_screen:true,logout:true});await context.close();
 }report.passed=true;console.log('Existing User1/User2 passed installed Docker permissions and login checks; passwords unchanged.');}
 catch(e){report.passed=false;report.error=String(e.message).split('\n')[0];throw e;}finally{fs.writeFileSync('/results/dataset-access-installed.json',JSON.stringify(report,null,2));await browser.close();}
})().catch(e=>{console.error(String(e.message).split('\n')[0]);process.exit(1);});
