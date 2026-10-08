export function supportedModelParameters(protocol: string, category: string, connection: Record<string, any> = {}): string[] {
  if (category === "embedding") {
    if (protocol === "ollama") return ["keep_alive"];
    if (["openai-compatible", "azure-openai"].includes(protocol)) return ["encoding_format"];
    if (protocol === "bedrock" && (connection.embedding_format || "titan") === "titan") return ["normalize"];
    return [];
  }
  const parameters: Record<string, string[]> = {
    ollama: ["temperature", "top_p", "top_k", "min_p", "repeat_penalty", "repeat_last_n", "seed", "stop", "keep_alive"],
    "openai-compatible": ["temperature", "top_p", "frequency_penalty", "presence_penalty", "seed", "stop", "reasoning_effort"],
    "azure-openai": ["temperature", "top_p", "frequency_penalty", "presence_penalty", "seed", "stop", "reasoning_effort"],
    bedrock: ["temperature", "topP", "stopSequences"],
    vertex: ["temperature", "topP", "topK", "stopSequences", "seed", "presencePenalty", "frequencyPenalty"],
    oci: ["temperature", "top_p", "top_k", "frequency_penalty", "presence_penalty", "seed", connection.chat_format === "cohere" ? "stop_sequences" : "stop"],
  };
  return parameters[protocol] || [];
}

export function parseModelParameters(text: string, supported: string[]): Record<string, unknown> {
  let value;
  try { value = JSON.parse(text.trim() || "{}"); }
  catch { throw new Error("Enter valid JSON, for example {\"temperature\": 0.2}."); }
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Extra parameters must be a JSON object.");
  if (Object.keys(value).length > 20) throw new Error("Use at most 20 extra parameters.");
  if (Object.keys(value).some(key => !supported.includes(key))) throw new Error("Use only the supported keys listed above. Token limits have their own fields.");
  return value;
}
