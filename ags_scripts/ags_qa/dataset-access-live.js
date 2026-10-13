// Actual browser, API, worker and Oracle; isolated AEGIS_TEST uses mock inference.
const {chromium,expect}=require('@playwright/test');
const fs=require('node:fs'),crypto=require('node:crypto');
(async()=>{
 const auth=JSON.parse(fs.readFileSync(0,'utf8')),base=process.env.AEGIS_ACCOUNT_TEST_URL,out='/results';
 if(!base)throw Error('Dedicated test deployment URL required');
 const report={database:'Oracle AEGIS_TEST',inference:'mock (permission/workflow test)',checks:[],page_errors:[]};
 const browser=await chromium.launch({executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,args:['--no-sandbox','--disable-dev-shm-usage']});
 const contexts=[],pages=[];const newPage=async()=>{const c=await browser.newContext({viewport:{width:1280,height:900}});contexts.push(c);const p=await c.newPage();p.setDefaultTimeout(30000);p.on('pageerror',e=>report.page_errors.push(e.message));pages.push(p);return p;};
 const admin=await newPage(),user=await newPage(),other=await newPage(),password=crypto.randomBytes(24).toString('base64');
 const check=async(name,fn)=>{let t=Date.now();console.log(JSON.stringify({starting:name}));await fn();report.checks.push({name,passed:true,seconds:(Date.now()-t)/1000});console.log(JSON.stringify(report.checks.at(-1)));};
 const login=async(p,name,pw)=>{await p.goto(base);await p.locator('#login-username').fill(name);await p.locator('#login-password').fill(pw);await p.getByRole('button',{name:'Sign in',exact:true}).click();await expect(p.getByRole('navigation')).toBeVisible();};
 const get=async(p,path)=>{const r=await p.request.get(base+'/api'+path);if(!r.ok())throw Error('GET '+path+' returned '+r.status());return r.json();};
 const write=async(p,path,data,method='post')=>{const me=await get(p,'/auth/me');const r=await p.request[method](base+'/api'+path,{headers:{'X-CSRF-Token':me.csrf_token},data});if(!r.ok())throw Error(method+' '+path+' returned '+r.status());return r.json();};
 const navigate=async(p,name)=>{const n=p.getByRole('navigation');const b=n.getByRole('button',{name,exact:true});if(!await b.isVisible())await n.getByRole('button',{name:'Manage workspace',exact:true}).click();await b.click();};
 const openMapping=async(id)=>{await admin.goto(base+'/#Users%20%26%20passwords');await admin.locator('.account-table tbody tr').filter({hasText:id===first.id?'AccountUiColleague':'AccountUiOther'}).getByRole('button',{name:'Dataset access',exact:true}).click();};
 let first,second,a,b,ex,doc;
 try{
  await check('Admin creates two users and two separate datasets',async()=>{
   await login(admin,auth.username,auth.password);
   first=await write(admin,'/users',{username:'AccountUiColleague',password,confirmation:password});second=await write(admin,'/users',{username:'AccountUiOther',password,confirmation:password});
   a=await write(admin,'/datasets',{name:'Assigned invoice QA'});b=await write(admin,'/datasets',{name:'Private admin QA'});
   a=await write(admin,'/datasets/'+a.id+'/migrate-settings');
  });
  await check('Unassigned users see no datasets and no administrator controls',async()=>{
   await login(user,first.username,password);await login(other,second.username,password);
   if((await get(user,'/datasets')).length||(await get(other,'/datasets')).length)throw Error('Unassigned dataset leak');
   await navigate(user,'Users & passwords');await expect(user.getByRole('button',{name:'Add user',exact:true})).toHaveCount(0);await expect(user.getByRole('button',{name:'Dataset access',exact:true})).toHaveCount(0);
   if((await user.request.get(base+'/api/users')).status()!==403)throw Error('User directory exposed');
  });
  await check('Admin assigns a dataset through the actual mapping screen',async()=>{
   await openMapping(first.id);const panel=admin.getByRole('region',{name:'Dataset access for '+first.username});await panel.getByRole('checkbox',{name:a.name,exact:true}).check();await panel.getByRole('button',{name:'Save dataset access',exact:true}).click();await expect(panel.getByRole('status')).toContainText('Saved dataset access');
   const mapping=await get(admin,'/users/'+first.id+'/datasets');if(mapping.dataset_ids.join()!==a.id)throw Error('Assignment was not stored');await admin.screenshot({path:out+'/dataset-assignments.png',fullPage:true});
   await admin.reload();await openMapping(first.id);await expect(admin.getByRole('region',{name:'Dataset access for '+first.username}).getByRole('checkbox',{name:a.name,exact:true})).toBeChecked();
   await admin.setViewportSize({width:390,height:844});if(await admin.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Mapping screen overflows mobile viewport');await admin.screenshot({path:out+'/dataset-assignments-mobile.png',fullPage:true});await admin.setViewportSize({width:1280,height:900});
  });
  await check('Assigned dataset appears in Assistant, Datasets and Review filters only',async()=>{
   await user.reload();await navigate(user,'Aegis Agent');const select=user.getByLabel('Agent dataset',{exact:true});await expect(select.locator('option').filter({hasText:a.name})).toHaveCount(1);await expect(select.locator('option').filter({hasText:b.name})).toHaveCount(0);await select.selectOption(a.id);
   await navigate(user,'Datasets');await expect(user.locator('main')).toContainText(a.name);await expect(user.locator('main')).not.toContainText(b.name);await expect(user.getByRole('button',{name:'New dataset',exact:true})).toHaveCount(0);await expect(user.getByRole('button',{name:'Settings',exact:true})).toHaveCount(0);await expect(user.getByRole('button',{name:'Model Mapping',exact:true})).toHaveCount(0);
   await navigate(user,'Extraction Review');await expect(user.getByLabel('Review dataset filter').locator('option').filter({hasText:a.name})).toHaveCount(1);if((await other.request.get(base+'/api/datasets/'+a.id)).status()!==404)throw Error('Unmapped user can open assigned dataset');
  });
  await check('Assigned user uploads, indexes and extracts using the real worker',async()=>{
   const me=await get(user,'/auth/me');const r=await user.request.post(base+'/api/documents/upload',{headers:{'X-CSRF-Token':me.csrf_token},multipart:{dataset_id:a.id,allow_external:'true',files:{name:'assignment-invoice.txt',mimeType:'text/plain',buffer:Buffer.from('Fictional invoice total 42.')}}});if(!r.ok())throw Error('Mapped upload returned '+r.status());doc=(await r.json()).documents[0];
   await expect.poll(async()=>{const d=await get(user,'/documents/'+doc.id);if(d.status==='failed')throw Error(d.error);return d.status;},{timeout:90000,intervals:[1000]}).toBe('ready');
   const template=await write(user,'/templates',{name:'assignment-invoice.json',source_filename:'assignment-invoice.json',dataset_id:a.id,schema:{type:'object',properties:{total:{type:'number'}},required:['total'],additionalProperties:false}});
   ex=await write(user,'/extractions',{dataset_id:a.id,document_ids:[doc.id],template_id:template.id,allow_external:true});await expect.poll(async()=>{const e=await get(user,'/extractions/'+ex.id);if(e.status==='failed')throw Error(e.error);return e.status;},{timeout:90000,intervals:[1000]}).toBe('ready');
   const conversation=await write(user,'/conversations',{dataset_id:a.id});const answer=await write(user,'/conversations/'+conversation.id+'/messages',{text:'What is the invoice total?',allow_external:true});if(!answer.message.citations.length)throw Error('Assigned user retrieval has no citations');
  });
  await check('Review arrow opens assigned extraction; edit and save succeeds',async()=>{
   await user.reload();await navigate(user,'Extraction Review');await user.getByLabel('Review dataset filter').selectOption(a.id);await user.getByRole('button',{name:'Review extraction '+ex.id,exact:true}).click();await expect(user.locator('.review-identity')).toContainText(ex.id);await expect(user.locator('.review-identity')).toContainText(a.name);await user.getByLabel('Value /total',{exact:true}).fill('42');await user.getByRole('button',{name:'Save changes',exact:true}).click();await expect(user.getByText('All changes saved',{exact:true})).toBeVisible();if((await get(user,'/extractions/'+ex.id)).result.total!==42)throw Error('Review edit not persisted');await user.screenshot({path:out+'/assigned-user-review.png',fullPage:true});
  });
  await check('Second assignment shares completed results but not private chats',async()=>{
   await openMapping(second.id);const panel=admin.getByRole('region',{name:'Dataset access for '+second.username});await panel.getByRole('checkbox',{name:a.name,exact:true}).check();await panel.getByRole('button',{name:'Save dataset access',exact:true}).click();await expect(panel.getByRole('status')).toContainText('Saved dataset access');
   await other.reload();await navigate(other,'Extraction Review');await other.getByRole('button',{name:'Review extraction '+ex.id,exact:true}).click();await expect(other.locator('.review-identity')).toContainText(ex.id);if((await get(other,'/conversations')).length)throw Error('Private conversation shared');
  });
  await check('Removing access blocks old IDs immediately, preserves admin and second user data',async()=>{
   await openMapping(first.id);const panel=admin.getByRole('region',{name:'Dataset access for '+first.username});await panel.getByRole('checkbox',{name:a.name,exact:true}).uncheck();await panel.getByRole('button',{name:'Save dataset access',exact:true}).click();await expect(panel.getByRole('status')).toContainText('Saved dataset access');
   for(const path of ['/datasets/'+a.id,'/documents/'+doc.id+'/download','/extractions/'+ex.id,'/extractions/'+ex.id+'/export'])if((await user.request.get(base+'/api'+path)).status()!==404)throw Error('Revoked link still allowed: '+path);
   if((await get(user,'/datasets')).length)throw Error('Revoked dataset in catalog');await user.reload();await navigate(user,'Aegis Agent');await expect(user.getByLabel('Agent dataset').locator('option').filter({hasText:a.name})).toHaveCount(0);
   await get(admin,'/extractions/'+ex.id);await get(other,'/extractions/'+ex.id);const mappings=await get(admin,'/users/'+first.id+'/datasets');if(!mappings.assignments.some(g=>g.dataset_id===a.id&&!g.enabled&&g.updated_by==='administrator'))throw Error('Revocation audit missing');
  });
  if(report.page_errors.length)throw Error('Browser JavaScript errors');report.passed=true;
 }catch(e){report.passed=false;report.error=String(e.message).split('\n')[0];for(const p of pages)for(const input of await p.locator('input[type=password]').all())await input.fill('');await user.screenshot({path:out+'/dataset-access-failure.png'});throw e;}
 finally{report.finished_at=new Date().toISOString();fs.writeFileSync(out+'/dataset-access.json',JSON.stringify(report,null,2));await browser.close();}
})().catch(e=>{console.error(String(e.message).split('\n')[0]);process.exit(1);});
