#!/usr/bin/env node
 
const fs = require("fs");
const path = require("path");

function rmDirRecursive(targetPath) {
  if (!fs.existsSync(targetPath)) return;

  for (const entry of fs.readdirSync(targetPath)) {
    const entryPath = path.join(targetPath, entry);
    const stat = fs.lstatSync(entryPath);

    if (stat.isDirectory() && !stat.isSymbolicLink()) {
      rmDirRecursive(entryPath);
      continue;
    }

    fs.unlinkSync(entryPath);
  }

  fs.rmdirSync(targetPath);
}

const nextDir = path.join(__dirname, "..", ".next");

try {
  if (!fs.existsSync(nextDir)) {
    console.log("No .next directory at", nextDir);
    process.exit(0);
  }
  rmDirRecursive(nextDir);
  console.log("Removed", nextDir);
} catch (error) {
  console.error("Failed to remove", nextDir);
  console.error(error);
  process.exit(1);
}
