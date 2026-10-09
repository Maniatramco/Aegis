export type PromptUpload = { fileName: string; name: string; schema: Record<string, unknown>; preview: string; replacesExisting?:boolean };
export async function readPromptUpload(file: Pick<File, 'name' | 'size' | 'text'>): Promise<PromptUpload> {
  if (!/\.json$/i.test(file.name)) throw new Error('Upload a .json file for your prompt.');
  if (!file.size || file.size > 1024 * 1024) throw new Error('Prompt JSON must be a non-empty file of 1 MB or smaller.');
  let parsed: unknown;
  const text=(await file.text()).replace(/^\uFEFF/, '');
  try { parsed = JSON.parse(text); }
  catch(error) {
    const message=error instanceof Error?error.message:'';
    const position=message.match(/position (\d+)/)?.[1];
    const coordinates=message.match(/line (\d+) column (\d+)/);
    let location='';
    if(coordinates)location=` at line ${coordinates[1]}, column ${coordinates[2]}`;
    else if(position!==undefined){const offset=Number(position);const before=text.slice(0,offset);location=` at line ${before.split('\n').length}, column ${offset-before.lastIndexOf('\n')}`;}
    throw new Error(`Invalid JSON${location}. Check quotes, commas and brackets, then attach the corrected file.`);
  }
  if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') throw new Error('Prompt JSON must contain a JSON Schema object, or an object with name and schema.');
  const payload = parsed as Record<string, unknown>;
  const schema = Object.prototype.hasOwnProperty.call(payload, 'schema') ? payload.schema : payload;
  if (!schema || Array.isArray(schema) || typeof schema !== 'object') throw new Error('The schema field must be a JSON object.');
  const name = file.name;
  if (!name.trim() || name.length > 200) throw new Error('The prompt filename must contain 1 to 200 characters.');
  return { fileName: file.name, name, schema: schema as Record<string, unknown>, preview: JSON.stringify(parsed, null, 2) };
}
