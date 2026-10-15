import { describe, expect, it, vi } from "vitest";
import { ApiClient } from "@dw/api-client";
import { IdempotencyKeys } from "../idempotency";

describe("IdempotencyKeys (ui-quality §3)", () => {
  it("gives a retry of the same payload the same key", () => {
    const keys = new IdempotencyKeys();
    const first = keys.keyFor("grant", { email: "lan@x.vn", role: "member" });
    expect(first).toMatch(/^[0-9a-f-]{36}$/);
    expect(keys.keyFor("grant", { email: "lan@x.vn", role: "member" })).toBe(
      first,
    );
  });

  it("replaces the key after an edit, and after the call succeeded", () => {
    const keys = new IdempotencyKeys();
    const first = keys.keyFor("grant", { email: "lan@x.vn" });
    const edited = keys.keyFor("grant", { email: "minh@x.vn" });
    expect(edited).not.toBe(first);
    keys.settle("grant");
    expect(keys.keyFor("grant", { email: "minh@x.vn" })).not.toBe(edited);
  });

  it("keeps one action's key apart from another's", () => {
    const keys = new IdempotencyKeys();
    expect(keys.keyFor("revoke/a", { w: 1 })).not.toBe(
      keys.keyFor("revoke/b", { w: 1 }),
    );
  });
});

describe("the platform client sends the key it is given", () => {
  function client() {
    const fetchImpl = vi.fn<typeof fetch>(
      async () =>
        new Response(
          JSON.stringify({ user_id: "u", email: null, display_name: "Lan" }),
          { status: 201 },
        ),
    );
    return {
      fetchImpl,
      api: new ApiClient({ baseUrl: "http://api.test", fetchImpl }),
    };
  }

  function sentKey(fetchImpl: ReturnType<typeof client>["fetchImpl"]) {
    const init = fetchImpl.mock.calls[0]![1];
    return (init?.headers as Record<string, string>)["Idempotency-Key"];
  }

  it("on a member grant", async () => {
    const { fetchImpl, api } = client();
    await api.grantMember(
      { email: "lan@x.vn", workspaceId: "w", roleKeys: ["member"] },
      "key-1",
    );
    expect(sentKey(fetchImpl)).toBe("key-1");
  });

  it("on a member revoke, which answers 204", async () => {
    const { fetchImpl, api } = client();
    fetchImpl.mockResolvedValueOnce(new Response(null, { status: 204 }));
    await api.revokeMember("u", "w", "key-2");
    expect(sentKey(fetchImpl)).toBe("key-2");
  });
});
