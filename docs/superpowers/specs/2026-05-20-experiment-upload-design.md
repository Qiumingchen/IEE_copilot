# Epic 12 Experiment Upload Design

## Goal

Add the first production-ready backend loop for wet-lab experiment uploads: parse tabular experiment data, validate required fields and mutation strings, map mutation positions against the mature engineering sequence, and persist private user experiments.

## Scope

This slice implements CSV-backed import first, then extends the same upload contract to `.xlsx` workbooks encoded as base64. The frontend upload page supports both `.csv` text files and `.xlsx` workbooks through the same preview and save flow.

## API Shape

Add endpoints under the existing enzyme detail surface:

- `POST /enzymes/{enzyme_id}/experiments/import-preview`
- `POST /enzymes/{enzyme_id}/experiments/import`

Both endpoints require authentication. The import request includes `project_id` and `csv_text`. The project must belong to the current user.

## Parsing And Validation

The parser reads CSV with headers and returns the field list plus normalized row results. A row must include `mutation_string` unless it is wild type (`WT`). It can either use generic `measured_property` and `measured_value` fields, or PRD property columns such as `specific_activity`, `relative_activity`, `opt_temperature`, and `opt_pH`. `visibility` defaults to `private`.

Mutation strings are parsed with the existing mutation parser. Non-WT mutations are validated against the enzyme's mature sequence when available, otherwise the stored sequence.

## Persistence

Validated property values become `UserExperiment` rows with assay context stored in `assay_condition_json`. Imported data starts as `UNREVIEWED` and private unless the upload explicitly requests another valid visibility value.

## Testing

Use TDD:

- service tests for parsing, field validation, row expansion, and mutation mismatch errors
- API tests for preview, project ownership checks, import persistence, and validation error responses
