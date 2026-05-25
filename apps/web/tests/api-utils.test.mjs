import assert from "node:assert/strict";
import test from "node:test";

import {
  apiUrl,
  cancelJob,
  discoverEnzymeFromPdb,
  getEnzymeRecordBundle,
  refreshEnzymeFamilyRealData,
  searchEnzyme
} from "../lib/api.ts";

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

test("searchEnzyme sends the requested result limit", async () => {
  const originalFetch = globalThis.fetch;
  let submittedBody;
  globalThis.fetch = async (_url, init) => {
    submittedBody = JSON.parse(init.body);
    return new Response(
      JSON.stringify({
        enzyme: {},
        matches: [],
        job_id: "job-1",
        cache_status: "miss_refreshed",
        query_kind: "keyword",
        module: "MICROBIAL_TRANSGLUTAMINASE_MATURE"
      }),
      { status: 200, headers: { "content-type": "application/json" } }
    );
  };

  try {
    await searchEnzyme("food lipase", "token", 20, "Bacillus subtilis");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(submittedBody, {
    query: "food lipase",
    result_limit: 20,
    organism: "Bacillus subtilis"
  });
});

test("getEnzymeRecordBundle fetches same-family enzyme entries", async () => {
  const originalFetch = globalThis.fetch;
  const requestedUrls = [];
  globalThis.fetch = async (url) => {
    requestedUrls.push(url);
    const payload = url.endsWith("/family-entries")
      ? [
          {
            id: "enzyme-2",
            family_id: "family-1",
            family_name: "Food lipases",
            name: "Food lipase Geobacillus",
            organism: "Geobacillus stearothermophilus",
            ec_number: "3.1.1.3",
            uniprot_id: "LIP002",
            pdb_id: null,
            alphafold_id: null,
            source: "uniprot",
            uniprot_reviewed: false,
            optimal_temperature: null,
            specific_activity: null,
            record_counts: { properties: 0, kinetics: 0, mutations: 0, structures: 0, expression: 0 }
          }
        ]
      : url.endsWith("/enzymes/enzyme-1")
        ? {
            id: "enzyme-1",
            family_id: "family-1",
            family_name: "Food lipases",
            name: "Food lipase Bacillus",
            organism: "Bacillus subtilis",
            ec_number: "3.1.1.3",
            uniprot_id: "LIP001",
            pdb_id: null,
            alphafold_id: null,
            source: "uniprot",
            uniprot_reviewed: true,
            optimal_temperature: null,
            specific_activity: null,
            record_counts: { properties: 0, kinetics: 0, mutations: 0, structures: 0, expression: 0 }
          }
        : [];
    return new Response(JSON.stringify(payload), {
      status: 200,
      headers: { "content-type": "application/json" }
    });
  };

  let bundle;
  try {
    bundle = await getEnzymeRecordBundle("enzyme-1", "token");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(bundle.family_entries.length, 1);
  assert.equal(bundle.family_entries[0].id, "enzyme-2");
  assert.ok(requestedUrls.includes("/api/backend/enzymes/enzyme-1/family-entries"));
});

test("refreshEnzymeFamilyRealData posts to the async family refresh job endpoint", async () => {
  const originalFetch = globalThis.fetch;
  let requestedUrl;
  let requestedMethod;
  globalThis.fetch = async (url, init) => {
    requestedUrl = url;
    requestedMethod = init.method;
    return new Response(
      JSON.stringify({
        id: "job-1",
        project_id: null,
        enzyme_entry_id: "enzyme-1",
        job_type: "real_data_refresh",
        status: "queued",
        parameters_json: { scope: "family" },
        result_summary_json: null,
        error_message: null,
        created_by: "user-1",
        created_at: "2026-05-25T00:00:00",
        started_at: null,
        finished_at: null
      }),
      { status: 200, headers: { "content-type": "application/json" } }
    );
  };

  try {
    await refreshEnzymeFamilyRealData("enzyme-1", "token");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(requestedUrl, "/api/backend/enzymes/enzyme-1/family-real-data/refresh-job");
  assert.equal(requestedMethod, "POST");
});

test("cancelJob posts to the job cancellation endpoint", async () => {
  const originalFetch = globalThis.fetch;
  let requestedUrl;
  let requestedMethod;
  globalThis.fetch = async (url, init) => {
    requestedUrl = url;
    requestedMethod = init.method;
    return new Response(
      JSON.stringify({
        id: "job-2",
        project_id: null,
        enzyme_entry_id: "enzyme-1",
        job_type: "real_data_refresh",
        status: "cancelled",
        parameters_json: { scope: "family" },
        result_summary_json: null,
        error_message: null,
        created_by: "user-1",
        created_at: "2026-05-25T00:00:00",
        started_at: "2026-05-25T00:01:00",
        finished_at: "2026-05-25T00:02:00"
      }),
      { status: 200, headers: { "content-type": "application/json" } }
    );
  };

  try {
    await cancelJob("job-2", "token");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(requestedUrl, "/api/backend/jobs/job-2/cancel");
  assert.equal(requestedMethod, "POST");
});
