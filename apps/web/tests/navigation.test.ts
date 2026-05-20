import assert from "node:assert/strict";
import test from "node:test";

import {
  buildEnzymeNavigation,
  primaryNavigationItems,
  utilityNavigationItems
} from "../lib/navigation.ts";

test("primary navigation exposes top-level workbench destinations", () => {
  assert.deepEqual(
    primaryNavigationItems.map((item) => [item.label, item.href]),
    [
      ["Dashboard", "/"],
      ["Search", "/search"],
      ["Curation", "/curation"]
    ]
  );
});

test("utility navigation exposes account destinations", () => {
  assert.deepEqual(
    utilityNavigationItems.map((item) => [item.label, item.href]),
    [["Sign in", "/login"]]
  );
});

test("enzyme navigation links detail, structures, analysis, and wet-lab data for the same enzyme", () => {
  assert.deepEqual(
    buildEnzymeNavigation("enzyme-123").map((item) => [item.label, item.href]),
    [
      ["Detail", "/enzymes/enzyme-123"],
      ["Structures", "/enzymes/enzyme-123/structures"],
      ["Analysis", "/enzymes/enzyme-123/analysis"],
      ["Wet-lab data", "/enzymes/enzyme-123/experiments"]
    ]
  );
});
