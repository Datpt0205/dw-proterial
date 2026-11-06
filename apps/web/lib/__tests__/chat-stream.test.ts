import { ApiClient, ApiError, chatFrames } from "@dw/api-client";
import { describe, expect, it } from "vitest";

const WIRE =
  'event: step\ndata: {"key":"read","title":"Đang đọc"}\n\n' +
  'event: delta\ndata: {"text":"Hồ sơ "}\n\n' +
  'event: done\ndata: {"session_id":"s"}\n\n';

function client(body: string | null, init: ResponseInit) {
  return new ApiClient({
    baseUrl: "http://api",
    fetchImpl: async () => new Response(body, init),
  });
}

const SSE = { headers: { "content-type": "text/event-stream" } };

describe("chatFrames", () => {
  it("keeps a frame a network chunk cut for the next read", () => {
    for (let cut = 1; cut < WIRE.length; cut++) {
      const first = chatFrames(WIRE.slice(0, cut));
      const second = chatFrames(first.rest + WIRE.slice(cut));
      expect([...first.frames, ...second.frames].map((f) => f.event)).toEqual([
        "step",
        "delta",
        "done",
      ]);
    }
  });
});

describe("chatStream", () => {
  const ask = (api: ApiClient, seen: unknown[] = []) =>
    api.chatStream(
      "/x",
      { body: {}, idempotencyKey: "k" },
      (event) => seen.push(event),
    );

  it("hands over each event and resolves with the kept turn", async () => {
    const seen: unknown[] = [];
    await expect(ask(client(WIRE, SSE), seen)).resolves.toEqual({
      session_id: "s",
    });
    expect(seen).toEqual([
      { event: "step", key: "read", title: "Đang đọc" },
      { event: "delta", text: "Hồ sơ " },
    ]);
  });

  it("raises a refusal as the status it is", async () => {
    const body = JSON.stringify({ code: "forbidden", message: "no", details: {} });
    await expect(ask(client(body, { status: 403 }))).rejects.toBeInstanceOf(
      ApiError,
    );
  });

  it("answers a replayed key with the kept turn and no events", async () => {
    const seen: unknown[] = [];
    const replay = client('{"session_id":"s"}', {
      headers: { "content-type": "application/json" },
    });
    await expect(ask(replay, seen)).resolves.toEqual({ session_id: "s" });
    expect(seen).toEqual([]);
  });

  it("says the server's fixed words on an error frame", async () => {
    const wire = 'event: error\ndata: {"message":"Hãy hỏi lại."}\n\n';
    await expect(ask(client(wire, SSE))).rejects.toThrow("Hãy hỏi lại.");
  });

  it("refuses a stream that ends with no turn: nothing was kept", async () => {
    const wire = 'event: delta\ndata: {"text":"Hồ"}\n\n';
    await expect(ask(client(wire, SSE))).rejects.toThrow();
  });
});
