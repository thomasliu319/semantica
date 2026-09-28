// Injects the active Explorer version (`v=iot2` / `v=marketing`) into every
// same-origin `/api/*` request so the backend can route to the matching graph
// session. The version is read fresh from the URL on every call, so switching
// versions takes effect on the next request without a reload.

function currentVersion(): string {
  try {
    const value = new URLSearchParams(window.location.search).get("v");
    return value === "marketing" ? "marketing" : "iot2";
  } catch {
    return "iot2";
  }
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.toString();
  return input.url;
}

export function installExplorerVersionFetch(): void {
  if (typeof window === "undefined" || typeof window.fetch !== "function") return;
  const native = window.fetch.bind(window);

  window.fetch = (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = requestUrl(input);
    const origin = typeof window !== "undefined" ? window.location.origin : "";
    const isApi = url.startsWith("/api/") || url.startsWith(`${origin}/api/`);
    if (!isApi) return native(input, init);

    const headers = new Headers(init?.headers);
    if (!headers.has("X-Explorer-Version")) {
      headers.set("X-Explorer-Version", currentVersion());
    }
    return native(input, { ...init, headers });
  };
}
