import assert from "node:assert/strict";
import test from "node:test";

import {
  buildEnzymeNavigation,
  buildPageBreadcrumbs,
  isNavigationItemActive,
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

test("enzyme navigation links detail, structures, properties, mutations, analysis, and wet-lab data for the same enzyme", () => {
  assert.deepEqual(
    buildEnzymeNavigation("enzyme-123").map((item) => [item.label, item.href]),
    [
      ["Overview", "/enzymes/enzyme-123"],
      ["User uploads", "/enzymes/enzyme-123/upload"],
      ["Structures", "/enzymes/enzyme-123/structures"],
      ["Properties", "/enzymes/enzyme-123/properties"],
      ["Mutations", "/enzymes/enzyme-123/mutations"],
      ["Analysis", "/enzymes/enzyme-123/analysis"],
      ["Wet-lab data", "/enzymes/enzyme-123/experiments"]
    ]
  );
});

test("navigation activity matches child routes without lighting unrelated roots", () => {
  assert.equal(isNavigationItemActive("/enzymes/enzyme-123/structures", "/enzymes/enzyme-123"), false);
  assert.equal(isNavigationItemActive("/enzymes/enzyme-123/structures", "/enzymes/enzyme-123/structures"), true);
  assert.equal(isNavigationItemActive("/enzymes/enzyme-123/structures/upload", "/enzymes/enzyme-123/structures"), true);
  assert.equal(isNavigationItemActive("/enzymes/enzyme-123", "/"), false);
  assert.equal(isNavigationItemActive("/", "/"), true);
});

test("breadcrumbs expose direct routes across top-level and enzyme pages", () => {
  assert.deepEqual(
    buildPageBreadcrumbs("/enzymes/enzyme-123/structures").map((item) => [item.label, item.href]),
    [
      ["Dashboard", "/"],
      ["Search", "/search"],
      ["Current enzyme", "/enzymes/enzyme-123"],
      ["Structures", "/enzymes/enzyme-123/structures"]
    ]
  );

  assert.deepEqual(
    buildPageBreadcrumbs("/curation").map((item) => [item.label, item.href]),
    [
      ["Dashboard", "/"],
      ["Curation", "/curation"]
    ]
  );
});
