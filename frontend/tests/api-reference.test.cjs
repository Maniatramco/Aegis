const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
const source = path.resolve(__dirname, '../app/api-reference.ts');
const compiled = new Module(source, module);
compiled._compile(ts.transpileModule(fs.readFileSync(source, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, source);
const { listOperations, resolveSchema, expandSchema, schemaType, sampleValue, curlExample, requestExample } = compiled.exports;

test('reference inventories only HTTP operations and carries authentication metadata', () => {
  const operations = listOperations({ schema: { paths: { '/api/x': { parameters: [], get: { tags: ['Documents'] }, post: {} } } }, operations: { 'GET /api/x': { authentication: 'Session or bearer token' } } });
  assert.equal(operations.length, 2);
  assert.equal(operations[0].group, 'Documents');
  assert.equal(operations[0].notes.authentication, 'Session or bearer token');
});
test('schema references resolve JSON pointer escaping without following remote or cyclic references', () => {
  const spec = { components: { schemas: { 'a/b': { type: 'integer', minimum: 3 }, Recursive: { $ref: '#/components/schemas/Recursive' } } } };
  assert.equal(resolveSchema({ $ref: '#/components/schemas/a~1b' }, spec).minimum, 3);
  assert.match(resolveSchema({ $ref: '#/components/schemas/Recursive' }, spec).description, /Reference/);
  assert.match(resolveSchema({ $ref: 'https://example.test/schema' }, spec).description, /Reference/);
});
test('examples handle nullable nested arrays, required fields, constraints and defaults', () => {
  const schema = { type: 'object', properties: { rows: { anyOf: [{ type: 'array', minItems: 2, items: { type: 'integer', minimum: 5 } }, { type: 'null' }] }, omitted: { type: 'string' }, mode: { enum: ['chat', 'extraction'] } }, required: ['rows', 'mode'] };
  assert.deepEqual(sampleValue(schema, {}), { rows: [5, 5], mode: 'chat' });
  assert.equal(schemaType(schema.properties.rows, {}), 'array<integer> | null');
  assert.equal(sampleValue({ type: 'boolean', default: true }, {}), true);
  assert.equal(schemaType({ type: 'array', items: { type: 'string', contentMediaType: 'application/octet-stream' } }, {}), 'array<file>');
});
test('nested model connection fields expand while recursive references stay bounded', () => {
  const spec = { components: { schemas: { Connection: { type: 'object', properties: { endpoint: { type: 'string' }, child: { $ref: '#/components/schemas/Connection' } } } } } };
  const expanded = expandSchema({ type: 'object', properties: { connection: { $ref: '#/components/schemas/Connection' } } }, spec);
  assert.equal(expanded.properties.connection.properties.endpoint.type, 'string');
  assert.equal(expanded.properties.connection.properties.child.$ref, '#/components/schemas/Connection');
});
test('multipart upload example repeats file parts and identifies the target dataset', () => {
  const op = { key: 'POST /api/documents/upload', path: '/api/documents/upload', method: 'POST', notes: { authentication: 'Session or bearer token', csrf_required: true }, definition: { requestBody: { content: { 'multipart/form-data': { schema: { type: 'object', properties: { files: { type: 'array', items: { type: 'string', format: 'binary' } }, dataset_id: { type: 'string' } }, required: ['files'] } } } } } };
  const example = curlExample(op, {});
  assert.equal((example.match(/-F 'files=@/g) || []).length, 2);
  assert.match(example, /dataset_id=<dataset-id>/);
  assert.match(example, /-b cookies.txt/);
  assert.match(example, /X-CSRF-Token: <csrf-token>/);
  assert.match(example, /\\\n/);
});
test('stream and public examples preserve transport and omit irrelevant auth headers', () => {
  const op = { key: 'POST /api/conversations/{id}/messages/stream', path: '/api/conversations/{id}/messages/stream', method: 'POST', notes: {}, definition: { requestBody: { content: { 'application/json': { schema: {} } } } } };
  assert.match(curlExample(op, {}), /^curl -N/);
  assert.doesNotMatch(curlExample(op, {}), /Authorization/);
  assert.match(curlExample(op, {}), /<id>/);
  const template = requestExample({ key: 'POST /api/templates' }, {});
  assert.equal(template.schema.additionalProperties, false);
  assert.deepEqual(template.schema.required, Object.keys(template.schema.properties));
});
