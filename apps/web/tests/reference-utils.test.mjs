import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildReferenceHref,
  formatReferenceCitation,
  formatReferenceIdentifier
} from "../app/enzymes/[id]/reference-utils.ts";

test("buildReferenceHref links DOI and PMID references", () => {
  assert.equal(
    buildReferenceHref({
      doi: "10.1000/MixedCase",
      pubmed_id: null
    }),
    "https://doi.org/10.1000/MixedCase"
  );
  assert.equal(
    buildReferenceHref({
      doi: null,
      pubmed_id: "PMID: 123456"
    }),
    "https://pubmed.ncbi.nlm.nih.gov/123456/"
  );
  assert.equal(buildReferenceHref({ doi: null, pubmed_id: null }), null);
});

test("formatReferenceIdentifier normalizes DOI URLs and PubMed IDs", () => {
  assert.equal(formatReferenceIdentifier({ doi: "https://doi.org/10.1000/ABC", pubmed_id: null }), "10.1000/abc");
  assert.equal(formatReferenceIdentifier({ doi: null, pubmed_id: "pubmed 123456" }), "PMID 123456");
  assert.equal(formatReferenceIdentifier({ doi: null, pubmed_id: null }), null);
});

test("formatReferenceCitation includes title journal year and source", () => {
  assert.equal(
    formatReferenceCitation({
      id: "ref-1",
      title: "Traceable MTGase evidence",
      authors: null,
      journal: "Biocatalysis Reports",
      year: 2024,
      doi: "10.1000/traceable",
      pubmed_id: null,
      source: "curated_literature",
      provenance: { mode: "curated" }
    }),
    "10.1000/traceable | Traceable MTGase evidence | Biocatalysis Reports | 2024 | curated_literature"
  );
});
