import { z } from "zod";
import {
  chatEventSchema,
  chatGreetingSchema,
  conversationSchema,
  documentTemplateSchema,
  errorResponseSchema,
  transcriptSchema,
  type ChatEvent,
  type ChatGreeting,
  type Conversation,
  type DocumentTemplate,
  type Transcript,
  type ViewContext,
} from "@dw/contracts";
import { ApiClient, ApiError, type ApiClientOptions } from "./client";

/**
 * Sales chat runs as its own service today, so it gets its own base URL.
 *
 * A turn is streamed over `fetch` rather than `EventSource`, which cannot send
 * the Authorization and tenant headers every request here is verified against.
 */
export class SalesChatClient extends ApiClient {
  constructor(private readonly chatOptions: ApiClientOptions) {
    super(chatOptions);
  }

  /**
   * The bytes of a saved document.
   *
   * Not `request`, which parses JSON against a schema: this returns a file.
   * The Authorization and tenant headers still have to be on it, which is why
   * it goes through the same `fetchImpl` rather than through a plain link -
   * an `<a href>` carries neither and would 401.
   *
   * `pdf` asks the server to render the document, because no browser shows a
   * .docx. The rendering is cached server-side, so a second preview is a
   * lookup rather than another LibreOffice run.
   */
  async downloadDocument(
    artifactId: string,
    format: "original" | "pdf" = "original",
  ): Promise<{ blob: Blob; filename: string }> {
    const fetchImpl = this.chatOptions.fetchImpl ?? fetch;
    const headers: Record<string, string> = {};
    const token = await this.chatOptions.getAccessToken?.();
    if (token) headers.Authorization = `Bearer ${token}`;

    const response = await fetchImpl(
      `${this.chatOptions.baseUrl}/api/v1/sales-chat/artifacts/${artifactId}/content?format=${format}`,
      { headers },
    );
    if (!response.ok) {
      throw new ApiError(response.status, {
        code: "internal",
        message: `HTTP ${response.status}`,
        details: {},
      });
    }
    return {
      blob: await response.blob(),
      filename: filenameFrom(response.headers.get("Content-Disposition")),
    };
  }

  /**
   * The templates of one scope, active and archived.
   *
   * Archived ones are included on purpose: a document generated last quarter
   * names one of them, and a list that hides it cannot explain that document.
   */
  listTemplates(
    scopeType: "workspace" | "account",
    scopeId?: string,
  ): Promise<DocumentTemplate[]> {
    const search = new URLSearchParams({ scope_type: scopeType });
    if (scopeId) search.set("scope_id", scopeId);
    return this.request(
      "GET",
      `/api/v1/sales-chat/templates?${search.toString()}`,
      z.array(documentTemplateSchema),
    );
  }

  /** Upload a .docx shell. The server validates it before anything opens it. */
  uploadTemplate(body: {
    scope_type: "workspace" | "account";
    scope_id?: string | null;
    name: string;
    filename: string;
    content_b64: string;
    make_default?: boolean;
  }): Promise<DocumentTemplate> {
    return this.request(
      "POST",
      "/api/v1/sales-chat/templates",
      documentTemplateSchema,
      { body },
    );
  }

  /** Retire a template. A POST, not a DELETE - this app allows GET and POST. */
  archiveTemplate(templateId: string): Promise<DocumentTemplate> {
    return this.request(
      "POST",
      `/api/v1/sales-chat/templates/${templateId}/archive`,
      documentTemplateSchema,
    );
  }

  /**
   * The line to open an empty thread with, written for the signed-in person.
   *
   * No conversation id: it describes their book, not a thread, so the panel
   * fetches it once and reuses it on every record - one model call a session
   * rather than one per screen.
   */
  greeting(): Promise<ChatGreeting> {
    return this.request(
      "GET",
      "/api/v1/sales-chat/greeting",
      chatGreetingSchema,
    );
  }

  openConversation(
    title: string,
    scope?: { scope_type: string; scope_ref: string },
  ): Promise<Conversation> {
    return this.request(
      "POST",
      "/api/v1/sales-chat/conversations",
      conversationSchema,
      { body: { title, ...scope } },
    );
  }

  listConversations(scope?: {
    scope_type: string;
    scope_ref?: string;
  }): Promise<Conversation[]> {
    const search = new URLSearchParams();
    if (scope?.scope_type) search.set("scope_type", scope.scope_type);
    if (scope?.scope_ref) search.set("scope_ref", scope.scope_ref);
    const query = search.toString();
    return this.request(
      "GET",
      `/api/v1/sales-chat/conversations${query ? `?${query}` : ""}`,
      z.array(conversationSchema),
    );
  }

