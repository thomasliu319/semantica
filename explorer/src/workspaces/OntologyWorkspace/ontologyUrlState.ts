// Sole owner of the Explorer deep-link query: v (app version) plus Ontology Hub tab/entity.
const VERSION_PARAM = "v";
const TAB_PARAM = "ontologyTab";
const ENTITY_PARAM = "ontologyEntity";
const EDITOR_TAB = "editor";
export const APP_VERSION = "iot2";
export const DEFAULT_TAB = "registry";
// Legal Explorer versions. `iot2` is the original IoT experience; `marketing`
// carries the marketing/operations domain. Anything else is normalized to `iot2`.
export const SUPPORTED_VERSIONS = ["iot2", "marketing"] as const;
export type ExplorerVersion = (typeof SUPPORTED_VERSIONS)[number];

function resolveVersion(value: string | null): ExplorerVersion {
  return (SUPPORTED_VERSIONS as readonly string[]).includes(value ?? "")
    ? (value as ExplorerVersion)
    : APP_VERSION;
}

export interface OntologyUrlState {
  /** Raw parameter value; the set of legal tab ids belongs to the workspace, not this module. */
  tab?: string;
  entityUri?: string;
}

/** `undefined` means the parameter is absent; an empty string means it is present but blank. */
export function parseOntologyUrlState(search: string): OntologyUrlState {
  const params = new URLSearchParams(search);
  return {
    tab: params.get(TAB_PARAM) ?? undefined,
    entityUri: params.get(ENTITY_PARAM) ?? undefined,
  };
}

/** The current Explorer version from a search string; defaults to `iot2`. */
export function parseVersion(search: string): ExplorerVersion {
  return resolveVersion(new URLSearchParams(search).get(VERSION_PARAM));
}

function ontologyParams(search: string): URLSearchParams {
  const incoming = new URLSearchParams(search);
  const next = new URLSearchParams();
  next.set(VERSION_PARAM, resolveVersion(incoming.get(VERSION_PARAM)));
  if (incoming.has(TAB_PARAM)) {
    next.set(TAB_PARAM, incoming.get(TAB_PARAM) ?? "");
  }
  if (incoming.has(ENTITY_PARAM)) {
    next.set(ENTITY_PARAM, incoming.get(ENTITY_PARAM) ?? "");
  }
  return next;
}

function serializeSearch(params: URLSearchParams): string {
  const text = params.toString();
  return text ? `?${text}` : "";
}

/** Preserve a legal `v` (iot2 or marketing); anything else normalizes to `v=iot2`. */
export function canonicalizeSearch(search: string): string {
  const incoming = new URLSearchParams(search);
  const next = new URLSearchParams();
  next.set(VERSION_PARAM, resolveVersion(incoming.get(VERSION_PARAM)));
  const entity = incoming.get(ENTITY_PARAM);
  const tab = incoming.get(TAB_PARAM);
  if (entity) {
    next.set(TAB_PARAM, EDITOR_TAB);
    next.set(ENTITY_PARAM, entity);
  } else if (tab) {
    next.set(TAB_PARAM, tab);
  } else {
    next.set(TAB_PARAM, DEFAULT_TAB);
  }
  return serializeSearch(next);
}

export function applyTab(search: string, tab: string): string {
  const params = ontologyParams(search);
  params.set(TAB_PARAM, tab);
  return serializeSearch(params);
}

// A selected entity is only addressable from the editor, so the tab moves with it.
export function applyEntitySelection(search: string, entityUri: string): string {
  const params = ontologyParams(search);
  params.set(TAB_PARAM, EDITOR_TAB);
  params.set(ENTITY_PARAM, entityUri);
  return serializeSearch(params);
}

// Pairs with applyEntitySelection: an entity URI is resolved back to its owning ontology on
// load, so leaving a stale one behind when the active ontology changes reopens the old ontology.
export function removeEntitySelection(search: string): string {
  const params = ontologyParams(search);
  params.delete(ENTITY_PARAM);
  return serializeSearch(params);
}

// Switches the Explorer version, resetting to the default Ontology Hub tab.
export function applyVersion(search: string, version: ExplorerVersion): string {
  const params = ontologyParams(search);
  params.set(VERSION_PARAM, version);
  params.set(TAB_PARAM, DEFAULT_TAB);
  params.delete(ENTITY_PARAM);
  return serializeSearch(params);
}

/**
 * Deliberately dual-role, and the argument is what selects the role: given a
 * `search` string this is pure and total, delegating straight to
 * `parseOntologyUrlState`; called with no argument it reads live `window`
 * state and yields empty state if the URL is unreadable. Callers in render or
 * effect paths use the no-argument form; tests and any caller that already
 * holds a search string pass it, which is the only form that is testable.
 */
export function readOntologyUrlState(search?: string): OntologyUrlState {
  if (search !== undefined) {
    return parseOntologyUrlState(search);
  }
  try {
    return parseOntologyUrlState(window.location.search);
  } catch {
    return {};
  }
}

/** The live Explorer version from `window.location.search`, defaulting to `iot2`. */
export function readVersion(): ExplorerVersion {
  try {
    return parseVersion(window.location.search);
  } catch {
    return APP_VERSION;
  }
}

/** True when the URL addresses the Ontology Hub at all, even with blank parameter values. */
export function hasOntologyUrlState(search?: string): boolean {
  const { tab, entityUri } = readOntologyUrlState(search);
  return tab !== undefined || entityUri !== undefined;
}

// Always keep a legal v=. Unknown keys are dropped. The fragment is carried across.
function updateSearch(transform: (search: string) => string): void {
  try {
    const path = window.location.pathname || "/";
    window.history.replaceState(
      null,
      "",
      `${path}${transform(window.location.search)}${window.location.hash}`,
    );
  } catch {
    // Deep-link state is a convenience; every caller stays correct without it.
  }
}

export function canonicalizeExplorerUrl(): void {
  try {
    const current = window.location.search;
    const next = canonicalizeSearch(current);
    if (next === current || (next === "" && current === "")) {
      return;
    }
    updateSearch(() => next);
  } catch {
    // Deep-link state is a convenience; every caller stays correct without it.
  }
}

export function writeTab(tab: string): void {
  updateSearch((search) => applyTab(search, tab));
}

export function writeEntitySelection(entityUri: string): void {
  updateSearch((search) => applyEntitySelection(search, entityUri));
}

export function clearEntitySelection(): void {
  updateSearch(removeEntitySelection);
}

export function switchVersion(version: ExplorerVersion): void {
  updateSearch((search) => applyVersion(search, version));
}
