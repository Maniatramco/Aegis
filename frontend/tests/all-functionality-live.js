// Real Docker/Oracle/Ollama browser acceptance. No substituted application responses.
const {chromium,expect}=require('@playwright/test');
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
(async()=>{
 let auth;try{auth=JSON.parse(fs.readFileSync(0,'utf8'));}catch{throw Error('Invalid QA credential input.');}
 const out='/results',phase=process.env.AEGIS_ALL_PHASE||'setup';fs.mkdirSync(out,{recursive:true});
 const stateFile=out+'/state.json',reportFile=out+'/live-'+phase+'.json';
 const state=fs.existsSync(stateFile)?JSON.parse(fs.readFileSync(stateFile,'utf8')):{suffix:String(Date.now()),models:{},screens:[]};
 const report={phase,steps:[],errors:[],started_at:new Date().toISOString()};
 const browser=await chromium.launch({executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,args:['--no-sandbox','--disable-dev-shm-usage','--unsafely-treat-insecure-origin-as-secure=http://web:3000']});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});page.setDefaultTimeout(30000);
 page.on('pageerror',e=>report.errors.push(e.message));
 const persist=()=>{fs.writeFileSync(stateFile,JSON.stringify(state,null,2));fs.writeFileSync(reportFile,JSON.stringify(report,null,2));};
 const step=async(name,fn)=>{const start=Date.now();console.log(JSON.stringify({starting:name}));try{await fn();report.steps.push({name,passed:true,seconds:Math.round((Date.now()-start)/10)/100});}catch(e){report.steps.push({name,passed:false,seconds:Math.round((Date.now()-start)/10)/100,error:e.message});throw e;}finally{persist();console.log(JSON.stringify(report.steps.at(-1)));}};
 const url=p=>new URL('/api'+p,page.url()).href;
 const checked=async response=>{if(!response.ok())throw Error('HTTP '+response.status()+' from '+new URL(response.url()).pathname+': '+(await response.text()).slice(0,500));return response.json();};
 const get=p=>page.request.get(url(p)).then(checked);
 const write=async(p,data,method='post')=>{const me=await get('/auth/me');return checked(await page.request[method](url(p),{headers:{'X-CSRF-Token':me.csrf_token},data}));};
 const nav=async(name)=>{const n=page.getByRole('navigation');const b=n.getByRole('button',{name,exact:true});if(!await b.isVisible())await n.getByRole('button',{name:'Manage workspace',exact:true}).click();await b.click();await expect(page.locator('main h1').first()).toBeVisible();};
 const refresh=async()=>{await page.getByLabel('Refresh workspace',{exact:true}).click();await expect(page.getByLabel('Refresh workspace',{exact:true})).toBeEnabled();};
 const responseTo=async(method,end,action,timeout=120000)=>{const wait=page.waitForResponse(r=>new URL(r.url()).pathname===end&&r.request().method()===method,{timeout});await action();return checked(await wait);};
 const waitEx=async id=>{let current;await expect.poll(async()=>{current=await get('/extractions/'+id);if(['failed','cancelled'].includes(current.status))throw Error('Extraction '+current.status+': '+(current.error||'Inspect its job.'));return current.status;},{timeout:900000,intervals:[2000,4000]}).toBe('ready');return current;};
 const fixture=(name,text)=>({name,mimeType:'text/plain',buffer:Buffer.from(text)});
 const fileA=()=>fixture('all-qa-invoice-a.txt','Fictional invoice. Invoice reference INV-A-42. Total including tax: 42 USD. Supplier: Example Test Supplies.');
 const fileB=()=>fixture('all-qa-invoice-b.txt','Fictional invoice. Invoice reference INV-B-75. Total including tax: 75 USD. Supplier: Example Test Supplies.');
 const prompt=()=>({name:'all-qa-invoice.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({name:'Ignored internal name',schema:{type:'object',description:'Extract invoice reference and total. Copy values; do not guess.',properties:{reference:{type:'string',description:'Invoice reference'},total:{type:'number',description:'Total including tax in USD'}},required:['reference','total'],additionalProperties:false}}))});
 const send=async text=>{const started=Date.now();const plan=await responseTo('POST','/api/agent-v2/plans',async()=>{await page.getByRole('textbox',{name:'Message Aegis Agent'}).fill(text);await page.getByRole('button',{name:'Send agent request',exact:true}).click();},300000);(report.planning_requests??=[]).push({plan_id:plan.id,seconds:Math.round((Date.now()-started)/10)/100});persist();return plan;};
 try{
  await step('Real login and session',async()=>{await page.goto('http://web:3000/');await page.locator('#login-username').fill(auth.username);await page.locator('#login-password').fill(auth.password);await responseTo('POST','/api/auth/login',()=>page.getByRole('button',{name:'Sign in',exact:true}).click());await expect(page.getByRole('navigation')).toBeVisible();await get('/auth/me');});
  if(phase==='setup'){
   await step('Register/test local Chat, Extraction and Embedding models',async()=>{
    await nav('Model Registration');
    for(const category of ['chat','extraction','embedding']){
     if(state.models[category])continue;
     await page.getByRole('button',{name:'Register model',exact:true}).click();
     await page.locator('#registration-name').fill('All screens QA '+category+' '+state.suffix);
     await page.locator('#registration-category').selectOption(category);
     await page.locator('#registration-model').fill(category==='embedding'?'nomic-embed-text':'qwen3:4b');
     await page.locator('#registration-endpoint').fill(process.env.AEGIS_TEST_MODEL_URL||'http://ollama:11434');
     await page.locator('#registration-timeout').fill('1200');
     await page.locator('#registration-context-limit').fill('8192');
     if(category!=='embedding')await page.locator('#registration-output-limit').fill('2048');
     const tested=await responseTo('POST','/api/model-registrations/test',()=>page.getByRole('button',{name:'Test Connection',exact:true}).click(),300000);
     if(!tested.ok)throw Error('Model test did not pass.');
     state.models[category]=await responseTo('POST','/api/model-registrations',()=>page.getByRole('button',{name:'Save Model',exact:true}).click());persist();
     await expect(page.getByRole('button',{name:'Register model',exact:true})).toBeVisible();
    }
    await page.getByLabel('Search registered models').fill(state.suffix);await expect(page.locator('.registration-row')).toHaveCount(3);
   });
   await step('Create dataset, preserve mapping draft through refresh, save mappings',async()=>{
    if(!state.dataset){await nav('Datasets');await page.getByRole('button',{name:'New dataset',exact:true}).first().click();await page.getByLabel('Dataset name',{exact:true}).fill('All screens QA '+state.suffix);await page.getByLabel('Dataset description',{exact:true}).fill('Fictional end-to-end acceptance data.');state.dataset=await responseTo('POST','/api/datasets',()=>page.getByRole('button',{name:'Create dataset',exact:true}).click());persist();}
    await nav('Model Mapping');await page.locator('#mapping-dataset').selectOption(state.dataset.id);
    await page.getByLabel('Chat model',{exact:true}).selectOption(state.models.chat.id);
    await page.getByLabel('Extraction model',{exact:true}).selectOption(state.models.extraction.id);
    await page.getByLabel('Embedding model',{exact:true}).selectOption(state.models.embedding.id);
    await refresh();await expect(page.getByLabel('Chat model',{exact:true})).toHaveValue(state.models.chat.id);
    await responseTo('PUT','/api/datasets/'+state.dataset.id+'/models',()=>page.getByRole('button',{name:'Save & Apply',exact:true}).click());
    const d=await get('/datasets/'+state.dataset.id+'/models');if(d.default_chat_model_id!==state.models.chat.id||d.default_extraction_model_id!==state.models.extraction.id||d.embedding_model_id!==state.models.embedding.id)throw Error('Saved mapping mismatch.');
   });
   await step('Home dataset search and navigation; dataset upload TXT, DOCX and PDF',async()=>{
    await nav('Home');await page.getByRole('button',{name:'Search datasets',exact:true}).click();await page.getByLabel('Search datasets').fill(state.suffix);await page.getByRole('link',{name:'Open dataset '+state.dataset.name,exact:true}).click();
    await expect(page.getByRole('button',{name:'Add documents',exact:true})).toBeEnabled();await page.getByRole('button',{name:'Add documents',exact:true}).click();
    await page.getByLabel('Choose documents',{exact:true}).setInputFiles([fileA(),{name:'all-qa-invoice-docx.docx',mimeType:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',buffer:fs.readFileSync('/fixtures/all-qa-invoice-docx.docx')},{name:'all-qa-arjun.pdf',mimeType:'application/pdf',buffer:fs.readFileSync('/fixtures/resumes/01-arjun-rao-backend.pdf')}]);
    const uploaded=await responseTo('POST','/api/documents/upload',()=>page.getByRole('button',{name:'Upload 3',exact:true}).click());state.documents=uploaded.documents;persist();
    for(const doc of state.documents){await expect.poll(async()=>{const d=await get('/documents/'+doc.id);if(d.status==='failed')throw Error(d.error);return d.status;},{timeout:300000,intervals:[2000,4000]}).toBe('ready');}
    await refresh();const row=page.getByRole('row').filter({hasText:'all-qa-invoice-a.txt'});await expect(row).toContainText('ready');await row.getByTitle('Preview document').click();await expect(page.getByRole('dialog')).toContainText('INV-A-42');await page.getByRole('button',{name:'Close preview',exact:true}).click();
   });
  }
  if(phase==='workflows'||phase==='review'){
   if(phase==='workflows'){
   await step('Malformed prompt validation, valid save, filename identity and update receipt',async()=>{
    await nav('Aegis Agent');await page.getByLabel('Agent dataset',{exact:true}).selectOption(state.dataset.id);await page.getByLabel('Agent Model',{exact:true}).selectOption(state.models.chat.id);
    await page.locator('input[type=file]').last().setInputFiles({name:'bad-qa.json',mimeType:'application/json',buffer:Buffer.from('{"schema":')});
    await page.getByRole('button',{name:'Prompt template',exact:true}).click();await expect(page.locator('.agent-v2-attachment-error')).toContainText(/JSON|invalid|unexpected|line/i);await expect(page.getByRole('button',{name:'Confirm prompt',exact:true})).toHaveCount(0);await expect(page.getByRole('button',{name:'Send agent request',exact:true})).toBeDisabled();await page.getByRole('button',{name:'Remove attachment bad-qa.json',exact:true}).click();
    await page.locator('input[type=file]').last().setInputFiles(prompt());await page.getByRole('button',{name:'Prompt template',exact:true}).click();await page.getByRole('button',{name:'Confirm prompt',exact:true}).click();
    let answer=await send('update this');if(answer.phase!=='answered'||answer.calls.length)throw Error('Prompt receipt became an extraction/upload loop.');
    let templates=await get('/templates');state.template=templates.find(t=>t.source_filename==='all-qa-invoice.json'&&t.dataset_id===state.dataset.id);if(!state.template||state.template.name!=='all-qa-invoice.json')throw Error('Template filename identity missing.');persist();
    await page.locator('input[type=file]').last().setInputFiles(prompt());await page.getByRole('button',{name:'Prompt template',exact:true}).last().click();await page.getByRole('button',{name:'Confirm prompt',exact:true}).click();answer=await send('update this');if(answer.phase!=='answered'||answer.calls.length)throw Error('Prompt update looped.');
    templates=await get('/templates');const newer=templates.find(t=>t.id===state.template.id);if(newer.version<=state.template.version)throw Error('Same filename did not version the same template.');state.template=newer;persist();
    await nav('Prompt templates');await page.getByLabel('Filter templates by dataset').selectOption(state.dataset.id);await page.getByLabel('Search prompt templates').fill('all-qa-invoice.json');await expect(page.getByRole('article',{name:'Prompt template all-qa-invoice.json',exact:true})).toContainText('Version '+state.template.version);
    await page.getByRole('article',{name:'Prompt template all-qa-invoice.json',exact:true}).getByRole('button',{name:'Versions',exact:true}).click();await expect(page.getByRole('dialog')).toContainText('Version 1');await page.getByLabel('Close template versions').click();
   });
   await step('Assistant drag/drop attachment handoff, merge choice, completed two-record extraction',async()=>{
    await nav('Aegis Agent');await page.getByLabel('Agent dataset',{exact:true}).selectOption(state.dataset.id);await page.getByLabel('Agent Model',{exact:true}).selectOption(state.models.chat.id);
    // The real DOM drop path, using two fictional TXT File objects.
    const dt=await page.evaluateHandle(()=>{const d=new DataTransfer();d.items.add(new File(['Fictional invoice. Invoice reference INV-A-42. Total including tax: 42 USD.'],'agent-invoice-a.txt',{type:'text/plain'}));d.items.add(new File(['Fictional invoice. Invoice reference INV-B-75. Total including tax: 75 USD.'],'agent-invoice-b.txt',{type:'text/plain'}));return d;});
    await page.locator('.agent-v2-composer').dispatchEvent('drop',{dataTransfer:dt});await dt.dispose();
    const plan=await send('Upload and extract these two attached invoices using all-qa-invoice.json.');state.agent_plan_id=plan.id;persist();if(plan.calls.map(c=>c.tool).join(',')!=='upload,extract')throw Error('Did not prepare the upload/extract chain.');
    await expect(page.locator('.agent-v2-composer')).not.toContainText('agent-invoice-a.txt');await expect(page.locator('.agent-v2-thread')).toContainText('agent-invoice-a.txt');
    await page.getByLabel('Workflow prompt template',{exact:true}).selectOption(state.template.id);await page.getByLabel('Extraction mode',{exact:true}).selectOption('merge');await page.getByLabel('Merged content',{exact:true}).selectOption('records');
    await page.getByRole('button',{name:'Confirm upload and extraction',exact:true}).click();await page.getByRole('button',{name:/Review result and evidence/}).last().waitFor({timeout:900000});
    const done=await get('/agent-v2/plans/'+plan.id);const result=done.calls.find(c=>c.tool==='extract').result;state.extraction_id=result.extraction_id||result.extractions?.[0]?.extraction_id;persist();
    const ex=await waitEx(state.extraction_id);const values=ex.result.records.map(r=>r.fields).sort((a,b)=>a.total-b.total);if(values.length!==2||values[0].reference!=='INV-A-42'||values[0].total!==42||values[1].reference!=='INV-B-75'||values[1].total!==75)throw Error('Combined extraction lost or changed invoice values.');state.merged_document_id=ex.document_ids[0];persist();
    await page.getByRole('button',{name:/Review result and evidence/}).last().click();await expect(page.locator('.review-identity')).toContainText(ex.id);
   });
   }else{await nav('Extraction Review');await page.getByLabel('Review dataset filter').selectOption(state.dataset.id);await page.getByLabel('Search extraction ID or filename').fill(state.extraction_id);await page.getByRole('button',{name:'Open extraction '+state.extraction_id,exact:true}).click();}
   await step('Review save/versioning, dirty guard, exports and re-extraction',async()=>{
    const ex=await get('/extractions/'+state.extraction_id);await page.getByLabel('Review profile',{exact:true}).selectOption('0');const field=page.locator('.review-values input[aria-label$="/fields/reference"]');await field.fill('INV-A-42-REVIEWED');
    await responseTo('PATCH','/api/extractions/'+ex.id,()=>page.getByRole('button',{name:'Save changes',exact:true}).click());const saved=await get('/extractions/'+ex.id);if(saved.version!==ex.version+1||saved.review_status!=='reviewed')throw Error('Review version or status missing.');
    await field.fill('UNSAVED');page.once('dialog',d=>d.dismiss());await nav('Home');await expect(page.locator('.review-identity')).toContainText(ex.id);await expect(field).toHaveValue('UNSAVED');await page.getByRole('button',{name:'Cancel',exact:true}).click();
    for(const format of ['json','csv','xlsx']){const response=await page.request.get(url('/extractions/'+ex.id+'/export?format='+format));if(!response.ok())throw Error('Export failed: '+format);const bytes=await response.body();if(format==='xlsx'&&bytes.subarray(0,2).toString()!=='PK')throw Error('Invalid Excel export.');if(format==='json'&&!JSON.parse(bytes).result)throw Error('No saved result in JSON export.');if(format==='csv'&&!bytes.toString().includes('INV-A-42-REVIEWED'))throw Error('CSV omitted saved edits.');}
    page.once('dialog',d=>d.accept());await responseTo('POST','/api/extractions/'+ex.id+'/reextract',()=>page.getByRole('button',{name:'Re-extract results',exact:true}).click());const again=await waitEx(ex.id);if(again.version!==saved.version+1||again.review_status!=='unreviewed')throw Error('Re-extraction lost version/review state.');const versions=await get('/extractions/'+ex.id+'/versions');if(versions.length<3||!versions.some(v=>JSON.stringify(v.result).includes('INV-A-42-REVIEWED')))throw Error('Saved review not retained as prior version.');await refresh();
   });
   await step('Re-extract menu starts an independent extraction and opens Review',async()=>{
    await nav('Re-extract');await page.getByLabel('Filter extraction documents by dataset').selectOption(state.dataset.id);await page.getByLabel('Search documents to extract').fill('all-qa-invoice-a.txt');
    await page.getByRole('article',{name:'Extraction document all-qa-invoice-a.txt',exact:true}).getByRole('button',{name:/Extract/,exact:false}).click();await page.getByLabel('Re-extract prompt template').selectOption(state.template.id);
    const started=await responseTo('POST','/api/extractions',()=>page.getByRole('button',{name:'Start extraction',exact:true}).click());state.independent_extraction_id=started.id;persist();const result=await waitEx(started.id);if(result.result.reference!=='INV-A-42'||result.result.total!==42)throw Error('Independent extraction mismatch.');
    await page.getByRole('button',{name:'Review results',exact:true}).waitFor({timeout:60000});await page.getByRole('button',{name:'Review results',exact:true}).click();await expect(page.locator('.review-identity')).toContainText(started.id);
   });
  }
  if(phase==='chat'||phase==='temporary'){
   if(phase==='chat'){
   await step('Document Chat retrieval, citation source, feedback, export and history',async()=>{
    await nav('Document Chat');await page.getByLabel('Chat dataset',{exact:true}).selectOption(state.dataset.id);
    const scope=page.locator('.chat-scope');if(!await scope.evaluate(el=>el.open))await scope.locator('summary').click();
    const doc=state.documents.find(d=>d.name==='all-qa-invoice-a.txt');const box=page.locator('.selection label').filter({hasText:doc.name}).getByRole('checkbox');await box.check();await scope.locator('summary').click();
    await page.getByLabel('Ask a question',{exact:true}).fill('What is the invoice reference and total? Cite the document.');
    const wait=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith('/messages/stream')&&r.request().method()==='POST',{timeout:300000});await page.getByRole('button',{name:'Send',exact:true}).click();await wait;await expect(page.getByRole('button',{name:'Send',exact:true})).toBeVisible({timeout:300000});
    const answer=page.getByRole('article',{name:'Aegis answer',exact:true}).last();await expect(answer).toContainText('INV-A-42');await expect(answer).toContainText('42');await answer.getByRole('button',{name:/Citation \d+:/}).first().click();await expect(page.getByRole('dialog')).toContainText('INV-A-42');await page.getByRole('dialog').getByRole('button',{name:/Close/}).click();
    await answer.getByRole('button',{name:'Helpful answer',exact:true}).click();const conversations=await get('/conversations');const current=await get('/conversations/'+conversations[0].id);if(!current.messages.some(m=>m.feedback==='up'))throw Error('Feedback not persisted.');
    const exported=await get('/conversations/'+current.id+'/export');if(!JSON.stringify(exported).includes('INV-A-42'))throw Error('Chat export omitted answer.');state.document_conversation_id=current.id;persist();await page.reload();await page.getByRole('button',{name:'Conversations',exact:true}).click();await page.locator('.chat-list button').filter({hasText:'What is the invoice reference and total? Cite the document.'}).first().click();await expect(page.locator('main')).toContainText('INV-A-42');
   });
   }else{await nav('Document Chat');}
   await step('Temporary Document Chat parses one file, answers, clears without indexing',async()=>{
    await page.getByRole('button',{name:'Temporary chat',exact:true}).click();await page.getByLabel('Temporary chat model').selectOption(state.models.chat.id);const before=(await get('/documents')).length;
    await page.getByLabel('Temporary document file',{exact:true}).setInputFiles(fileA());await expect(page.getByLabel('Temporary document attachment')).toContainText('Ready for direct questions');
    await page.getByLabel('Ask a temporary question').fill('What is the invoice reference and total?');await page.getByLabel('Send temporary question').click();await expect(page.getByRole('article',{name:'Temporary answer',exact:true}).last()).toContainText('INV-A-42',{timeout:300000});await expect(page.getByLabel('Send temporary question')).toBeVisible({timeout:300000});
    if((await get('/documents')).length!==before)throw Error('Temporary chat created a durable indexed document.');await page.getByLabel('Clear temporary document').click();await expect(page.getByLabel('Temporary document attachment')).toHaveCount(0);await expect(page.getByLabel('Send temporary question')).toBeDisabled();
   });
  }


  if(phase==='assistant'){
   await step('Assistant general knowledge and saved-result numeric filter with citations',async()=>{
    await nav('Aegis Agent');await page.getByLabel('Agent dataset',{exact:true}).selectOption(state.dataset.id);await page.getByLabel('Agent Model',{exact:true}).selectOption(state.models.chat.id);
    let plan=await send('What is Kubernetes? Explain briefly.');if(plan.calls.length)throw Error('General knowledge request proposed document operations.');await expect(page.locator('.agent-v2-chat-answer').last()).toContainText(/container/i,{timeout:300000});
    let expected=0;for(const item of (await get('/extractions')).filter(e=>(e.dataset_id||e.parent_id||e.kb_id)===state.dataset.id&&e.status==='ready')){const ex=await get('/extractions/'+item.id);const rows=ex.result.records?ex.result.records.map(r=>r.fields):[ex.result];expected+=rows.filter(r=>r.total>50).length;}
    plan=await send('How many saved invoice items have a total greater than 50?');if(plan.calls.length||!plan.explanation.includes('There are '+expected+' saved profiles/items'))throw Error('Numeric count differed from saved results: '+plan.explanation);const conversation=await get('/conversations/'+plan.conversation_id);const message=conversation.messages.filter(m=>m.role==='assistant').at(-1);if(!message.citations.length||message.citations.some(c=>c.kind!=='extraction'))throw Error('Saved result count omitted extraction citations.');await page.getByRole('button',{name:/Open citation \d+/}).last().click();await expect(page.locator('.review-identity')).toContainText(message.citations.at(-1).extraction_id);await page.locator('.download-results summary').click();const awaited=page.waitForEvent('download');await page.getByRole('link',{name:'JSON (.json)',exact:true}).click();const download=await awaited;await download.saveAs(out+'/review-download.json');const exported=JSON.parse(fs.readFileSync(out+'/review-download.json','utf8'));if(exported.extraction_id!==message.citations.at(-1).extraction_id||!exported.result)throw Error('UI download did not match the opened extraction.');state.filtered_count=expected;persist();
   });
  }
  if(phase==='failures'||phase==='cancel'){
   if(phase==='failures'){
   await step('Assistant partial upload failure, retry failure and continue-ready extraction',async()=>{
    await nav('Aegis Agent');await page.getByLabel('Agent dataset',{exact:true}).selectOption(state.dataset.id);await page.getByLabel('Agent Model',{exact:true}).selectOption(state.models.chat.id);
    await page.locator('input[type=file]').last().setInputFiles([fixture('recovery-good-invoice.txt','Fictional invoice. Invoice reference INV-RECOVERY-22. Total including tax: 22 USD.'),{name:'recovery-invalid.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.4\nFictional invalid PDF fixture.\n')}]);
    const plan=await send('Upload and extract these attached invoices.');await page.getByLabel('Workflow prompt template',{exact:true}).selectOption(state.template.id);await page.getByLabel('Extraction mode',{exact:true}).selectOption('independent');await page.getByRole('button',{name:'Confirm upload and extraction',exact:true}).click();
    await page.getByRole('button',{name:'Continue with ready documents',exact:true}).waitFor({timeout:300000});await expect(page.getByRole('button',{name:'End this request',exact:true})).toBeVisible();
    await page.getByRole('button',{name:'Retry failed indexing',exact:true}).click();await page.getByRole('button',{name:'Continue with ready documents',exact:true}).waitFor({timeout:300000});
    await page.getByRole('button',{name:'Continue with ready documents',exact:true}).click();await page.getByRole('button',{name:'Confirm extraction',exact:true}).click();await page.getByRole('button',{name:/Review result and evidence/}).waitFor({timeout:900000});
    const final=await get('/agent-v2/plans/'+plan.id);const upload=final.calls.find(c=>c.tool==='upload');if(upload.uploaded_document_ids.length!==1||upload.skipped_document_ids.length!==1)throw Error('Failed file was not excluded from continuation.');const result=final.calls.find(c=>c.tool==='extract').result;const id=result.extraction_id||result.extractions?.[0]?.extraction_id;const ex=await waitEx(id);if(ex.result.reference!=='INV-RECOVERY-22'||ex.result.total!==22)throw Error('Recovery extraction mismatch.');state.recovery_extraction_id=id;persist();
    await page.getByRole('button',{name:/Review result and evidence/}).click();await expect(page.locator('.review-identity')).toContainText(id);await page.screenshot({path:out+'/recovery-review.png',fullPage:true});
   });
   }
   await step('Assistant cancellation preserves failed-upload status and original file',async()=>{
    await nav('Aegis Agent');await page.getByLabel('Agent dataset',{exact:true}).selectOption(state.dataset.id);await expect(page.getByLabel('Agent Model',{exact:true})).toHaveValue(state.models.chat.id);await page.getByRole('button',{name:'New agent conversation',exact:true}).click();await page.locator('input[type=file]').last().setInputFiles({name:'cancel-invalid.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.4\nInvalid fictional fixture.\n')});const plan=await send('Upload this attached file.');if(plan.calls.map(c=>c.tool).join(',')!=='upload')throw Error('Upload-only request proposed unrequested extraction.');await page.getByRole('button',{name:'Confirm upload',exact:true}).click();await page.getByRole('button',{name:'End this request',exact:true}).waitFor({timeout:300000});await page.getByRole('button',{name:'End this request',exact:true}).click();const cancelled=await get('/agent-v2/plans/'+plan.id);if(!cancelled.superseded)throw Error('Request did not end.');state.failed_job_id=cancelled.calls[0].jobs[0].id;state.failed_job_attempts=cancelled.calls[0].jobs[0].attempts;persist();const target=cancelled.calls[0].jobs[0].target_id;const doc=await get('/documents/'+target);if(doc.status!=='failed')throw Error('Document falsely marked ready.');const original=await page.request.get(url('/documents/'+target+'/source'));if(!original.ok())throw Error('Failed original was not retained.');
   });
  }
  if(phase==='operations'||phase==='operations_finish'){
   if(phase==='operations'){
   await step('Model edit validation and cancel preserve the registered model',async()=>{
    await nav('Model Registration');await page.getByLabel('Search registered models').fill(state.models.chat.name);await page.getByRole('button',{name:'Edit '+state.models.chat.name,exact:true}).click();await page.locator('.registration-extra summary').click();await page.locator('#registration-extra-parameters').fill('{"unsupported_option":true}');await expect(page.locator('#registration-parameter-error')).toContainText(/supported keys/i);await expect(page.getByRole('button',{name:'Save Model',exact:true})).toBeDisabled();await page.getByLabel('Cancel model registration').click();const models=await get('/models');if(models.find(m=>m.id===state.models.chat.id).version!==state.models.chat.version)throw Error('Cancelled edits changed saved registration.');
   });

   await step('Dataset inactive guard and reactivation',async()=>{
    await nav('Home');await page.getByRole('button',{name:'Search datasets',exact:true}).click();await page.getByLabel('Search datasets').fill(state.suffix);await page.getByRole('link',{name:'Open dataset '+state.dataset.name,exact:true}).click();
    await page.getByRole('button',{name:'Settings',exact:true}).click();await page.getByRole('button',{name:'Deactivate dataset',exact:true}).click();await expect(page.getByRole('button',{name:'Activate dataset',exact:true})).toBeVisible();const invalid=await page.request.post(url('/extractions'),{headers:{'X-CSRF-Token':(await get('/auth/me')).csrf_token},data:{dataset_id:state.dataset.id,document_ids:[state.documents[0].id],template_id:state.template.id}});if(invalid.status()!==409)throw Error('Inactive dataset permitted extraction.');await page.getByRole('button',{name:'Activate dataset',exact:true}).click();await expect(page.getByRole('button',{name:'Deactivate dataset',exact:true})).toBeVisible();
   });
   await step('Connections profile save/version and safe export, without activating settings',async()=>{
    await nav('Connections');await page.getByRole('button',{name:'Profiles',exact:true}).click();await page.getByLabel('Profile name').fill('All screens QA profile '+state.suffix);state.profile=await responseTo('POST','/api/settings/profiles',()=>page.getByRole('button',{name:'Save current profile',exact:true}).click());persist();const profile=page.locator('.item.row.between.wrap').filter({has:page.getByRole('heading',{name:state.profile.name,exact:true})});await profile.getByRole('button',{name:'Save new version',exact:true}).click();await responseTo('PUT','/api/settings/profiles/'+state.profile.id,()=>page.getByRole('button',{name:'Confirm',exact:true}).click());await expect(profile).toContainText('Version 2');
    // Endpoint verification uses the browser's authenticated request; global configuration remains unchanged.
    const exported=await get('/settings/export');if(exported.api_key||exported.oci_api_key)throw Error('Settings export exposed credentials.');
    await page.getByRole('button',{name:'Providers',exact:true}).click();const diagnostics=await responseTo('POST','/api/settings/test',()=>page.getByRole('button',{name:'Test saved connections',exact:true}).click(),180000);if(!diagnostics.ok)throw Error('Configured service diagnostics failed: '+JSON.stringify(diagnostics.checks));state.service_checks=diagnostics.checks;persist();await expect(page.locator('main')).toContainText('Connection test result');
   });
   }
   await step('Jobs and activity retry preserves a truthful failed status for a corrupt original',async()=>{
    if(!state.failed_job_id)throw Error('Run failure fixtures first.');await nav('Jobs & activity');const row=page.getByRole('row').filter({hasText:'cancel-invalid.pdf'}).first();const retried=await responseTo('POST','/api/jobs/'+state.failed_job_id+'/retry',()=>row.getByRole('button',{name:'Retry',exact:true}).click());await expect.poll(async()=>{const jobs=await get('/jobs');const j=jobs.find(j=>j.id===state.failed_job_id);return j.status==='failed'&&j.attempts>=1;},{timeout:180000,intervals:[1000,2000]}).toBe(true);await refresh();await expect(row).toContainText('failed');
   });

   await step('Every screen at mobile size; no horizontal page overflow',async()=>{
    await page.setViewportSize({width:390,height:844});
    for(const name of ['Home','Aegis Agent','Datasets','Document Chat','Extraction Review','Re-extract','Prompt templates','Model Registration','Model Mapping','Dashboard','Jobs & activity','Connections','Services & migration','Users & passwords']){
     const open=page.getByRole('button',{name:'Open navigation',exact:true});if(await open.isVisible())await open.click();await nav(name);if(!await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1))throw Error('Horizontal overflow on '+name);state.screens.push(name);persist();
    }
    await page.screenshot({path:out+'/all-screens-mobile.png',fullPage:true});
   });
   await step('Logout, invalid login, empty-form validation and recovery navigation',async()=>{
    await page.setViewportSize({width:1440,height:1000});await page.getByRole('button',{name:'Sign out',exact:true}).click();await expect(page.locator('#login-username')).toBeVisible();await page.locator('#login-username').fill('');await page.getByRole('button',{name:'Sign in',exact:true}).click();await expect(page.locator('main')).toContainText('Enter your username.');await page.locator('#login-username').fill('nonexistent-all-screens-qa');await page.locator('#login-password').fill('Invalid-QA-password-only');await page.getByRole('button',{name:'Sign in',exact:true}).click();await expect(page.locator('main')).toContainText('Invalid username or password');await page.locator('#login-password').fill('');await page.getByRole('link',{name:'Forgot password?',exact:true}).click();await expect(page.locator('main')).toContainText(/password recovery|Direct password reset|Recover|Reset/i);state.recovery_text=await page.locator('main').innerText();persist();await page.getByRole('link',{name:/Back to sign in|Return to sign in/}).click();await expect(page.locator('#login-username')).toBeVisible();
   });
  }
  if(phase==='recovery'){
   await step('Docker Oracle recovery availability is explicitly blocked; return to sign in works',async()=>{
    await page.getByRole('button',{name:'Sign out',exact:true}).click();await page.getByRole('link',{name:'Forgot password?',exact:true}).click();await expect(page.locator('main').getByRole('alert')).toContainText('Direct password reset is available only in the local desktop app.');const response=await page.request.get(url('/local-recovery'));if(response.status()!==403)throw Error('Unexpected recovery availability status.');state.recovery_text=await page.locator('main').innerText();persist();await page.getByRole('link',{name:'Back to sign in',exact:true}).click();await expect(page.locator('#login-username')).toBeVisible();
   });
  }
  if(report.errors.length)throw Error('Uncaught browser errors were recorded.');
  report.passed=true;
 }catch(e){report.passed=false;report.failure=e.message;await page.screenshot({path:out+'/failure-'+phase+'.png',fullPage:true}).catch(()=>{});process.exitCode=1;}
 finally{report.completed_at=new Date().toISOString();persist();console.log(JSON.stringify({phase,passed:report.passed,failure:report.failure,errors:report.errors}));await browser.close();}
})();
