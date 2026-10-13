import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach } from "vitest";

// The first visit to a lazily loaded screen (the Evaluation Lab pulls in the chart library) can take a
// few seconds to compile under jsdom, so asynchronous queries wait longer than the 1 s default.
configure({ asyncUtilTimeout: 8000 });

// jsdom lacks a few browser APIs the app touches; give it harmless versions.
if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({ matches: false, media: query, onchange: null, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, dispatchEvent: () => false }) as MediaQueryList;
}
if (!("ResizeObserver" in window)) {
  (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
if (!URL.createObjectURL) {
  URL.createObjectURL = () => "blob:test";
  URL.revokeObjectURL = () => {};
}
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView || (() => {});

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  localStorage.clear();
});
