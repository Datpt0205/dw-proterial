/**
 * What antd needs from a browser and jsdom does not have: `ResizeObserver`
 * (the horizontal menu measures its items) and `matchMedia` (breakpoints,
 * reduced motion). Both answer as a screen that asked for nothing. Tests in
 * the node environment have no `window` and skip this.
 */
if (typeof window !== "undefined") {
  if (typeof window.ResizeObserver !== "function") {
    window.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver;
  }
  if (typeof window.matchMedia !== "function") {
    window.matchMedia = (query: string): MediaQueryList => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    });
  }
}
