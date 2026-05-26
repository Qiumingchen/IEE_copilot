import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const searchPageSource = readFileSync(new URL("../app/search/page.tsx", import.meta.url), "utf8");

test("search page does not show cache or retrieval diagnostics in the result view", () => {
  assert.equal(searchPageSource.includes("cache_status"), false);
  assert.equal(searchPageSource.includes("Retrieval source"), false);
  assert.equal(searchPageSource.includes("Query kind"), false);
  assert.equal(searchPageSource.includes("formatSearchProvenanceSummary"), false);
});
