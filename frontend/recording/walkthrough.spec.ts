import { test, expect, type Locator, type Page } from '@playwright/test';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { checked, seedMockCatalog, seedDataset, uploadReady } from '../tests/fixtures';

// Records the running application, not a mock UI or intercepted API responses.
// Only the browser cursor is annotated. Captions are added to the exported video.
// Authentication occurs before recording; no storageState, trace or secrets persist.
const output = path.resolve('recording-output');
const invoiceName = 'Northstar-invoice-INV-2026-1042.txt';
const briefName = 'Northstar-project-brief.txt';
const summaryName = 'Northstar-invoice-summary.txt';
const invoice = `SYNTHETIC DEMONSTRATION DOCUMENT. No real customer or payment details.
INVOICE INV-2026-1042
Supplier: Northstar Studio (fictional).
Customer: Aegis Demonstration Workspace.
Project: Document Intelligence Pilot.
Issue date: 1 October 2026. Currency: USD.
Discovery and information architecture: 20 hours at USD 150 = USD 3,000.
Prototype implementation: 40 hours at USD 150 = USD 6,000.
Accessibility and acceptance testing: 10 hours at USD 150 = USD 1,500.
Subtotal USD 10,500. Tax USD 0. Total due USD 10,500.
Payment terms: net 30 calendar days. Due date: 31 October 2026.
No bank details are included. Review every field against this original.`;
const brief = `SYNTHETIC PROJECT BRIEF — Document Intelligence Pilot
Objective: searchable project evidence while preserving original files.
Milestone 1, 5 October 2026: upload and index sample documents.
Milestone 2, 12 October 2026: review answers and source citations.
Milestone 3, 19 October 2026: validate extraction schemas and exports.
Acceptance review: 23 October 2026.
Analyst: review sources and extracted fields. Administrator: configure providers.
This is synthetic content for a screen-recorded integration walkthrough.`;
const summary = 'SYNTHETIC DEMO. Invoice INV-2026-1042 totals USD 10,500. Payment terms are Net 30 calendar days. The stated due date is 31 October 2026.';

