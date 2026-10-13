const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
const source = path.resolve(__dirname, '../app/chat-stream.ts');
const compiled = new Module(source, module);
compiled._compile(ts.transpileModule(fs.readFileSync(source, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText, source);
const { readChatStream } = compiled.exports;
function stream(text) {
  const bytes = new TextEncoder().encode(text);
  return new ReadableStream({ start(controller) {
    // One-byte chunks split UTF-8 characters, CRLF pairs, and event boundaries.
    for (const byte of bytes) controller.enqueue(Uint8Array.of(byte));
    controller.close();
  }});
}
test('parses split UTF-8, CRLF and heartbeat comments', async () => {
  const received = [];
  await readChatStream(stream(': keep-alive\r\n\r\nevent: delta\r\ndata: {"text":"Hello 🌍"}\r\n\r\nevent: done\r\ndata: {"message":{"status":"completed"}}\r\n\r\n'), e => received.push(e));
  assert.deepEqual(received.map(e => e.type), ['delta', 'done']);
  assert.equal(received[0].payload.text, 'Hello 🌍');
});
test('an abrupt end retains deltas and never reports completion', async () => {
  const received = [];
  await assert.rejects(readChatStream(stream('event: delta\ndata: {"text":"Partial answer"}\n\n'), e => received.push(e)), /before the answer finished/);
  assert.deepEqual(received.map(e => e.payload.text), ['Partial answer']);
});
test('a terminal event without a trailing separator is accepted', async () => {
  const received = [];
  await readChatStream(stream('event: done\ndata: {"message":{"text":"Complete"}}'), e => received.push(e));
  assert.equal(received[0].payload.message.text, 'Complete');
});
test('the structured provider error reaches the UI with partial text', async () => {
  let saved;
  await assert.rejects(readChatStream(stream('event: error\ndata: {"detail":"Provider unavailable","message":{"text":"Partial","status":"failed"}}\n\n'), e => {
    saved = e.payload.message;
    throw new Error(e.payload.detail);
  }), /Provider unavailable/);
  assert.equal(saved.text, 'Partial');
  assert.equal(saved.status, 'failed');
});
