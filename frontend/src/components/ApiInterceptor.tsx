"use client";

import { useEffect } from "react";

export default function ApiInterceptor() {
  useEffect(() => {
    if (typeof window === "undefined") return;

    const originalFetch = window.fetch;
    window.fetch = async (input, init) => {
      let url = "";
      if (typeof input === "string") {
        url = input;
      } else if (input instanceof URL) {
        url = input.toString();
      } else if (input && typeof input === "object" && "url" in input) {
        url = (input as any).url;
      }

      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "localhost:8000";
      const isBackendCall = url.includes("127.0.0.1:8000") || url.includes("localhost:8000") || url.includes(backendUrl);

      if (isBackendCall) {
        init = init || {};
        init.credentials = "include";
      }
      return originalFetch(input, init);
    };
  }, []);

  return null;
}
