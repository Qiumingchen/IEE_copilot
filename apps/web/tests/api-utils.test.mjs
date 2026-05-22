import assert from "node:assert/strict";
import test from "node:test";

import { apiUrl } from "../lib/api.ts";

test("apiUrl uses the same-origin backend proxy by default", () => {
  assert.equal(apiUrl("/auth/login"), "/api/backend/auth/login");
  assert.equal(apiUrl("enzymes/search"), "/api/backend/enzymes/search");
});
