// Compile inline scripts without running the browser UI or requiring a bundler.
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const html = fs.readFileSync(path.join(__dirname, "../web/index.html"), "utf8");
let count = 0;
for (const match of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)) {
  if (/\bsrc\s*=/.test(match[1])) continue;
  new vm.Script(match[2], { filename: `web/index.html:inline-${++count}` });
}
if (!count) throw new Error("No inline scripts found");
console.log(`Compiled ${count} inline browser script(s)`);
