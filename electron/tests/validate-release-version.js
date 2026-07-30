"use strict";

const fs = require("fs");
const path = require("path");

const ELECTRON_ROOT = path.resolve(__dirname, "..");
const PACKAGE_PATH = path.join(ELECTRON_ROOT, "package.json");
const LOCK_PATH = path.join(ELECTRON_ROOT, "package-lock.json");
const STABLE_SEMVER = /^\d+\.\d+\.\d+$/;

const results = [];
function check(name, actual, expected, predicate = (value, target) => value === target) {
  results.push({ name, actual, expected, passed: Boolean(predicate(actual, expected)) });
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function main() {
  const expectedVersion = String(process.argv[2] || "").trim();
  check("expected version argument", expectedVersion, "stable semver", (value) => STABLE_SEMVER.test(value));
  check("package.json exists", fs.existsSync(PACKAGE_PATH), true);
  check("package-lock.json exists", fs.existsSync(LOCK_PATH), true);

  if (!fs.existsSync(PACKAGE_PATH) || !fs.existsSync(LOCK_PATH) || !STABLE_SEMVER.test(expectedVersion)) {
    return finish();
  }

  const packageJson = readJson(PACKAGE_PATH);
  const lockJson = readJson(LOCK_PATH);
  const lockRoot = lockJson.packages?.[""] || {};
  const expectedTag = `electron-v${expectedVersion}`;
  const artifactTemplate = packageJson.build?.artifactName || "";
  const artifactName = artifactTemplate
    .replace("${version}", expectedVersion)
    .replace("${ext}", "exe");

  check("package name", packageJson.name, "kdrg-v47-relation-search-electron");
  check("package version", packageJson.version, expectedVersion);
  check("lock top version", lockJson.version, expectedVersion);
  check("lock root version", lockRoot.version, expectedVersion);
  check("lock top name", lockJson.name, packageJson.name);
  check("lock root name", lockRoot.name, packageJson.name);
  check("lockfileVersion", lockJson.lockfileVersion, 3);
  check("artifact template uses version", artifactTemplate.includes("${version}"), true);
  check(
    "portable artifact name",
    artifactName,
    `KDRG_V47_Relation_Search_Electron_${expectedVersion}_Portable.exe`,
  );
  check("release tag", expectedTag, `electron-v${expectedVersion}`);
  check("version has no prerelease", packageJson.version, "stable semver", (value) => STABLE_SEMVER.test(value));
  return finish();
}

function finish() {
  const failed = results.filter((item) => !item.passed);
  for (const item of results) {
    const status = item.passed ? "PASS" : "FAIL";
    console.log(`[${status}] ${item.name} | actual=${JSON.stringify(item.actual)} | expected=${JSON.stringify(item.expected)}`);
  }
  if (failed.length) {
    console.log(`[FAIL] Electron release version 검증: ${results.length - failed.length} PASS / ${failed.length} FAIL`);
    return 1;
  }
  console.log(`[PASS] Electron release version 검증: ${results.length} PASS / 0 FAIL`);
  return 0;
}

process.exitCode = main();
