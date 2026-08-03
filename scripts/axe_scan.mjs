import { readFileSync } from "node:fs";
import puppeteer from "puppeteer-core";

const browser = await puppeteer.launch({
  executablePath: "/usr/bin/google-chrome",
  headless: "new", args: ["--no-sandbox", "--disable-gpu"],
});
const page = await browser.newPage();
await page.goto(process.argv[2] || "http://localhost:8123", { waitUntil: "networkidle2", timeout: 30000 });
await page.evaluate(readFileSync(new URL("./node_modules/axe-core/axe.min.js", import.meta.url), "utf8"));
const results = await page.evaluate(async () => await axe.run(document, {
  runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "section508"] },
}));
console.log(`violations: ${results.violations.length}`);
for (const v of results.violations) {
  console.log(`- [${v.impact}] ${v.id}: ${v.help} (${v.nodes.length} nodes)`);
  for (const n of v.nodes.slice(0, 3)) console.log(`    ${n.target.join(" ")}`);
}
await browser.close();
process.exit(results.violations.length ? 1 : 0);