test('record complete actual-app walkthrough with safe synthetic data', async ({ browser, request }) => {
  await mkdir(output, { recursive: true });
  const password = process.env.AEGIS_SMOKE_PASSWORD;
  if (!password) throw new Error('A disposable recording password is required.');
  const authStatus = await checked(await request.get('/api/auth/status'));
  expect(authStatus.setup_required, 'Use a fresh disposable deployment, never an existing workspace').toBe(true);
  const env = await readFile(path.resolve('../.env'), 'utf8');
  const bootstrap = env.split('\n').find(line => line.startsWith('AEGIS_BOOTSTRAP_TOKEN='))?.split('=', 2)[1];
  if (!bootstrap) throw new Error('Disposable bootstrap token is missing.');
  await checked(await request.post('/api/auth/setup', { data: { username: 'demo', password, bootstrap_token: bootstrap } }));
  const session = await checked(await request.post('/api/auth/login', { data: { username: 'demo', password } }));
  const headers = { 'X-CSRF-Token': session.csrf_token };
  const models = await seedMockCatalog(request, headers, 'Demo');
  const starter = await seedDataset(request, headers, 'Product knowledge · demo', [models.fast], models.embedding);
  await uploadReady(request, headers, starter, 'Getting-started.txt', 'SYNTHETIC DEMO. Aegis preserves originals, indexes documents, answers with citations, and extracts structured fields.');
  await checked(await request.post('/api/datasets', { headers, data: { name: 'Archived research · demo', description: 'Synthetic archived dataset. Processing paused.', active: false } }));
  const template = await checked(await request.post('/api/templates', { headers, data: {
    name: 'Invoice review · demo', schema: { type: 'object', properties: {
      invoice_number: { type: 'string' }, supplier: { type: 'string' }, currency: { type: 'string' }, total_due: { type: 'number' }, due_date: { type: ['string', 'null'] },
    }, required: ['invoice_number', 'supplier', 'currency', 'total_due', 'due_date'], additionalProperties: false },
  } }));
  const context = await browser.newContext({
    baseURL: process.env.AEGIS_TEST_BASE_URL || 'http://127.0.0.1:3000',
    storageState: await request.storageState(),
    viewport: { width: 1440, height: 960 },
    recordVideo: { dir: path.join(output, 'raw'), size: { width: 1440, height: 960 } },
    locale: 'en-US', timezoneId: 'UTC', reducedMotion: 'reduce',
  });
  await context.addInitScript(() => {
    document.addEventListener('DOMContentLoaded', () => {
      const pointer = document.createElement('div');
      pointer.id = 'recording-cursor';
      pointer.setAttribute('aria-hidden', 'true');
      pointer.style.cssText = 'position:fixed;width:20px;height:20px;border:3px solid #df8600;background:#ffdf7050;border-radius:50%;pointer-events:none;z-index:2147483647;left:0;top:0;transform:translate(-50%,-50%);box-shadow:0 0 0 2px #fff';
      document.body.append(pointer);
      document.addEventListener('mousemove', event => { pointer.style.left = event.clientX + 'px'; pointer.style.top = event.clientY + 'px'; });
      document.addEventListener('mousedown', () => { pointer.style.background = '#f97316bb'; });
      document.addEventListener('mouseup', () => { pointer.style.background = '#ffdf7050'; });
    });
  });
  const started = Date.now();
  const page = await context.newPage();
  const chapters: { start: number; title: string; text: string }[] = [];
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  const pause = (seconds = 3) => page.waitForTimeout(seconds * 1000);
  async function chapter(title: string, text: string) {
    chapters.push({ start: (Date.now() - started) / 1000, title, text });
    for (const input of await page.locator('input[type="password"]').all()) expect(await input.inputValue()).toBe('');
  }
  async function click(locator: Locator) {
    await locator.scrollIntoViewIfNeeded();
    const box = await locator.boundingBox();
    if (box) await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 14 });
    await pause(0.35);
    await locator.click();
    await pause(0.6);
  }
  async function type(locator: Locator, value: string) {
    await click(locator);
    await locator.fill('');
    await locator.pressSequentially(value, { delay: 40 });
    await pause(0.5);
  }
  async function select(locator: Locator, value: string) {
    await locator.scrollIntoViewIfNeeded();
    const box = await locator.boundingBox();
    if (box) await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 14 });
    await pause(0.7);
    await locator.selectOption(value);
    await pause(1.2);
  }
  async function nav(name: string) {
    const navigation = page.getByRole('navigation');
    const target = navigation.getByRole('button', { name, exact: true });
    if (!await target.isVisible()) await click(navigation.getByRole('button', { name: 'Manage workspace', exact: true }));
    await click(target);
    await expect(page.getByRole('heading', { name: name === 'Dashboard' ? 'Workspace overview' : name, exact: true }).first()).toBeVisible();
    await page.evaluate(() => window.scrollTo(0, 0));
    await pause(1);
  }
  async function frame(name: string) { await page.screenshot({ path: path.join(output, name + '.png') }); }
  const button = (name: string) => page.getByRole('button', { name, exact: true });

  try {
    await chapter('01  Home', 'A real Aegis workspace: start with a dataset, then ask questions or extract fields.');
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Home', exact: true })).toBeVisible();
    await pause(7); await frame('01-home');

    await chapter('02  Onboard a dataset', 'Give the project its own dataset. Models and documents are scoped to that dataset.');
    await nav('Datasets'); await pause(3);
    await click(page.locator('.dataset-intro').getByRole('button', { name: 'Onboard dataset', exact: true }));
    await type(page.getByLabel('Dataset name', { exact: true }), 'Northstar pilot · demo');
    await type(page.getByLabel('Dataset description', { exact: true }), 'Synthetic invoice and project evidence for the walkthrough.');
    await pause(2);
    const created = page.waitForResponse(r => r.url().endsWith('/api/datasets') && r.request().method() === 'POST');
    await click(button('Create dataset'));
    const dataset = await checked(await created);
    await expect(page.getByRole('heading', { name: 'Models approved for this dataset', exact: true })).toBeVisible();

    await chapter('03  Map models', 'Approve two generation models and one embedding model, then choose dataset defaults.');
    for (const model of [models.fast, models.careful, models.embedding]) await click(page.getByLabel(`Mapped model ${model.name}`, { exact: true }));
    await select(page.getByLabel('Default chat model', { exact: true }), models.fast.id);
    await select(page.getByLabel('Default extraction model', { exact: true }), models.careful.id);
    await select(page.getByLabel('Embedding model', { exact: true }), models.embedding.id);
    await pause(4); await frame('03-model-mapping');
    await click(button('Save model mappings'));
    await expect.poll(async () => (await checked(await request.get(`/api/datasets/${dataset.id}/models`))).embedding_model_id).toBe(models.embedding.id);

    await chapter('04  Add source documents', 'Upload synthetic TXT documents. Aegis stores the originals and indexes their content.');
    await click(button('Documents')); await click(button('Add documents'));
    await page.getByLabel('Choose documents').setInputFiles([
      { name: invoiceName, mimeType: 'text/plain', buffer: Buffer.from(invoice) },
      { name: briefName, mimeType: 'text/plain', buffer: Buffer.from(brief) },
      { name: summaryName, mimeType: 'text/plain', buffer: Buffer.from(summary) },
    ]);
    await pause(3); await click(button('Upload 3'));
    const row = page.getByRole('row').filter({ hasText: invoiceName });
    await expect(row.getByText('ready', { exact: true })).toBeVisible({ timeout: 90000 });
    await pause(4); await frame('04-documents');
    await chapter('05  Check the original', 'Preview the stored invoice before trusting any answer or extracted field.');
    await click(row.getByTitle('Preview document'));
    await expect(page.getByRole('dialog')).toContainText('INV-2026-1042');
    await pause(7); await frame('05-preview'); await click(button('Close preview'));

    await chapter('06  Ask Aegis', 'Choose the dataset and model. Limit the question to a specific source when needed.');
    await nav('Ask Aegis');
    await select(page.getByLabel('Chat dataset', { exact: true }), dataset.id);
    await select(page.getByRole('combobox', { name: 'Chat model', exact: true }), models.careful.id);
    await click(page.locator('summary').filter({ hasText: /^Document scope/ }));
    await click(page.getByRole('checkbox', { name: new RegExp(summaryName.replaceAll('.', '\\.')) }));
    await pause(3);
    await click(page.locator('summary').filter({ hasText: /^Document scope/ }));
    const consent = page.getByRole('checkbox', { name: /I approve sending this request/ });
    if (await consent.isVisible()) await click(consent);
    await type(page.getByLabel('Ask a question'), 'What are the invoice total and payment terms?');
    await pause(2); await click(button('Send'));
    await expect(page.getByTitle('Copy answer')).toBeVisible();
    await expect(page.getByText('MOCK TEST OUTPUT', { exact: true })).toBeVisible();
    await pause(6); await frame('06-chat');

    await chapter('07  Inspect sources', 'Open Sources to inspect the retrieved evidence. This mock answer repeats source text.');
    await click(page.getByRole('button', { name: /^Sources(?: \d+)?$/ }));
    await expect(page.getByRole('dialog', { name: 'Sources', exact: true })).toContainText(summaryName);
    await pause(7); await frame('07-sources'); await click(button('Close sources'));
    await chapter('08  Continue and revisit', 'Follow-up questions stay in the conversation. History lets you reopen the saved thread.');
    if (await consent.isVisible()) await click(consent);
    await type(page.getByLabel('Ask a question'), 'What due date is stated in the source?');
    await click(button('Send')); await expect(page.getByTitle('Copy answer')).toHaveCount(2);
    await pause(5);
    const title = await page.locator('.chat-list button[aria-current="true"] strong').textContent();
    await click(page.getByLabel('New conversation', { exact: true }).first());
    await pause(3);
    await click(page.locator('.chat-list button').filter({ hasText: title || '' }).first());
    await expect(page.getByTitle('Copy answer')).toHaveCount(2);
    await pause(4); await frame('08-history');

    await chapter('09  Create an extraction', 'Select a schema, a mapped extraction model and the invoice document.');
    await nav('Extract');
    await select(page.getByLabel('Extraction dataset', { exact: true }), dataset.id);
    await select(page.getByRole('combobox', { name: 'Extraction model', exact: true }), models.careful.id);
    await select(page.getByLabel('Extraction template'), template.id);
    // Switching from chat may preserve the scoped summary selection. Choose only the invoice.
    for (const box of await page.locator('.extraction-focus input[type="checkbox"]').all()) if (await box.isChecked()) await click(box);
    await click(page.getByRole('checkbox', { name: new RegExp(invoiceName.replaceAll('.', '\\.')) }));
    if (await consent.isVisible()) await click(consent);
    await pause(4); await frame('09-extract-create');
    const extractionCreated = page.waitForResponse(r => r.url().endsWith('/api/extractions') && r.request().method() === 'POST');
    await click(button('Run extraction'));
    const extraction = await checked(await extractionCreated);
    await expect.poll(async () => (await checked(await request.get(`/api/extractions/${extraction.id}`))).status, { timeout: 90000 }).toBe('ready');
    await click(page.getByTitle('Reload extraction'));
    await expect(page.getByLabel('Extraction result JSON')).toHaveValue(/MOCK TEST VALUE/);

    await chapter('10  Review and export', 'Mock extraction yields placeholders. In live use, compare every value with the source before export.');
    await pause(7); await frame('10-extract-review');
    const download = page.waitForEvent('download');
    await click(page.getByRole('link', { name: 'JSON', exact: true }));
    expect((await download).suggestedFilename()).toContain('.json');
    await pause(2);
    await click(button('Extraction history')); await pause(4); await frame('10-extract-history');

    await chapter('11  Templates', 'Reusable JSON schemas define field names, types and required values. Templates are versioned.');
    await nav('Templates');
    await expect(page.getByLabel('Template name', { exact: true })).toHaveValue('Invoice review · demo');
    await pause(8); await frame('11-templates');

    await chapter('12  Workspace dashboard', 'Manage workspace opens the operational views: document status, activity and service readiness.');
    await nav('Dashboard'); await pause(7); await frame('12-dashboard');
    await chapter('13  Index inspector', 'Inspect the stored chunks and provenance behind retrieval for a selected document.');
    await nav('Index inspector');
    await page.getByLabel('Document to inspect').selectOption({ label: invoiceName });
    await click(button('Inspect index'));
    await expect(page.locator('pre.code').filter({ hasText: 'INV-2026-1042' }).first()).toBeVisible();
    await pause(7); await frame('13-index');
    await chapter('14  Jobs and activity', 'Track ingestion and extraction jobs. Completed states here come from the real background worker.');
    await nav('Jobs & activity');
    await expect(page.getByText('completed', { exact: true }).first()).toBeVisible();
    await pause(6); await frame('14-jobs');

    await chapter('15  Connections', 'Register models and save provider profiles. This demonstration uses only mock providers.');
    await nav('Connections'); await pause(5); await frame('15-connections');
    await click(button('Profiles')); await pause(4);
    await click(button('Providers')); await expect(page.getByLabel('Model provider', { exact: true })).toHaveValue('mock');
    await pause(5); await frame('15-providers');
    await click(button('Storage')); await pause(4);
    await chapter('16  Migration and setup', 'OCI requires provisioned services and migration validation. This walkthrough does not connect a live tenancy.');
    await nav('Services & migration'); await pause(6); await frame('16-services');
    await nav('Setup'); await pause(6); await frame('16-setup');
    await chapter('17  Your document workflow', 'Onboard a dataset → map models → upload → ask with evidence → review and export structured data.');
    await nav('Home'); await pause(8); await frame('17-home-finish');
    expect(errors).toEqual([]);
    await expect(page.getByRole('button', { name: 'Dismiss error' })).toHaveCount(0);
  } finally {
    const duration = (Date.now() - started) / 1000;
    await writeFile(path.join(output, 'recording.json'), JSON.stringify({
      commit: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
      applicationBaseCommit: '236efd1fb1a1844f658714ebf0637db44ba3d11c',
      viewport: { width: 1440, height: 960 }, duration, chapters, errors,
      data: 'Synthetic fictional documents. Real app and backend with explicitly gated mock model/embedding providers. No intercepted API responses. No live provider calls.',
    }, null, 2));
    await context.close();
  }
});
