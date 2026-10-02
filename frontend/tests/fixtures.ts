import { expect, type APIRequestContext, type APIResponse, type Response } from "@playwright/test";

export type Entity = { id: string; name: string; [key: string]: any };
export type Headers = Record<string, string>;

export async function checked(response: APIResponse | Response) {
  expect(response.ok(), `API request returned ${response.status()}`).toBeTruthy();
  return response.json();
}

export async function sessionHeaders(request: APIRequestContext): Promise<Headers> {
  const session = await checked(await request.get("/api/auth/me"));
  return { "X-CSRF-Token": session.csrf_token };
}

// Every test catalog entry uses a named, explicitly mock-only connection profile.
// No live provider key or substituted browser API response is needed by these tests.
export async function seedMockCatalog(request: APIRequestContext, headers: Headers, prefix: string) {
  const settings = await checked(await request.get("/api/settings"));
  expect(settings.model_provider).toBe("mock");
  expect(settings.embedding_provider).toBe("mock");
  const existing: Entity[] = await checked(await request.get("/api/models"));
  const definitions = [
    ["Fast review", "mock-fast", ["chat", "extraction"]],
    ["Careful review", "mock-careful", ["chat", "extraction"]],
    ["Separate review", "mock-separate", ["chat", "extraction"]],
    ["Local test embedding", "mock-embedding", ["embedding"]],
  ] as const;
  const prior = definitions.map(([label, providerModel, capabilities]) => existing.find(model =>
    model.name === `${prefix} · ${label}` && model.provider === "mock" && model.enabled !== false &&
    model.provider_model === providerModel && JSON.stringify(model.capabilities) === JSON.stringify(capabilities),
  ));
  if (prior.every(Boolean)) {
    return { profile: { id: prior[0]!.connection_profile_id, name: `${prefix} · mock connection` }, fast: prior[0]!, careful: prior[1]!, separate: prior[2]!, embedding: prior[3]! };
  }
  const profile: Entity = await checked(await request.post("/api/settings/profiles", {
    headers, data: { name: `${prefix} · mock connection` },
  }));
  const models: Entity[] = [];
  for (const [index, [label, providerModel, capabilities]] of definitions.entries()) {
    models.push(prior[index] || await checked(await request.post("/api/models", {
      headers, data: {
        name: `${prefix} · ${label}`, connection_profile_id: profile.id,
        provider_model: providerModel, capabilities, enabled: true,
      },
    })));
  }
  return { profile, fast: models[0], careful: models[1], separate: models[2], embedding: models[3] };
}

export async function mapDataset(request: APIRequestContext, headers: Headers, dataset: Entity, models: Entity[], embedding: Entity) {
  return checked(await request.put(`/api/datasets/${dataset.id}/models`, {
    headers, data: {
      mappings: [...models, embedding].map(model => ({ model_id: model.id, enabled: true })),
      default_chat_model_id: models[0]?.id || null,
      default_extraction_model_id: models[0]?.id || null,
      embedding_model_id: embedding.id,
    },
  }));
}

export async function seedDataset(request: APIRequestContext, headers: Headers, name: string, models: Entity[], embedding: Entity) {
  const dataset: Entity = await checked(await request.post("/api/datasets", {
    headers, data: { name, description: "Synthetic integration-test evidence only." },
  }));
  await mapDataset(request, headers, dataset, models, embedding);
  return dataset;
}

export async function uploadReady(request: APIRequestContext, headers: Headers, dataset: Entity, name: string, content: string) {
  const upload = await checked(await request.post("/api/documents/upload", {
    headers, multipart: { dataset_id: dataset.id, files: { name, mimeType: "text/plain", buffer: Buffer.from(content) } },
  }));
  const document: Entity = upload.documents[0];
  await expect.poll(async () => {
    const current = await checked(await request.get(`/api/documents/${document.id}`));
    if (current.status === "failed") throw new Error(`Synthetic document indexing failed: ${name}`);
    return current.status;
  }, { timeout: 120000 }).toBe("ready");
  return document;
}

export async function seedTemplate(request: APIRequestContext, headers: Headers, name: string) {
  return checked(await request.post("/api/templates", {
    headers, data: {
      name, schema: {
        type: "object", properties: { reference: { type: "string" } },
        required: ["reference"], additionalProperties: false,
      },
    },
  }));
}
