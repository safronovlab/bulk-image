import '@testing-library/jest-dom/vitest';
import { URL as NodeURL } from 'node:url';
import { vi } from 'vitest';

// jsdom replaces the global URL constructor with one that resolves relative
// URLs against window.location (http://localhost:3000). Several worker tests
// pass `import.meta.url` as a base — a `file://` URL — and then read the
// resolved URL via Node's `fs.readFileSync(URL)`. The jsdom URL drops the
// scheme. Restore Node's URL globally so those tests can read source files
// via the file:// scheme.
vi.stubGlobal('URL', NodeURL);

// jsdom does not expose `Worker` on globalThis. The component test suites
// (e.g. BatchProcessTab) spy on it to verify worker lifecycle. Provide a
// minimal stub so vi.spyOn(globalThis, 'Worker') can attach without
// "property does not exist" errors. Real-component code wraps construction
// in try/catch, so the stub returning a plain object is enough.
if (typeof globalThis.Worker === 'undefined') {
  class StubWorker {
    constructor() {
      this.postMessage = () => {};
      this.terminate = () => {};
      this.addEventListener = () => {};
      this.removeEventListener = () => {};
      this.onmessage = null;
      this.onerror = null;
    }
  }
  globalThis.Worker = StubWorker;
}
