import { describe, expect, it } from "vitest";
import { landingFor, supportLanding, type SupportHost } from "../registry";

const HOSTS: SupportHost[] = [
  {
    scopeSetKeys: ["probe.read"],
    landing: (resourceType, resourceId) =>
      resourceId ? `/probe/${resourceType}/${resourceId}` : "/probe",
  },
  { scopeSetKeys: ["evil.read"], landing: () => "//evil.example/steal" },
];

describe("the support landing registry", () => {
  it("returns the matching context's page", () => {
    expect(landingFor(HOSTS, "workspace", "probe.read", null)).toBe("/probe");
    expect(landingFor(HOSTS, "case", "probe.read", "c-1")).toBe(
      "/probe/case/c-1",
    );
  });

  it("returns / when no context claims the scope set", () => {
    expect(landingFor(HOSTS, "workspace", "unknown.read", null)).toBe("/");
    expect(landingFor([], "workspace", "probe.read", null)).toBe("/");
  });

  it("returns / for a page outside the app", () => {
    expect(landingFor(HOSTS, "workspace", "evil.read", null)).toBe("/");
  });

  it("lands Sales' support set on the orders list", () => {
    expect(supportLanding("workspace", "sales.case_support", null)).toBe(
      "/sales/orders",
    );
  });
});
