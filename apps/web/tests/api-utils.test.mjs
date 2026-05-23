import assert from "node:assert/strict";
import test from "node:test";

import { apiUrl, discoverEnzymeFromPdb } from "../lib/api.ts";

test("apiUrl uses the same-origin backend proxy by default", () => {
  assert.equal(apiUrl("/auth/login"), "/api/backend/auth/login");
  assert.equal(apiUrl("enzymes/search"), "/api/backend/enzymes/search");
});

test("discoverEnzymeFromPdb submits only the uploaded structure file", async () => {
  const originalFetch = globalThis.fetch;
  let submittedBody;
  globalThis.fetch = async (_url, init) => {
    submittedBody = init.body;
    return new Response(
      JSON.stringify({
        file_name: "query.pdb",
        metadata: {},
        structure_type: "pdb",
        complex_state: "apo",
        chains: [],
        query_chain_id: "A",
        query_sequence: "",
        hits: []
      }),
      { status: 200, headers: { "content-type": "application/json" } }
    );
  };

  try {
    await discoverEnzymeFromPdb(new File(["ATOM"], "query.pdb", { type: "chemical/x-pdb" }), "token");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(submittedBody.get("file").name, "query.pdb");
  assert.equal(submittedBody.has("module"), false);
});
