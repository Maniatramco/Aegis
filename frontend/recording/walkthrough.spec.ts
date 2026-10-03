import { test, expect, type Locator } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { checked, seedMockCatalog, seedDataset } from '../tests/fixtures';

// Isolated issue-7 preview. Real app/API/storage/worker; synthetic content and
// explicit mock providers. No intercepted responses or invented UI states.
const output = path.resolve('recording-output');
test('record chat attachments, durable indexing and a source-grounded answer', async ({ browser, request }) => {
  await mkdir(output, { recursive: true });
  const password = process.env.AEGIS_SMOKE_PASSWORD;
  if (!password) throw new Error('Use the disposable smoke deployment.');
  const session = await checked(await request.post('/api/auth/login', { data: { username: 'smoke', password } }));
  const headers = { 'X-CSRF-Token': session.csrf_token };
  const settings = await checked(await request.get('/api/settings'));
  expect(settings.model_provider).toBe('mock'); expect(settings.embedding_provider).toBe('mock');
  const models = await seedMockCatalog(request, headers, 'Upload demo');
  const dataset = await seedDataset(request, headers, 'Chat uploads · synthetic demo', [models.fast, models.careful], models.embedding);
  const context = await browser.newContext({
    baseURL: process.env.AEGIS_TEST_BASE_URL || 'http://127.0.0.1:3000', storageState: await request.storageState(),
    viewport: { width: 1440, height: 960 }, recordVideo: { dir: path.join(output, 'raw'), size: { width: 1440, height: 960 } },
    locale: 'en-US', timezoneId: 'UTC', reducedMotion: 'reduce',
  });
  await context.addInitScript(() => {
    document.addEventListener('DOMContentLoaded', () => {
      const pointer = document.createElement('div'); pointer.setAttribute('aria-hidden', 'true');
      pointer.style.cssText = 'position:fixed;width:20px;height:20px;border:3px solid #df8600;background:#ffdf7050;border-radius:50%;pointer-events:none;z-index:2147483647;left:0;top:0;transform:translate(-50%,-50%);box-shadow:0 0 0 2px #fff';
      document.body.append(pointer);
      document.addEventListener('mousemove', event => { pointer.style.left = event.clientX + 'px'; pointer.style.top = event.clientY + 'px'; });
      document.addEventListener('mousedown', () => { pointer.style.background = '#f97316bb'; });
      document.addEventListener('mouseup', () => { pointer.style.background = '#ffdf7050'; });
    });
  });
  const started = Date.now(); const page = await context.newPage();
  const chapters: { start: number; title: string; text: string }[] = []; const errors: string[] = []; const uploads: string[] = []; const chatWrites: string[] = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('request', r => { if (r.method() !== 'POST') return; if (r.url().endsWith('/api/documents/upload')) uploads.push(r.url()); if (r.url().includes('/api/conversations')) chatWrites.push(r.url()); });
  const pause = (seconds = 3) => page.waitForTimeout(seconds * 1000);
  const chapter = (title: string, text: string) => { chapters.push({ start: (Date.now() - started) / 1000, title, text }); };
  const button = (name: string) => page.getByRole('button', { name, exact: true });
  const modal = page.getByRole('dialog', { name: 'Attach documents', exact: true });
  async function click(locator: Locator) {
    await locator.scrollIntoViewIfNeeded(); const box = await locator.boundingBox();
    if (box) await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 12 });
    await pause(.25); await locator.click(); await pause(.4);
  }
  const compose = (action: string) => execFileSync('docker', ['compose', action, 'worker'], { cwd: path.resolve('..'), stdio: 'pipe' });
  let workerStopped = false;
  try {
    chapter('01  Choose a dataset', 'Start in Ask Aegis and choose the dataset that will own your documents. This demonstration uses synthetic files and mock models.');
    await page.goto('/#Ask%20Aegis');
    await expect(page.getByRole('heading', { name: 'Ask Aegis', exact: true })).toBeVisible();
    await page.getByLabel('Chat dataset', { exact: true }).selectOption(dataset.id);
    await page.getByRole('combobox', { name: 'Chat model', exact: true }).selectOption(models.careful.id);
    await click(button('Hide conversations'));
    const question = 'What are the delivery date and review reference?';
    await page.getByLabel('Ask a question').fill(question);
    await pause(8);

    chapter('02  Attach a document', 'Use the paperclip on desktop or mobile. Select a file, review its destination, and keep your question draft unchanged.');
    await click(button('Attach documents'));
    await modal.getByLabel('Choose documents').setInputFiles({ name: 'Review-note.txt', mimeType: 'text/plain', buffer: Buffer.from('SYNTHETIC DEMO. Review reference UPLOAD-2026. Keep source originals for evidence review.') });
    await expect(modal).toContainText('Ready to upload'); await pause(8);
    await page.screenshot({ path: path.join(output, '01-attachment-panel.png') });
    await click(button('Close uploads'));

    chapter('03  Drag and drop', 'You can also drop files directly into chat. Files are staged for review first. Dropping a file does not upload it or send your question.');
    const data = await page.evaluateHandle(() => {
      const transfer = new DataTransfer(); transfer.items.add(new File(['SYNTHETIC DEMO. The delivery date is 12 October 2026. The review reference is UPLOAD-2026. This evidence was uploaded from Ask Aegis and retained as a stored original.'], 'Delivery-brief.txt', { type: 'text/plain' })); return transfer;
    });
    await page.locator('.chat-main').dispatchEvent('dragenter', { dataTransfer: data });
    await page.locator('.chat-main').dispatchEvent('dragover', { dataTransfer: data });
    await expect(page.locator('.chat-drop-overlay')).toBeVisible(); await pause(4);
    await page.locator('.chat-main').dispatchEvent('drop', { dataTransfer: data }); await data.dispose();
    await expect(modal.getByRole('listitem')).toHaveCount(2); expect(uploads).toHaveLength(0); expect(chatWrites).toHaveLength(0); await pause(6);

    chapter('04  Store, then index', 'Upload uses the same dataset storage and indexing workflow. Originals are stored first, and durable jobs track progress until the files are ready.');
    // Pause only this disposable worker to make the actual durable queued state
    // visible on video, then resume it. No API responses or statuses are faked.
    compose('stop'); workerStopped = true;
    await click(modal.getByRole('button', { name: 'Upload 2', exact: true }));
    await expect(modal.getByText('Stored · queued for indexing', { exact: true })).toHaveCount(2);
    await expect(modal.getByRole('progressbar')).toHaveCount(2); await pause(5);
    await page.screenshot({ path: path.join(output, '02-stored-queued.png') });
    compose('start'); workerStopped = false;
    await click(button('Close uploads')); await expect(page.getByLabel('Ask a question')).toHaveValue(question); await pause(3);
    await click(button('Attach documents'));
    await expect(modal.getByText('Ready for questions', { exact: true })).toHaveCount(2, { timeout: 90000 });
    expect(uploads).toHaveLength(2); expect(chatWrites).toHaveLength(0); await pause(5);
    await page.screenshot({ path: path.join(output, '03-ready.png') });
    await click(button('Close uploads'));

    chapter('05  Ask when ready', 'Choose the new ready document in Document scope. Chat consent stays separate from upload. Only pressing Send requests an answer.');
    await click(page.locator('.chat-scope summary'));
    await click(page.getByRole('checkbox', { name: /Delivery-brief\.txt/ })); await pause(3);
    await click(page.locator('.chat-scope summary'));
    await click(page.getByRole('checkbox', { name: /I approve sending this request/ })); await pause(3);
    const response = page.waitForResponse(r => /\/messages\/stream$/.test(r.url()) && r.request().method() === 'POST');
    await click(button('Send')); expect((await response).ok()).toBe(true);
    await expect(page.getByTitle('Copy answer')).toBeVisible();
    await expect(page.getByText('MOCK TEST OUTPUT', { exact: true })).toBeVisible(); await pause(5);
    await page.screenshot({ path: path.join(output, '04-answer.png') });

    chapter('06  Inspect the source', 'The answer links back to the document you just uploaded. Open Sources to inspect the evidence. Mock output demonstrates the workflow, not live model quality.');
    await click(page.getByRole('button', { name: /^Sources(?: \d+)?$/ }));
    const sources = page.getByRole('dialog', { name: 'Sources', exact: true });
    await expect(sources).toContainText('Delivery-brief.txt'); await expect(sources).toContainText('UPLOAD-2026');
    await pause(10); await page.screenshot({ path: path.join(output, '05-source.png') });
    await click(button('Close sources'));
    await expect(page.getByRole('button', { name: 'Dismiss error' })).toHaveCount(0); expect(errors).toEqual([]);
    await pause(3);
  } finally {
    if (workerStopped) compose('start');
    const duration = (Date.now() - started) / 1000;
    await writeFile(path.join(output, 'recording.json'), JSON.stringify({ commit: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(), applicationBaseCommit: '4964434dd417660c1493c43ed553be30a6b5d3a6', localApplicationCommit: 'ad5afc0dcbe12d64d337cb79b0f40cf4078f8dbf', viewport: { width: 1440, height: 960 }, duration, chapters, errors, data: 'Synthetic documents, real app/API/storage and worker; mock model/embeddings. Worker paused briefly to demonstrate the real durable queue. No intercepted responses. Authentication completed before recording.' }, null, 2));
    await context.close();
  }
});
