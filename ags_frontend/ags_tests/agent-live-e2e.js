// Opt-in real browser test. Fictional fixtures only. Credentials enter on stdin.
// Builds: docker build -f ags_deploy/ags_docker/Dockerfile.agent-browser -t aegis-agent-browser .
const {chromium, expect} = require('@playwright/test');
const fs = require('node:fs');
(async()=>{
 let auth;try{auth=JSON.parse(fs.readFileSync(0,'utf8'));}catch{throw new Error('Test credentials are not valid JSON.');}
 const browser=await chromium.launch({executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,args:['--no-sandbox','--disable-dev-shm-usage','--unsafely-treat-insecure-origin-as-secure=http://web:3000']});
 const page=await browser.newPage({viewport:{width:1280,height:850}});
 page.setDefaultTimeout(30000);
 const report={steps:[],errors:[]};
 const out=process.env.AEGIS_TEST_OUTPUT||'/results';fs.mkdirSync(out,{recursive:true});
 page.on('pageerror',e=>report.errors.push(e.message));
 let lastPlan;
 page.on('response',async response=>{
  if(response.url().endsWith('/api/agent-v2/plans')&&response.request().method()==='POST'){
   try {lastPlan={status:response.status(),...await response.json()};}catch{}
  }
 });
 const checkpoint=async(name,start)=>{report.steps.push({name,seconds:Math.round((Date.now()-start)/10)/100});fs.writeFileSync(out+'/agent-live-e2e.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report.steps.at(-1)));};
 const send=async(text)=>{
  lastPlan=undefined;const start=Date.now();await page.getByRole('textbox',{name:'Message Aegis Agent'}).fill(text);
  const wait=page.waitForResponse(r=>r.url().endsWith('/api/agent-v2/plans')&&r.request().method()==='POST',{timeout:300000});
  await page.getByRole('button',{name:'Send agent request',exact:true}).click();
  const response=await wait;const data=await response.json();
  if(response.status()!==200)throw Error('Agent request failed: '+JSON.stringify(data));
  await checkpoint('agent request: '+text,start);return data;
 };
 try{
  let start=Date.now();await page.goto(process.env.AEGIS_TEST_URL||'http://web:3000/');
  await page.locator('#login-username').fill(auth.username);await page.locator('#login-password').fill(auth.password);
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.getByRole('button',{name:'Aegis Agent',exact:true}).click();
  await page.getByLabel('Agent dataset',{exact:true}).selectOption(auth.dataset_id);
  await page.getByLabel('Agent Model',{exact:true}).selectOption(auth.model_id);
  await checkpoint('login and mapped dataset',start);
  if(process.env.AEGIS_TEST_KNOWLEDGE_REVIEW==='true'){
   let plan;
   if(!process.env.AEGIS_TEST_EXISTING_PLAN){
   await page.locator('input[type=file]').last().setInputFiles('/fixtures/sample_resume.json');
   await page.getByRole('button',{name:'Prompt template',exact:true}).click();
   await page.getByRole('button',{name:'Confirm prompt',exact:true}).click();
   await page.locator('input[type=file]').last().setInputFiles(['/fixtures/ags_resumes/04-sara-khan-frontend.pdf','/fixtures/ags_resumes/05-dev-patel-qa.pdf']);
   plan=await send('Extract these two attached resumes using the attached prompt.');
   if(plan.calls.map(c=>c.tool).join(',')!=='upload,extract')throw Error('Mixed prompt/documents did not prepare extraction.');
   await page.getByLabel('Extraction mode',{exact:true}).selectOption('merge');
   await page.getByLabel('Merged content',{exact:true}).selectOption('records');
   start=Date.now();await page.getByRole('button',{name:'Confirm upload and extraction',exact:true}).click();
   await page.getByRole('button',{name:/Review result and evidence/}).last().waitFor({timeout:900000});
   await checkpoint('two additional profiles uploaded and extracted',start);
   }else plan={id:process.env.AEGIS_TEST_EXISTING_PLAN};
   const updated=await (await page.request.get(new URL('/api/agent-v2/plans/'+plan.id,page.url()).href)).json();
   const result=updated.calls.find(c=>c.tool==='extract').result;
   report.extraction_id=result.extraction_id||result.extractions?.[0]?.extraction_id;
   if(!report.extraction_id)throw Error('No completed extraction ID.');
   const saved=await (await page.request.get(new URL('/api/extractions/'+report.extraction_id,page.url()).href)).json();
   const expected=JSON.parse(fs.readFileSync('/fixtures/expected-results.json','utf8')).cases;
   for(const r of saved.result.records){const truth=expected.find(c=>c.expected_result.full_name===r.fields.full_name);if(!truth||!require('node:util').isDeepStrictEqual(truth.expected_result,r.fields))throw Error('Saved fields differ from known fixture '+r.fields.full_name);}
   report.exact_fields_passed=true;
   for(const question of ['can you bring profiles who is skilled in python?','who is expert in react','can you bring me summarized on profiles','only three profiles are there?']){
    const answer=await send(question);report.answers=report.answers||[];report.answers.push({question,text:answer.explanation});
    if(answer.calls.length)throw Error('A question proposed new extraction.');
    const conversation=await (await page.request.get(new URL('/api/conversations/'+answer.conversation_id,page.url()).href)).json();
    const message=conversation.messages.filter(m=>m.role==='assistant').at(-1);
    if(!message.citations?.length||message.citations.some(c=>c.kind!=='extraction'||!c.extraction_id||!c.version))throw Error('Saved-result answer lacks versioned extraction citations.');
    report.answers.at(-1).citation_count=message.citations.length;

    if(!/\[\d+\]/.test(answer.explanation))throw Error('Answer lacks numbered source references.');
    if(question.includes('summarized'))for(const name of ['Arjun','Meera','Nikhil','Sara','Dev'])if(!answer.explanation.includes(name))throw Error('Summary missed '+name);
    if(question.includes('summarized')&&/from verified documents|complete contact information/i.test(answer.explanation))throw Error('Summary claimed unsupported verification/completeness.');
    for(const c of message.citations)if(!answer.explanation.includes(c.extraction_id))throw Error('Answer omitted a cited extraction ID.');
    if(question.includes('three')&&!/There are 5 saved profiles/i.test(answer.explanation))throw Error('Count did not reflect all five saved profiles.');
    if(question.includes('python')&&(!/Arjun/.test(answer.explanation)||!/Nikhil/.test(answer.explanation)||!/Dev/.test(answer.explanation)))throw Error('Python filter missed matching profiles.');
    if(question.includes('python')&&/Sara|Meera/.test(answer.explanation))throw Error('Python filter included a non-match.');
    if(question.includes('react')&&(!/Sara/.test(answer.explanation)||/Dev Patel|Arjun Rao|Nikhil Shah|Meera Iyer/.test(answer.explanation)))throw Error('React filter included wrong profiles.');
    await expect(page.getByRole('button',{name:/Open citation \d+/}).last()).toBeVisible();
   }
   // Use a source citation to open the result, then locate an exact extraction ID.
   await page.getByRole('button',{name:/Open citation \d+/}).last().click();
   await expect(page.getByLabel('Review dataset filter',{exact:true})).toHaveValue(auth.dataset_id);
   await page.getByLabel('Search extraction ID or filename').fill(report.extraction_id);
   await expect(page.locator('.extraction-directory-results')).toContainText('2 profiles / items');
   await page.getByRole('button',{name:'Open extraction '+report.extraction_id,exact:true}).click();
   await expect(page.getByRole('region',{name:'Review extraction',exact:true})).toContainText(report.extraction_id);
   await expect(page.locator('.review-identity')).toContainText('LangGraph final browser QA');
   await page.getByLabel('Review profile',{exact:true}).selectOption('0');
   const nameField=page.locator('.review-values input[aria-label$="/fields/full_name"]');
   await expect(nameField).toHaveCount(1);await expect(nameField).toHaveValue('Sara Khan');
   await nameField.fill('Unsaved QA edit');
   page.once('dialog',dialog=>dialog.dismiss());
   await page.getByLabel('Review dataset filter').selectOption('');
   await expect(page.getByLabel('Review dataset filter')).toHaveValue(auth.dataset_id);
   await expect(nameField).toHaveValue('Unsaved QA edit');
   await page.getByRole('button',{name:'Cancel',exact:true}).click();
   await page.getByLabel('Review profile').selectOption('all');
   const frame=page.locator('.review-source iframe');
   const src=await frame.getAttribute('src');
   const source=await page.request.get(new URL(src,page.url()).href);
   const bytes=await source.body();
   if(source.status()!==200||!source.headers()['content-type']?.includes('application/pdf')||bytes.subarray(0,5).toString()!=='%PDF-')throw Error('Original source PDF failed HTTP/content validation.');
   report.source_pdf_http_passed=true;
   await page.screenshot({path:out+'/extraction-review-desktop.png',fullPage:true});
   await page.setViewportSize({width:390,height:844});
   await page.screenshot({path:out+'/extraction-review-mobile.png',fullPage:true});
   report.review_passed=true;report.passed=true;console.log(JSON.stringify({passed:true,extraction_id:report.extraction_id,answers:report.answers}));return;
  }
  if(process.env.AEGIS_TEST_PROMPT_ONLY==='true'){
   await page.locator('input[type=file]').last().setInputFiles({name:'prompt-only-upload.json',mimeType:'application/json',buffer:fs.readFileSync('/fixtures/sample_resume.json')});
   await page.getByRole('button',{name:'Prompt template',exact:true}).click();
   await page.getByRole('button',{name:'Confirm prompt',exact:true}).click();
   const plan=await send('can you upload it');
   report.prompt_acknowledgement=plan.explanation;report.model_calls=plan.model_calls;
   if(plan.phase!=='answered'||plan.calls.length||plan.model_calls>2)throw Error('Prompt-only upload looped or started a document workflow.');
   if(!plan.explanation.includes('prompt-only-upload.json')||!plan.explanation.includes('version'))throw Error('Missing verified prompt filename/version.');
   await expect(page.locator('.agent-v2-composer [aria-label="Attached files"]')).toHaveCount(0);
   await expect(page.locator('.agent-v2-thread')).toContainText('prompt-only-upload.json');
   await page.screenshot({path:out+'/prompt-only-confirmed.png',fullPage:true});
   await page.getByRole('button',{name:'Prompt templates',exact:true}).click();
   await expect(page.locator('main')).toContainText('prompt-only-upload.json');
   report.passed=true;console.log(JSON.stringify({passed:true,prompt_acknowledgement:plan.explanation,model_calls:plan.model_calls}));return;
  }
  if(process.env.AEGIS_TEST_SUMMARY_ONLY==='true'){
   const plan=await send('If these were already extracted, summarize each profile using the saved fields. Do not extract again.');
   report.summary=plan.explanation;report.conversation_id=plan.conversation_id;
   if(plan.calls.length)throw Error('Conditional summary reran extraction.');
   for(const name of ['Arjun','Meera','Nikhil'])if(!plan.explanation.includes(name))throw Error('Summary missed '+name);
   await expect(page.getByRole('button',{name:/Review result/}).last()).toBeVisible();
   await page.screenshot({path:out+'/saved-result-summary.png',fullPage:true});
   await page.getByRole('button',{name:/Review result/}).last().click();
   await expect(page.getByRole('region',{name:'Review extraction',exact:true})).toBeVisible();
   report.passed=true;console.log(JSON.stringify({passed:true,summary:report.summary}));return;
  }
  if(process.env.AEGIS_TEST_DOCUMENT_ONLY==='true'){
   const plan=await send('Search the original uploaded resumes: which candidate has Kubernetes experience? Cite the document passage.');
   report.document_answer=plan.explanation;
   if(!/Meera/i.test(plan.explanation)||!/[\[]\d+[\]]/.test(plan.explanation))throw Error('Document answer missed candidate or citation.');
   await expect(page.locator('.agent-v2-thread')).toContainText('Sources');
   await page.screenshot({path:out+'/document-search.png',fullPage:true});
   report.passed=true;console.log(JSON.stringify({passed:true,document_answer:report.document_answer}));return;
  }
  // Malformed JSON must stay unsaved and show a validation error.
  await page.locator('input[type=file]').last().setInputFiles({name:'invalid.json',mimeType:'application/json',buffer:Buffer.from('{bad json')});
  await page.getByRole('button',{name:'Prompt template',exact:true}).click();
  await expect(page.locator('.agent-v2-attachment-error')).toBeVisible();
  await page.getByRole('button',{name:'Remove attachment invalid.json',exact:true}).click();
  report.steps.push({name:'invalid JSON rejected',passed:true});
  await page.locator('input[type=file]').last().setInputFiles('/fixtures/sample_resume.json');
  await page.getByRole('button',{name:'Prompt template',exact:true}).click();
  await page.getByRole('button',{name:'Confirm prompt',exact:true}).click();
  let plan=await send('Update this prompt for my selected dataset.');
  report.prompt_acknowledgement=plan.explanation;
  if(/(?:you(?:'ll)? need to|rename|_v2\.json|upload it)/i.test(plan.explanation))throw Error('Agent contradicted the successful prompt-save receipt.');
  if(plan.calls.length)throw Error('Saved prompt was incorrectly proposed as document workflow.');
  await expect(page.locator('.agent-v2-thread')).toContainText('sample_resume.json',{timeout:30000});
  // Uploaded prompt is discoverable in the separate template screen.
  await page.getByRole('button',{name:'Prompt templates',exact:true}).click();
  await expect(page.locator('main')).toContainText('sample_resume.json');
  await page.getByRole('button',{name:'Aegis Agent',exact:true}).click();
  await page.getByLabel('Agent dataset',{exact:true}).selectOption(auth.dataset_id);
  start=Date.now();await page.locator('input[type=file]').last().setInputFiles([
   '/fixtures/ags_resumes/01-arjun-rao-backend.pdf','/fixtures/ags_resumes/02-meera-iyer-devops.pdf','/fixtures/ags_resumes/03-nikhil-shah-data.pdf']);
  plan=await send('Extract all three attached resumes using the saved prompt.');
  report.plan_id=plan.id;report.conversation_id=plan.conversation_id;report.runtime=plan.runtime;report.model_calls=plan.model_calls;
  if(plan.runtime!=='langgraph'||plan.calls.map(c=>c.tool).join(',')!=='upload,extract')throw Error('Wrong workflow proposal.');
  await expect(page.locator('.agent-v2-composer [aria-label="Attached files"]')).toHaveCount(0);
  await expect(page.locator('.agent-v2-thread')).toContainText('01-arjun-rao-backend.pdf');
  report.steps.push({name:'attachments moved to submitted question',passed:true});
  await page.getByLabel('Extraction mode',{exact:true}).selectOption('merge');
  await page.getByLabel('Merged content',{exact:true}).selectOption('records');
  await page.getByRole('button',{name:'Confirm upload and extraction',exact:true}).click();
  await page.getByRole('button',{name:/Review result and evidence/}).first().waitFor({timeout:900000});
  await checkpoint('three-file upload, indexing and merged extraction',start);
  await page.screenshot({path:out+'/agent-completed.png',fullPage:true});
  await page.getByRole('button',{name:/Review result and evidence/}).first().click();
  await expect(page.getByText('Review extraction',{exact:true})).toBeVisible();
  await expect(page.locator('main')).toContainText('Arjun Rao');
  await expect(page.locator('main')).toContainText('Meera Iyer');
  await expect(page.locator('main')).toContainText('Nikhil Shah');
  await page.screenshot({path:out+'/merged-review.png',fullPage:true});
  report.steps.push({name:'review displays all three profiles',passed:true});
  await page.getByRole('button',{name:'Aegis Agent',exact:true}).click();
  plan=await send('If these were already extracted, summarize each profile using the saved fields. Do not extract again.');
  if(plan.calls.length)throw Error('Conditional summary incorrectly reruns extraction.');
  report.summary=plan.explanation;
  for(const name of ['Arjun','Meera','Nikhil'])if(!plan.explanation.includes(name))throw Error('Summary missed '+name);
  await expect(page.getByRole('button',{name:/Review result/}).last()).toBeVisible();
  await page.screenshot({path:out+'/saved-result-summary.png',fullPage:true});
  plan=await send('Search the original uploaded resumes: which candidate has Kubernetes experience? Cite the document passage.');
  report.document_answer=plan.explanation;
  if(!/Meera/i.test(plan.explanation)||!/[\[]\d+[\]]/.test(plan.explanation))throw Error('Document answer missed the candidate or citation.');
  await expect(page.locator('.agent-v2-thread')).toContainText('Sources');
  await page.screenshot({path:out+'/document-search.png',fullPage:true});
  report.passed=true;console.log(JSON.stringify({passed:true,steps:report.steps,summary:report.summary,document_answer:report.document_answer}));
 }catch(error){report.passed=false;report.failure=error.message;report.last_plan=lastPlan;await page.screenshot({path:out+'/failure.png',fullPage:true}).catch(()=>{});console.log(JSON.stringify({passed:false,failure:report.failure,last_plan:lastPlan}));process.exitCode=1;}
 finally{fs.writeFileSync(out+'/agent-live-e2e.json',JSON.stringify(report,null,2));await browser.close();}
})();
