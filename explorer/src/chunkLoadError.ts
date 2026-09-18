const CHUNK_RELOAD_KEY = "semantica-explorer-chunk-reload";

export function isStaleChunkError(error: unknown): boolean {
  const message = error instanceof Error
    ? `${error.name} ${error.message} ${error.stack ?? ""}`
    : String(error ?? "");
  return /Failed to fetch dynamically imported module|error loading dynamically imported module|Importing a module script failed|Loading chunk [\w./-]+ failed|ChunkLoadError/i.test(message);
}

export function reloadOnceForStaleChunk(error: unknown): boolean {
  if (!isStaleChunkError(error) || typeof sessionStorage === "undefined") {
    return false;
  }
  if (sessionStorage.getItem(CHUNK_RELOAD_KEY) === "1") {
    return false;
  }
  sessionStorage.setItem(CHUNK_RELOAD_KEY, "1");
  window.location.reload();
  return true;
}

export function clearStaleChunkReloadToken(): void {
  if (typeof sessionStorage === "undefined") return;
  sessionStorage.removeItem(CHUNK_RELOAD_KEY);
}
