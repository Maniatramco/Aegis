// Real Qwen/Ollama in isolated Oracle QA. No scripted model responses.
const {chromium,expect}=require('@playwright/test');const fs=require('node:fs');
(async()=>{
 const auth=JSON.parse(fs.readFileSync(0,'utf8')),base=process.env.AEGIS_ACCOUNT_TEST_URL,out='/results',baseline=process.env.AEGIS_ALL_PHASE==='baseline',uiOnly=process.env.AEGIS_ALL_PHASE==='ui';
 if(auth.username!=='AccountUiAdmin'||!base)throw Error('Isolated QA credentials required');
 const report={started_at:new Date().toISOString(),checks:[],layouts:[],page_errors:[],streams:[]};
 const browser=await chromium.launch({executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,args:['--no-sandbox','--disable-dev-shm-usage','--unsafely-treat-insecure-origin-as-secure='+base]});
 const context=await browser.newContext({viewport:{width:938,height:668}}),page=await context.newPage();page.setDefaultTimeout(30000);page.on('pageerror',e=>report.page_errors.push(e.message));
 await page.addInitScript(()=>{
  window.__streams=[];window.__renders=[];const original=window.fetch;
  window.fetch=async(...args)=>{
   const start=performance.now(),response=await original(...args);
   if(String(args[0]).match(/agent-v2\/plans\/[^/]+\/reply$/)&&response.ok){
    const entry={start,headers_at:performance.now(),events:[]};window.__streams.push(entry);const reader=response.clone().body.getReader(),decoder=new TextDecoder();let pending='';
    (async()=>{try{for(;;){const {value,done}=await reader.read();if(done)break;pending+=decoder.decode(value,{stream:true});let index;while((index=pending.indexOf('\n\n'))>=0){const frame=pending.slice(0,index);pending=pending.slice(index+2);const data=frame.split('\n').find(line=>line.startsWith('data: '));if(data){const event=JSON.parse(data.slice(6));entry.events.push({at:performance.now(),type:frame.match(/event: (\w+)/)?.[1],length:event.text?.length||event.message?.text?.length||0,status:event.message?.status});}}}}catch(error){entry.error=error.name;}})();
   }return response;
  };
  window.addEventListener('DOMContentLoaded',()=>new MutationObserver(()=>{const node=document.querySelector('.agent-v2-chat-answer[data-streaming=true]');if(node){const length=node.querySelector('.agent-v2-reply')?.textContent.length||0,last=window.__renders.at(-1);if(length&&length!==last?.length)window.__renders.push({at:performance.now(),length});}}).observe(document.body,{childList:true,subtree:true,characterData:true}));
 });
 const check=async(name,fn)=>{const start=Date.now();await fn();const result={name,passed:true,seconds:(Date.now()-start)/1000};report.checks.push(result);fs.writeFileSync(out+'/assistant-progress.json',JSON.stringify(report,null,2));console.log(JSON.stringify(result));};
 const message=()=>page.getByRole('textbox',{name:'Message Aegis Agent'});
 const send=async(text)=>{await message().fill(text);await page.getByRole('button',{name:'Send agent request',exact:true}).click();};
 const finished=async()=>{await expect(page.getByRole('button',{name:'Stop answer',exact:true})).toBeHidden({timeout:300000});await expect(page.locator('.agent-v2-working')).toBeHidden({timeout:300000});const error=await page.locator('.agent-v2-error').allTextContents();if(error.length)throw Error('Assistant error: '+error.join(' '));};
 try{
  await page.goto(base);await page.waitForLoadState('networkidle');await page.locator('#login-username').fill(auth.username);await page.locator('#login-password').fill(auth.password);await page.getByRole('button',{name:'Sign in',exact:true}).click();await expect(page.getByRole('heading',{name:'Home',exact:true})).toBeVisible();await page.goto(base+'/#Aegis%20Assistant');await expect(message()).toBeVisible();await page.waitForFunction(()=>document.querySelector('[aria-label="Agent Model"]')?.options.length>1);
  await check('Conversation and composer fit desktop, short viewport and mobile',async()=>{
   for(const viewport of [{width:938,height:668},{width:1280,height:900},{width:390,height:844},{width:938,height:500}]){
    await page.setViewportSize(viewport);const layout=await page.evaluate(()=>{const rect=selector=>{const r=document.querySelector(selector).getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,bottom:r.bottom};};return {viewport:{width:innerWidth,height:innerHeight},thread:rect('.agent-v2-thread'),composer:rect('.agent-v2-composer'),box:rect('.agent-v2-compose-box'),body_scroll:document.documentElement.scrollHeight-innerHeight,body_width:document.documentElement.scrollWidth-innerWidth,font:getComputedStyle(document.querySelector('.agent-v2-input textarea')).fontSize,shell:document.querySelector('.shell').className,shell_display:getComputedStyle(document.querySelector('.shell')).display,topbar_height:rect('.topbar').height};});report.layouts.push(layout);
    if(!baseline){expect(layout.body_scroll).toBeLessThanOrEqual(1);expect(layout.body_width).toBeLessThanOrEqual(1);expect(layout.composer.bottom).toBeLessThanOrEqual(viewport.height);expect(layout.font).toBe('16px');expect(layout.thread.height).toBeGreaterThan(viewport.height<600?120:200);}
    await page.screenshot({path:out+'/assistant-'+(baseline?'before-':'')+viewport.width+'x'+viewport.height+'.png'});
   }
  });
  if(!baseline&&!uiOnly){
   await page.setViewportSize({width:938,height:668});await page.getByRole('button',{name:'New agent conversation'}).click();await page.getByRole('combobox',{name:'Agent dataset',exact:true}).selectOption('');
   const catalog=await (await page.request.get(base+'/api/agent-v2/catalog')).json(),model=catalog.models.find(m=>m.name.startsWith('All screens QA chat'));
   if(!model)throw Error('Actual Qwen chat registration unavailable');await page.getByRole('combobox',{name:'Agent Model',exact:true}).selectOption(model.id);
   await check('Actual model answer streams into the UI before completion',async()=>{
    await send('Explain how Kubernetes deployments work in eight separate short paragraphs, around 260 words. Include rolling updates and health checks.');
    await page.waitForFunction(()=>window.__renders.length>=3||document.querySelector('.agent-v2-error'),{},{timeout:300000});if(await page.locator('.agent-v2-error').count())await finished();await page.screenshot({path:out+'/assistant-streaming.png'});await finished();
    const evidence=await page.evaluate(()=>({stream:window.__streams[0],renders:window.__renders})),deltas=evidence.stream.events.filter(e=>e.type==='delta'),done=evidence.stream.events.find(e=>e.type==='done');expect(deltas.length).toBeGreaterThan(5);expect(evidence.renders.length).toBeGreaterThan(2);expect(done.status).toBe('completed');expect(evidence.renders[0].at).toBeLessThan(done.at);
    report.streams.push({name:'general answer',headers_seconds:(evidence.stream.headers_at-evidence.stream.start)/1000,first_token_seconds:(deltas[0].at-evidence.stream.start)/1000,total_seconds:(done.at-evidence.stream.start)/1000,delta_events:deltas.length,visible_updates:evidence.renders.length,final_characters:done.length});await page.screenshot({path:out+'/assistant-completed.png'});
   });
   await check('Reading earlier content does not jump; latest button and Stop retain partial text',async()=>{
    const before=await page.evaluate(()=>window.__renders.length);await send('Describe Kubernetes services and networking in eight separate paragraphs, around 300 words.');
    await page.waitForFunction(n=>window.__renders.length>n+3,before,{timeout:300000});
    await page.locator('.agent-v2-thread').evaluate(node=>{node.scrollTop=0;node.dispatchEvent(new Event('scroll'));});const rendered=await page.evaluate(()=>window.__renders.length);
    await page.waitForFunction(n=>window.__renders.length>n+4,rendered,{timeout:300000});expect(await page.locator('.agent-v2-thread').evaluate(node=>node.scrollTop)).toBeLessThanOrEqual(1);await expect(page.getByRole('button',{name:'Scroll to latest message'})).toBeVisible();await page.getByRole('button',{name:'Scroll to latest message'}).click();
    expect(await page.locator('.agent-v2-thread').evaluate(node=>node.scrollHeight-node.scrollTop-node.clientHeight)).toBeLessThan(2);await page.getByRole('button',{name:'Stop answer'}).click();await expect(page.getByRole('button',{name:'Send agent request'})).toBeVisible();await expect(page.getByText('Stopped · partial answer kept',{exact:true})).toBeVisible();expect((await page.locator('.agent-v2-chat-answer').last().innerText()).length).toBeGreaterThan(50);
    const stoppedId=await page.evaluate(()=>sessionStorage.getItem('aegis-agent-v2:AccountUiAdmin'));
    await expect.poll(async()=>((await (await page.request.get(base+'/api/agent-v2/plans/'+stoppedId)).json()).chat||{}).status,{timeout:30000}).toBe('aborted');
    const saved=await (await page.request.get(base+'/api/agent-v2/plans/'+stoppedId)).json();expect(saved.chat.text.length).toBeGreaterThan(50);expect(saved.chat.error).toBeUndefined();
    await page.screenshot({path:out+'/assistant-stopped.png'});
   });
   await check('Next turn succeeds and completed history survives refresh',async()=>{
    await send('In one sentence, what is a Kubernetes pod?');await finished();expect((await page.locator('.agent-v2-chat-answer').last().innerText()).toLowerCase()).toContain('pod');await page.reload();await expect(message()).toBeVisible();await expect(page.locator('.agent-v2-chat-answer').last()).toContainText('pod',{ignoreCase:true});
   });
   const dataset=catalog.datasets.find(d=>d.name.startsWith('All screens QA '));if(!dataset)throw Error('Isolated document QA dataset unavailable');
   await check('Document answer retains source citations',async()=>{
    await page.getByRole('button',{name:'New agent conversation'}).click();await page.getByRole('combobox',{name:'Agent dataset'}).selectOption(dataset.id);await send('Read the original invoice document and tell me its invoice number and total. Cite the original document source.');await finished();await expect(page.locator('.agent-v2-sources').last()).toBeVisible();await expect(page.getByRole('button',{name:/Open citation/}).first()).toBeVisible();await page.screenshot({path:out+'/assistant-citations.png'});
   });
   await check('Submitted file leaves composer; proposed upload still requires confirmation',async()=>{
    await page.getByRole('button',{name:'New agent conversation'}).click();const before=await (await page.request.get(base+'/api/jobs')).json();await page.locator('.agent-v2 input[type=file]').setInputFiles({name:'stream-upload-qa.txt',mimeType:'text/plain',buffer:Buffer.from('Fictional invoice total 42.')});await send('Upload the attached file to this dataset only; do not extract it.');await finished();await expect(page.getByRole('button',{name:'Confirm upload',exact:true})).toBeVisible();await expect(page.locator('.agent-v2-files')).toBeHidden();await expect(page.locator('.agent-v2-submitted-file')).toContainText('stream-upload-qa.txt');expect((await (await page.request.get(base+'/api/jobs')).json()).length).toBe(before.length);await page.screenshot({path:out+'/assistant-upload-proposal.png'});
   });
  }
  if(uiOnly){
   await check('Provider failure offers retry and restores the original attached file into the draft',async()=>{
    const catalog=await (await page.request.get(base+'/api/agent-v2/catalog')).json(),model=catalog.models.find(m=>m.name.startsWith('All screens QA chat')),dataset=catalog.datasets.find(d=>d.name.startsWith('All screens QA '));
    if(!model||!dataset)throw Error('Isolated QA model and dataset required');
    await page.setViewportSize({width:938,height:668});await page.getByRole('button',{name:'New agent conversation'}).click();await page.getByRole('combobox',{name:'Agent dataset'}).selectOption(dataset.id);await page.getByRole('combobox',{name:'Agent Model'}).selectOption(model.id);
    // Deliberately fail the response transport. Real model tests run separately.
    await page.route('**/api/agent-v2/plans/*/reply',route=>route.fulfill({status:502,contentType:'application/json',body:JSON.stringify({detail:'Synthetic QA model connection failure'})}));
    await page.locator('.agent-v2 input[type=file]').setInputFiles({name:'retry-stream-qa.txt',mimeType:'text/plain',buffer:Buffer.from('Retain these fictional source bytes.')});await send('Upload this file.');await expect(page.getByRole('button',{name:'Retry request',exact:true})).toBeVisible();await expect(page.locator('.agent-v2-files')).toBeHidden();await expect(page.locator('.agent-v2-submitted-file')).toContainText('retry-stream-qa.txt');
    await page.getByRole('button',{name:'Retry request',exact:true}).click();await expect(message()).toHaveValue('Upload this file.');await expect(page.locator('.agent-v2-files')).toContainText('retry-stream-qa.txt');
    await page.setViewportSize({width:390,height:844});expect((await page.locator('.agent-v2-composer').boundingBox()).y+(await page.locator('.agent-v2-composer').boundingBox()).height).toBeLessThan(844);await page.screenshot({path:out+'/assistant-retry.png'});await page.unroute('**/api/agent-v2/plans/*/reply');
   });
  }
  if(report.page_errors.length)throw Error('Browser JavaScript errors');report.passed=true;
 }catch(error){report.passed=false;report.error=String(error.message).slice(0,700);await page.screenshot({path:out+'/assistant-failure.png'}).catch(()=>{});throw error;}
 finally{report.finished_at=new Date().toISOString();report.stream_timings=await page.evaluate(()=>window.__streams.map((s,index)=>{const first=s.events.find(e=>e.type==='delta'&&e.length),done=s.events.find(e=>e.type==='done');return {turn:index+1,first_token_seconds:first?(first.at-s.start)/1000:null,total_seconds:done?(done.at-s.start)/1000:null,deltas:s.events.filter(e=>e.type==='delta'&&e.length).length,status:done?.status||s.error||'unfinished'};})).catch(()=>[]);fs.writeFileSync(out+'/assistant-'+(baseline?'baseline':uiOnly?'ui':'stream')+'.json',JSON.stringify(report,null,2));await browser.close();}
})().catch(error=>{console.error(String(error.message).slice(0,700));process.exit(1);});
