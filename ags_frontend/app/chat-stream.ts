type ChatEvent = { type: string; payload: Record<string, any> };

// Streams can end without a done event (proxy timeout, disconnect, Stop).
// Keep partial text, but never label that as a completed answer.
export async function readChatStream(stream: ReadableStream<Uint8Array>, onEvent: (event: ChatEvent) => void) {
  const reader = stream.getReader(), decoder = new TextDecoder();
  let buffer = "", completed = false;
  const dispatch = (frame: string) => {
    const lines = frame.split("\n");
    const type = lines.find(line => line.startsWith("event:"))?.slice(6).trim();
    const raw = lines.filter(line => line.startsWith("data:")).map(line => line.slice(5).trimStart()).join("\n");
    if (!raw || !type) return; // SSE keep-alive comments have no data.
    const payload = JSON.parse(raw);
    onEvent({ type, payload });
    if (type === "done") completed = true;
  };
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer = (buffer + decoder.decode(value, { stream: !done })).replace(/\r\n/g, "\n");
      let end;
      while ((end = buffer.indexOf("\n\n")) !== -1) {
        dispatch(buffer.slice(0, end)); buffer = buffer.slice(end + 2);
      }
      if (done) break;
    }
    if (buffer.trim()) dispatch(buffer);
    if (!completed) throw new Error("The connection closed before the answer finished. Retry the question; any partial response is kept below.");
  } finally {
    await reader.cancel().catch(() => {}); reader.releaseLock();
  }
}