  getTranscript(conversationId: string): Promise<Transcript> {
    return this.request(
      "GET",
      `/api/v1/sales-chat/conversations/${conversationId}`,
      transcriptSchema,
    );
  }

  /**
   * Stop the turn in flight on the server, not only this reader's stream.
   *
   * The run outlives the connection on purpose, so aborting the stream alone
   * left it calling tools and raising approval cards for work the person had
   * just abandoned. `cancelled` is false when nothing was running any more.
   */
  cancelTurn(conversationId: string): Promise<{ cancelled: boolean }> {
    return this.request(
      "POST",
      `/api/v1/sales-chat/conversations/${conversationId}/turn/cancel`,
      z.object({ cancelled: z.boolean() }),
    );
  }

  /** Clear the chat: the thread closes, its transcript stays readable. */
  archiveConversation(conversationId: string): Promise<void> {
    return this.requestNoContent(
      "POST",
      `/api/v1/sales-chat/conversations/${conversationId}/archive`,
    );
  }

  /**
   * One turn, as the events it produces.
   *
   * `signal` is how the reader stops a turn they no longer want. Aborting
   * ends this generator quietly rather than throwing: a person pressing
   * Stop has not hit an error, and surfacing `AbortError` to the caller put
   * "The user aborted a request." on screen as if something had gone wrong.
   *
   * The server is not told to stop. It finishes the run and writes the
   * transcript either way, which is deliberate - the run is the audit
   * record, and a turn that wrote to a CRM record cannot be made to have
   * never happened because a browser stopped listening.
   */
  async *sendMessage(
    conversationId: string,
    message: string,
    view?: ViewContext,
    signal?: AbortSignal,
  ): AsyncGenerator<ChatEvent> {
    const fetchImpl = this.chatOptions.fetchImpl ?? fetch;
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    };
    const token = await this.chatOptions.getAccessToken?.();
    if (token) headers.Authorization = `Bearer ${token}`;

    const response = await fetchImpl(
      `${this.chatOptions.baseUrl}/api/v1/sales-chat/conversations/${conversationId}/messages`,
      {
        method: "POST",
        headers,
        body: JSON.stringify({ message, view }),
        signal,
      },
    );
    // The backend explains itself in the body; showing only the status turned
    // every business refusal into "network error" on screen.
    if (!response.ok || !response.body) {
      const json: unknown = await response.json().catch(() => null);
      const parsed = errorResponseSchema.safeParse(json);
      throw new ApiError(
        response.status,
        parsed.success
          ? parsed.data
          : {
              code: "internal",
              message: `HTTP ${response.status}`,
              details: {},
            },
      );
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let boundary = buffer.indexOf("\n\n");
        while (boundary !== -1) {
          const block = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          const event = parseEvent(block);
          if (event) yield event;
          boundary = buffer.indexOf("\n\n");
        }
      }
    } catch (cause) {
      // Only the stop we asked for is swallowed. A dropped connection throws
      // the same `AbortError` name in some runtimes, so the signal - not the
      // error - is what says which of the two happened.
      if (!signal?.aborted) throw cause;
    } finally {
      // Runs on an abort, on a `break` in the consumer, and on a normal end.
      // Without it a turn the reader walked away from held its connection
      // open until the response was garbage collected.
      await reader.cancel().catch(() => {
        // The stream is already gone; there is nothing left to release.
      });
    }
  }
}

function parseEvent(block: string): ChatEvent | null {
  const lines = block.split("\n");
  const type = lines.find((line) => line.startsWith("event: "))?.slice(7);
  const data = lines.find((line) => line.startsWith("data: "))?.slice(6);
  if (!type || !data) return null;

  const parsed = chatEventSchema.safeParse({ type, data: JSON.parse(data) });
  return parsed.success ? parsed.data : null;
}

/**
 * The name the server chose, out of `Content-Disposition`.
 *
 * `filename*` is read first: it is the RFC 5987 form and the only one that
 * survives a Vietnamese title. The ASCII `filename` beside it is the fallback
 * the header carries for clients that cannot read the encoded one.
 */
function filenameFrom(disposition: string | null): string {
  if (!disposition) return "document";
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition)?.[1];
  if (encoded) {
    try {
      return decodeURIComponent(encoded);
    } catch {
      // A malformed header should not stop a download that otherwise worked.
    }
  }
  return /filename="([^"]+)"/i.exec(disposition)?.[1] ?? "document";
}
