// Development-only screenshot capture. See docs/USER_GUIDE.md for reproduction.
// All local requests are intercepted: no running companion or Foundry is touched.
const { chromium } = require("playwright");
const fs = require("node:fs/promises");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const session = "Session 1 - The Missing Lantern";
const note = `# The Missing Lantern

The beacon at Lantern Quay has gone dark. Mira Reed asks the party to recover
its lens before tonight's boats arrive.

## People and places
- [[Mira Reed]] keeps the quay's signal tower.
- [[Lantern Keepers]] maintain the lights.
- [[Lantern Quay]] is home to [[Tavi Finch]].

## Encounters
- [[Encounter - A Light at the Quay]]

## Questions for the table
Who last saw the lens? What would you risk to guide the boats home?`;
const encounter = {
  name: "Encounter - A Light at the Quay", title: "A Light at the Quay",
  found: true, meta: { type: "Social", difficulty: "Low", location: "Lantern Quay" },
  scene: "Lantern Quay", npcs: ["Mira Reed"],
  markdown: `**Scene**: Lantern Quay\n**NPCs**: [[Mira Reed]]\n
## Overview
The keeper offers a brass token for news of the missing lens.

## Leads
- A trail of blue wax leads toward the old ferry.
- [[Tavi Finch]] heard a bell after midnight.

## Resolution
Return the lens, negotiate a replacement, or signal the boats from shore.`,
};
const endpoints = {
  "/api/sessions": { sessions: [session] },
  "/api/encounters": { session, encounters: [encounter] },
  "/api/note": { session, markdown: note },
  "/api/npcs": { npcs: [{ name: "Mira Reed", target: "NPCs/Mira Reed",
    race: "Human", occupation: "Beacon keeper", faction: "[[Lantern Keepers]]",
    location: "[[Lantern Quay]]", summary: "Patient, practical, and worried about the boats." }] },
  "/api/players": { players: [], dashboard: null },
};

async function main() {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.route("http://127.0.0.1:4100/**", async route => {
      const pathname = new URL(route.request().url()).pathname;
      if (pathname === "/") {
        await route.fulfill({ contentType: "text/html", body: await fs.readFile(path.join(root, "web/index.html"), "utf8") });
      } else if (endpoints[pathname]) {
        await route.fulfill({ json: endpoints[pathname] });
      } else {
        await route.fulfill({ status: 404, body: "No screenshot fixture" });
      }
    });
    await page.routeWebSocket("ws://127.0.0.1:4100/ws/ui", ws => {
      ws.send(JSON.stringify({
        type: "state", foundryConnected: false, foundry: {}, scenes: [],
        combat: null, favorites: [],
        clocks: [
          { id: "beacon", name: "Repair the beacon", segments: 6, filled: 2, visible: true },
          { id: "boats", name: "Boats reach the shoals", segments: 4, filled: 1, visible: false },
        ],
        showcase: { items: [], layout: "column", view: "corner" },
      }));
    });
    await page.goto("http://127.0.0.1:4100/", { waitUntil: "networkidle" });
    await page.waitForFunction(() => typeof marked !== "undefined" && document.querySelector("#session-select").value);
    await page.evaluate(() => document.fonts.ready);
    // Confirm the CDN styles loaded rather than capturing an unstyled page.
    await page.waitForFunction(() => getComputedStyle(document.querySelector("#nav")).display !== "block");
    await page.addStyleTag({ content: "*, *::before, *::after { transition: none !important; animation: none !important; }" });
    const output = path.join(__dirname, "images");
    await fs.mkdir(output, { recursive: true });
    for (const view of ["notes", "encounters", "clocks"]) {
      await page.locator(`[data-view="${view}"]`).click();
      if (view === "encounters") {
        await page.locator("#view summary").first().click();
        await page.getByText("The keeper offers a brass token for news of the missing lens.").waitFor({ state: "visible" });
        await page.waitForFunction(() => document.querySelector("#view details").getBoundingClientRect().height > 350);
      }
      await page.screenshot({ path: path.join(output, `${view}.png`), fullPage: true, animations: "disabled" });
    }
    if (errors.length) throw new Error(errors.join("\n"));
    console.log("Captured three guide screenshots using fictional fixtures.");
  } finally {
    await browser.close();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
