#!/usr/bin/env node

const major = Number(process.versions.node.split('.')[0] || 0);

if (!Number.isFinite(major) || major < 20) {
  console.error(
    `\n[web] Unsupported Node.js version: ${process.version}\n` +
    '[web] Use Node 20.x or 22.x for Next.js 14 dev stability.\n' +
    '[web] Example with nvm:\n' +
    '  nvm install 20\n' +
    '  nvm use 20\n'
  );
  process.exit(1);
}

