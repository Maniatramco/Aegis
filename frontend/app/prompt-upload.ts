export type PromptUpload = { fileName: string; name: string; schema: Record<string, unknown>; preview: string };
export async function readPromptUpload(file: Pick<File, 'name' | 'size' | 'text'>): Promise<PromptUpload> {
  if (!/\.json$/i.test(file.name)) throw new Error('Upload a .json file for your prompt.');
  if (!file.size || file.size > 1024 * 1024) throw new Error('Prompt JSON must be a non-empty file of 1 MB or smaller.');
  let parsed: unknown;
  try { parsed = JSON.parse((await file.text()).replace(/^\uFEFF/, '')); }
  catch { throw new Error('Invalid JSON. Fix the file syntax and upload it again.'); }
  if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') throw new Error('Prompt JSON must contain a JSON Schema object, or an object with name and schema.');
  const payload = parsed as Record<string, unknown>;
  const schema = Object.prototype.hasOwnProperty.call(payload, 'schema') ? payload.schema : payload;
  if (!schema || Array.isArray(schema) || typeof schema !== 'object') throw new Error('The schema field must be a JSON object.');
  const name = typeof payload.name === 'string' ? payload.name.trim() : file.name.replace(/\.json$/i, '');
  if (!name || name.length > 200) throw new Error('The prompt name must contain 1 to 200 characters.');
  return { fileName: file.name, name, schema: schema as Record<string, unknown>, preview: JSON.stringify(parsed, null, 2) };
}
