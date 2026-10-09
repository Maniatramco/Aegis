export type Json = Record<string, any>;
export type Operation = { key: string; path: string; method: string; group: string; definition: Json; notes: Json };
const methods = new Set(['get', 'post', 'put', 'patch', 'delete', 'head', 'options']);

export function listOperations(documentation: Json): Operation[] {
  return Object.entries(documentation.schema?.paths || {}).flatMap(([path, item]) =>
    Object.entries(item as Json).filter(([method]) => methods.has(method)).map(([method, definition]) => {
      const key = `${method.toUpperCase()} ${path}`;
      return { key, path, method: method.toUpperCase(), definition: definition as Json,
        group: (definition as Json).tags?.[0] || 'Other', notes: documentation.operations?.[key] || {} };
    }));
}

export function resolveSchema(schema: Json | undefined, spec: Json, seen: string[] = []): Json {
  if (!schema) return {};
  if (!schema.$ref) return schema;
  if (!schema.$ref.startsWith('#/') || seen.includes(schema.$ref)) return { description: `Reference: ${schema.$ref}` };
  const target = schema.$ref.slice(2).split('/').reduce((value: any, key: string) => value?.[key.replaceAll('~1', '/').replaceAll('~0', '~')], spec);
  const { $ref, ...siblings } = schema;
  return { ...resolveSchema(target, spec, [...seen, $ref]), ...siblings };
}

export function schemaType(schema: Json, spec: Json): string {
  const s = resolveSchema(schema, spec);
  if (s.anyOf || s.oneOf) return (s.anyOf || s.oneOf).map((part: Json) => schemaType(part, spec)).join(' | ');
  if (s.type === 'array') return `array<${schemaType(s.items || {}, spec)}>`;
  return s.format === 'binary' || s.contentMediaType === 'application/octet-stream' ? 'file' : Array.isArray(s.type) ? s.type.join(' | ') : s.type || (s.properties ? 'object' : 'any');
}

export function expandSchema(value: any, spec: Json, seen: string[] = [], depth = 0): any {
  if (depth > 18 || !value || typeof value !== 'object') return value;
  if (Array.isArray(value)) return value.map(child => expandSchema(child, spec, seen, depth + 1));
  if (value.$ref && seen.includes(value.$ref)) return value;
  const resolved = resolveSchema(value, spec, seen);
  const next = value.$ref ? [...seen, value.$ref] : seen;
  return Object.fromEntries(Object.entries(resolved).map(([key, child]) => [key, expandSchema(child, spec, next, depth + 1)]));
}

export function sampleValue(schema: Json, spec: Json, depth = 0): any {
  if (depth > 6) return {};
  const s = resolveSchema(schema, spec);
  if (s.example !== undefined) return s.example;
  if (s.examples?.length) return s.examples[0];
  if (s.enum?.length) return s.enum[0];
  if (s.const !== undefined) return s.const;
  if (s.default !== undefined && s.default !== null) return s.default;
  if (s.anyOf || s.oneOf) return sampleValue((s.anyOf || s.oneOf).find((part: Json) => part.type !== 'null') || {}, spec, depth + 1);
  if (s.type === 'object' || s.properties) return Object.fromEntries(Object.entries(s.properties || {})
    .filter(([name]) => (s.required || []).includes(name)).map(([name, child]) => [name, sampleValue(child as Json, spec, depth + 1)]));
  if (s.type === 'array') return Array.from({ length: Math.max(1, Math.min(s.minItems || 1, 20)) }, () => sampleValue(s.items || {}, spec, depth + 1));
  if (s.type === 'boolean') return false;
  if (s.type === 'integer' || s.type === 'number') return Math.max(s.minimum || 0, s.exclusiveMinimum !== undefined ? s.exclusiveMinimum + 1 : 1);
  if (s.type === 'null') return null;
  if (s.format === 'binary') return '@document.pdf';
  return 'example'.padEnd(s.minLength || 0, 'x');
}

