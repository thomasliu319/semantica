import assert from "node:assert/strict";
import test from "node:test";

import {
  applyEntitySelection,
  applyTab,
  canonicalizeExplorerUrl,
  canonicalizeSearch,
  clearEntitySelection,
  hasOntologyUrlState,
  parseOntologyUrlState,
  readOntologyUrlState,
  removeEntitySelection,
  writeEntitySelection,
  writeTab,
} from "../src/workspaces/OntologyWorkspace/ontologyUrlState";

function withStubbedLocation(search: string, hash: string, body: () => void): string[] {
  const written: string[] = [];
  const original = (globalThis as { window?: unknown }).window;
  const location = { search, hash, pathname: "/" };
  (globalThis as { window?: unknown }).window = {
    location,
    history: {
      replaceState: (_s: unknown, _t: string, url: string) => {
        written.push(url);
        const parsed = new URL(url, "http://127.0.0.1");
        location.search = parsed.search;
        location.hash = parsed.hash;
        location.pathname = parsed.pathname;
      },
    },
  };
  try {
    body();
  } finally {
    (globalThis as { window?: unknown }).window = original;
  }
  return written;
}

test("selecting an entity round-trips and pins the editor tab", () => {
  const search = applyEntitySelection("", "https://example.test/foo#Bar");
  assert.deepEqual(parseOntologyUrlState(search), {
    tab: "editor",
    entityUri: "https://example.test/foo#Bar",
  });
  assert.equal(search.startsWith("?v=iot2&"), true);
});

test("writers keep v=iot2 and drop other versions", () => {
  const search = applyEntitySelection("?v=metrics1&view=graph", "https://example.test/foo#Bar");
  assert.equal(
    search,
    "?v=iot2&ontologyTab=editor&ontologyEntity=https%3A%2F%2Fexample.test%2Ffoo%23Bar",
  );
  const cleared = removeEntitySelection(search);
  assert.equal(cleared, "?v=iot2&ontologyTab=editor");
  assert.equal(parseOntologyUrlState(cleared).entityUri, undefined);
});

test("writing a tab leaves an existing entity selection alone", () => {
  const search = applyTab(applyEntitySelection("", "urn:x"), "health");
  assert.deepEqual(parseOntologyUrlState(search), { tab: "health", entityUri: "urn:x" });
});

test("/ and leftover v= params canonicalize to the IoT registry URL", () => {
  assert.equal(canonicalizeSearch(""), "?v=iot2&ontologyTab=registry");
  assert.equal(canonicalizeSearch("?v=iot2"), "?v=iot2&ontologyTab=registry");
  assert.equal(canonicalizeSearch("?v=metrics1"), "?v=iot2&ontologyTab=registry");
  assert.equal(canonicalizeSearch("?v=iot2&ontologyTab=health"), "?v=iot2&ontologyTab=health");
  assert.equal(canonicalizeSearch("?v=iot2&ontologyTab=registry"), "?v=iot2&ontologyTab=registry");
  assert.equal(
    canonicalizeSearch("?ontologyEntity=urn%3Ax"),
    "?v=iot2&ontologyTab=editor&ontologyEntity=urn%3Ax",
  );
});

test("absent params read as undefined, blank params as empty strings", () => {
  assert.deepEqual(parseOntologyUrlState(""), { tab: undefined, entityUri: undefined });
  assert.deepEqual(parseOntologyUrlState("?other=1"), { tab: undefined, entityUri: undefined });
  assert.deepEqual(parseOntologyUrlState("?ontologyTab=&ontologyEntity="), {
    tab: "",
    entityUri: "",
  });
});

test("a present but blank param still counts as ontology deep-link state", () => {
  assert.equal(hasOntologyUrlState("?ontologyEntity="), true);
  assert.equal(hasOntologyUrlState("?ontologyTab="), true);
  assert.equal(hasOntologyUrlState("?view=graph"), false);
  assert.equal(hasOntologyUrlState(""), false);
});

test("malformed search strings degrade to plain values instead of throwing", () => {
  assert.deepEqual(parseOntologyUrlState("???"), { tab: undefined, entityUri: undefined });
  assert.deepEqual(parseOntologyUrlState("ontologyEntity=urn%3Ax&&=&"), {
    tab: undefined,
    entityUri: "urn:x",
  });
});

test("entity URIs survive characters that need escaping", () => {
  const entityUri = "https://example.test/vocab#Has Part/&?=";
  const search = applyEntitySelection("?keep=1", entityUri);
  assert.equal(parseOntologyUrlState(search).entityUri, entityUri);
});

test("every writer preserves the URL fragment and pins v=iot2", () => {
  const written = withStubbedLocation("?v=metrics1", "#section-3", () => {
    writeTab("health");
    writeEntitySelection("urn:x");
    clearEntitySelection();
  });

  assert.deepEqual(written, [
    "/?v=iot2&ontologyTab=health#section-3",
    "/?v=iot2&ontologyTab=editor&ontologyEntity=urn%3Ax#section-3",
    "/?v=iot2&ontologyTab=editor#section-3",
  ]);
});

test("canonicalizeExplorerUrl upgrades / to the IoT registry URL", () => {
  const written = withStubbedLocation("", "", () => {
    canonicalizeExplorerUrl();
  });
  assert.deepEqual(written, ["/?v=iot2&ontologyTab=registry"]);
});

test("readOntologyUrlState with no argument reads live URL state", () => {
  withStubbedLocation("?ontologyTab=editor&ontologyEntity=urn%3Ax", "", () => {
    assert.deepEqual(readOntologyUrlState(), { tab: "editor", entityUri: "urn:x" });
    assert.equal(hasOntologyUrlState(), true);
  });
});
