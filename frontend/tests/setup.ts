import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";
afterEach(() => {
  cleanup();
  sessionStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
  value() {
    this.open = true;
  },
});
Object.defineProperty(HTMLDialogElement.prototype, "close", {
  value() {
    this.open = false;
  },
});
class Observer {
  constructor(private callback: ResizeObserverCallback) {}
  observe(target: Element) {
    this.callback(
      [
        {
          target,
          contentRect: new DOMRect(0, 0, 640, 250),
        } as ResizeObserverEntry,
      ],
      this as unknown as ResizeObserver,
    );
  }
  unobserve() {}
  disconnect() {}
}
// jsdom has no layout engine; provide a stable chart container, not chart internals.
Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
  value: () => new DOMRect(0, 0, 640, 250),
  configurable: true,
});
Object.defineProperty(globalThis, "ResizeObserver", {
  value: Observer,
  configurable: true,
});