export function requestExample(op: Operation, spec: Json): any {
  const preset: Record<string, any> = {
    'POST /api/auth/login': { username: 'your-username', password: '<your-password>' },
    'POST /api/datasets': { name: 'Invoices', description: 'Invoice documents' },
    'POST /api/conversations': { title: 'Invoice questions', dataset_id: '<dataset-id>', document_ids: ['<document-id>'] },
    'POST /api/templates': { name: 'Invoice total', dataset_id: '<dataset-id>', schema: { type: 'object', properties: { total: { type: 'number' } }, required: ['total'], additionalProperties: false } },
    'POST /api/extractions': { dataset_id: '<dataset-id>', document_ids: ['<document-id>'], template_id: '<template-id>', allow_external: false },
    'POST /api/temporary-chat/messages': { document_id: '<temporary-document-id>', model_id: '<chat-model-id>', text: 'What is the invoice total?', history: [], allow_external: false },
    'PUT /api/datasets/{id}/models': { mappings: ['embedding', 'chat', 'extraction'].map(role => ({ model_id: `<${role}-model-id>`, enabled: true })), embedding_model_id: '<embedding-model-id>', default_chat_model_id: '<chat-model-id>', default_extraction_model_id: '<extraction-model-id>', acknowledge_reindex: false },
    'POST /api/model-registrations': { name: 'Local chat', category: 'chat', provider_model: 'qwen3:4b', connection: { protocol: 'ollama', endpoint: 'http://127.0.0.1:11435', auth_mode: 'none' }, timeout: 60, enabled: true },
  };
  if (op.key === 'POST /api/templates/validate') return preset['POST /api/templates'];
  if (preset[op.key]) return preset[op.key];
  if (/\/messages(?:\/stream)?$/.test(op.path)) return { text: 'What is the invoice total?', dataset_id: '<dataset-id>', allow_external: false };
  const content = op.definition.requestBody?.content || {};
  return sampleValue((Object.values(content)[0] as Json)?.schema || {}, spec);
}

function shellQuote(value: string) { return `'${value.replaceAll("'", "'\\''")}'`; }
export function curlExample(op: Operation, spec: Json): string {
  const path = op.path.replace(/\{([^}]+)\}/g, '<$1>');
  const query = (op.definition.parameters || []).filter((p: Json) => p.in === 'query' && p.required).map((p: Json) => `${p.name}=<${p.name}>`).join('&');
  const lines = [`curl${op.path.endsWith('/stream') ? ' -N' : ''} -X ${op.method} ${shellQuote(`<API_BASE_URL>${path}${query ? '?' + query : ''}`)}`];
  if (op.key === 'POST /api/auth/login') lines.push(`  -c cookies.txt`);
  if (op.notes.authentication === 'Session or bearer token') {
    lines.push(`  -b cookies.txt`);
    if (op.notes.csrf_required) lines.push(`  -H 'X-CSRF-Token: <csrf-token>'`);
  }
  const content = op.definition.requestBody?.content || {};
  if (content['multipart/form-data']) {
    const s = resolveSchema(content['multipart/form-data'].schema, spec);
    for (const [name, field] of Object.entries(s.properties || {})) {
      if (name === 'files') {
        lines.push(`  -F 'files=@document-1.pdf'`);
        if (op.path !== '/api/temporary-chat/documents') lines.push(`  -F 'files=@document-2.pdf'`);
      }
      else if (name === 'dataset_id') lines.push(`  -F 'dataset_id=<dataset-id>'`);
      else if ((s.required || []).includes(name)) lines.push(`  -F ${shellQuote(`${name}=${sampleValue(field as Json, spec)}`)}`);
    }
  } else if (content['application/json']) {
    lines.push(`  -H 'Content-Type: application/json'`, `  --data ${shellQuote(JSON.stringify(requestExample(op, spec), null, 2))}`);
  }
  return lines.join(' \\\n');
}
