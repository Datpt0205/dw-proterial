import type { ChatStreamEvent } from "@dw/api-client";
import type { ChatLive } from "@dw/ui";

export const NOTHING_YET: ChatLive = { steps: [], answer: "" };

/**
 * The turn being answered, one event further on. A `replace` takes the words
 * back: they stopped being checkable on the server, and its own sentence is
 * the answer.
 */
export function liveAfter(live: ChatLive, event: ChatStreamEvent): ChatLive {
  switch (event.event) {
    case "step":
      return {
        ...live,
        steps: [...live.steps, { key: event.key, title: event.title }],
      };
    case "delta":
      return { ...live, answer: live.answer + event.text };
    case "replace":
      return { ...live, answer: event.text };
  }
}
