import assert from "node:assert/strict";
import test from "node:test";

import {
  buildStructureAnalysisHref,
  formatPdbDiscoveryMatchReason,
  formatPdbDiscoveryHitSubtitle,
  formatSearchMatchSubtitle,
  pdbDiscoveryErrorMessage,
  searchResultMatches
} from "../app/search/search-utils.ts";

const enzyme = {
  id: "enzyme-1",
  family_id: "family-1",
  name: "Microbial transglutaminase",
  organism: "Streptomyces mobaraensis",
  ec_number: "2.3.2.13",
  uniprot_id: "P81453",
  pdb_id: null,
  alphafold_id: null,
  source: "uniprot"
};

test("searchResultMatches falls back to the primary enzyme and deduplicates matches", () => {
  assert.deepEqual(
    searchResultMatches({
      enzyme,
      matches: [],
      job_id: "job-1",
      cache_status: "hit",
      query_kind: "keyword",
      module: "MICROBIAL_TRANSGLUTAMINASE_MATURE"
    }),
    [enzyme]
  );

  assert.deepEqual(
    searchResultMatches({
      enzyme,
      matches: [enzyme, enzyme, { ...enzyme, id: "enzyme-2", source: "curated_literature" }],
      job_id: "job-1",
      cache_status: "hit",
      query_kind: "keyword",
      module: "MICROBIAL_TRANSGLUTAMINASE_MATURE"
    }).map((match) => match.id),
    ["enzyme-1", "enzyme-2"]
  );
});

test("formatSearchMatchSubtitle combines organism identifiers and source details", () => {
  assert.equal(
    formatSearchMatchSubtitle({ ...enzyme, pdb_id: "1ABC", alphafold_id: "AF-P81453-F1" }),
    "Streptomyces mobaraensis | EC 2.3.2.13 | UniProt P81453 | RCSB PDB 1ABC | AlphaFold AF-P81453-F1"
  );
  assert.equal(
    formatSearchMatchSubtitle({ ...enzyme, organism: null, ec_number: null, uniprot_id: null }),
    "Source details not reported"
  );
});

test("formatPdbDiscoveryHitSubtitle summarizes similarity evidence for upload hits", () => {
  assert.equal(
    formatPdbDiscoveryHitSubtitle({
      enzyme,
      identity: 0.875,
      coverage: 0.75,
      aligned_length: 120,
      evidence: ["sequence_similarity", "local_database"],
      confidence: "high"
    }),
    "87.5% identity | 75.0% coverage | high confidence | sequence_similarity, local_database"
  );

  assert.equal(
    formatPdbDiscoveryHitSubtitle({
      enzyme,
      identity: 1,
      coverage: 1,
      aligned_length: 407,
      evidence: ["uniprot_id", "local_database"],
      confidence: "exact"
    }),
    "Identifier match | exact confidence | uniprot_id, local_database"
  );
});

test("formatPdbDiscoveryMatchReason explains exact identifier and sequence matches", () => {
  assert.equal(
    formatPdbDiscoveryMatchReason({
      enzyme,
      identity: 1,
      coverage: 1,
      aligned_length: 407,
      evidence: ["alphafold_id", "local_database"],
      confidence: "high"
    }),
    "Exact AlphaFold ID match"
  );

  assert.equal(
    formatPdbDiscoveryMatchReason({
      enzyme,
      identity: 1,
      coverage: 1,
      aligned_length: 407,
      evidence: ["uniprot_id", "local_database"],
      confidence: "exact"
    }),
    "Exact UniProt ID match"
  );

  assert.equal(
    formatPdbDiscoveryMatchReason({
      enzyme,
      identity: 0.875,
      coverage: 0.75,
      aligned_length: 120,
      evidence: ["sequence_similarity", "local_database"],
      confidence: "high"
    }),
    "Sequence similarity match"
  );
});

test("buildStructureAnalysisHref points discovery uploads at the selected structure", () => {
  assert.equal(
    buildStructureAnalysisHref("enzyme 1", "structure/2"),
    "/enzymes/enzyme%201/structures?structure_id=structure%2F2"
  );
});

test("pdbDiscoveryErrorMessage distinguishes authentication and parser failures", () => {
  assert.equal(
    pdbDiscoveryErrorMessage({ status: 401 }),
    "Your login session has expired. Please sign in again before uploading a PDB file."
  );
  assert.equal(
    pdbDiscoveryErrorMessage({ status: 422, detail: "uploaded structure does not contain a protein sequence" }),
    "uploaded structure does not contain a protein sequence"
  );
});
