import { configure } from "@testing-library/react";

// A `findBy`/`waitFor` waits 1 s by default. Under a loaded machine (a full
// run beside a Docker build) the heavier pages took longer to draw and three
// files failed as "Unable to find" while passing alone (2026-10-27). Waiting
// longer costs nothing when the element is there: the wait ends as it shows.
configure({ asyncUtilTimeout: 5_000 });

// antd's responsive helpers and its overlays ask for browser APIs jsdom does
// not implement. A test that needs a particular width overrides matchMedia.
if (typeof window !== "undefined") {
  if (!window.matchMedia) {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }),
    });
  }
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
