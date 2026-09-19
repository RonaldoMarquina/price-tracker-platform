import "@testing-library/jest-dom";

// Mock ResizeObserver for Recharts ResponsiveContainer in tests
if (typeof globalThis !== "undefined") {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

