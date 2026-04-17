/// <reference types="vite/client" />

import type { AppBridgeApiSurface } from "./bridge";

declare global {
  interface Window {
    pywebview?: {
      api?: AppBridgeApiSurface;
    };
  }
}

export {};
