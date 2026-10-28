import type { PGlite } from "@electric-sql/pglite";
import { beforeAll, beforeEach, describe, expect, it } from "vitest";
import { getLead, getTimeline, listLeads, listProjects, PAGE_SIZE } from "@/lib/leads";
import type { Db, User } from "@/lib/types";
import { contact, event, message, reset, testDb } from "./db";

const GV: [string, string] = ["GV", "Green Valley Residency"];
const SH: [string, string] = ["SH", "Sunrise Heights"];
const owner: User = { email: "owner@x.com", name: "Owner", role: "owner", siteIds: [] };
const gvRep: User = { email: "rahul@x.com", name: "Rahul", role: "sales", siteIds: ["GV"] };
const noProjects: User = { email: "new@x.com", name: "", role: "sales", siteIds: [] };

let db: PGlite & Db;
beforeAll(async () => {
  db = await testDb();
});

describe("leads with three customers", () => {
  beforeEach(async () => {
    await reset(db);
    // Priya: Green Valley, wants a visit
    await contact(db, "919800000001", "Priya");
    await message(db, "919800000001", "in", "text", "hi");
    await event(db, "919800000001", "site_selected", GV);
    await event(db, "919800000001", "visit_request", GV, "Wants a site visit");
    // Amit: Sunrise Heights only, asked the price
    await contact(db, "919800000002", "Amit");
    await message(db, "919800000002", "in", "text", "What is the 100% price of 3 BHK?");
    await event(db, "919800000002", "price_request", SH);
    // a newcomer who never picked a project
    await contact(db, "919800000003", "");
    await message(db, "919800000003", "in", "audio", "");
    await message(db, "919800000003", "out", "text", "I can read text messages only.");
  });

  it("shows owners everyone, newest first, with projects and events", async () => {
    const { leads, hasMore } = await listLeads(db, owner, {});
    expect(leads.map((l) => l.phone)).toEqual(["919800000003", "919800000002", "919800000001"]);
    expect(hasMore).toBe(false);
    const priya = leads[2];
    expect(priya.sites).toEqual(["Green Valley Residency"]);
    expect(priya.events.sort()).toEqual(["site_selected", "visit_request"]);
    expect(leads[0]).toMatchObject({ last_direction: "out", last_body: "I can read text messages only." });
    expect(leads[0].sites).toEqual([]);
  });

  it("shows a sales rep only leads of their projects, whatever the filters say", async () => {
    expect((await listLeads(db, gvRep, {})).leads.map((l) => l.name)).toEqual(["Priya"]);
    expect((await listLeads(db, gvRep, { site: "SH" })).leads).toEqual([]);
    expect((await listLeads(db, gvRep, { q: "price" })).leads).toEqual([]);
    expect((await listLeads(db, noProjects, {})).leads).toEqual([]);
  });

  it("opens a lead only for people allowed to see it", async () => {
    expect(await getLead(db, gvRep, "919800000001")).toMatchObject({ name: "Priya", sites: ["Green Valley Residency"] });
    expect(await getLead(db, gvRep, "919800000002")).toBeNull();
    expect(await getLead(db, owner, "919800000002")).toMatchObject({ name: "Amit" });
    expect(await getLead(db, owner, "910000000000")).toBeNull();
  });

  it("searches names, message text and phone digits; % and _ are plain characters", async () => {
    const names = async (q: string) => (await listLeads(db, owner, { q })).leads.map((l) => l.name);
    expect(await names("priya")).toEqual(["Priya"]);
    expect(await names("3 bhk")).toEqual(["Amit"]);
    expect(await names("100%")).toEqual(["Amit"]);
    expect(await names("_")).toEqual([]);
    expect(await names("98000 00002")).toEqual(["Amit"]);
  });

  it("filters by project and by needing follow-up", async () => {
    expect((await listLeads(db, owner, { site: "SH" })).leads.map((l) => l.name)).toEqual(["Amit"]);
    expect((await listLeads(db, owner, { followUp: true })).leads.map((l) => l.name)).toEqual(["Amit", "Priya"]);
  });

  it("lists the projects each user can filter by", async () => {
    expect(await listProjects(db, owner)).toEqual([
      { site_id: "GV", site_name: "Green Valley Residency" },
      { site_id: "SH", site_name: "Sunrise Heights" },
    ]);
    expect(await listProjects(db, gvRep)).toEqual([{ site_id: "GV", site_name: "Green Valley Residency" }]);
  });

  it("merges messages and events in time order", async () => {
    const timeline = await getTimeline(db, "919800000001");
    expect(timeline.map((t) => (t.type === "message" ? t.body : t.event))).toEqual([
      "hi",
      "site_selected",
      "visit_request",
    ]);
  });
});

it("pages through many leads", async () => {
  await reset(db);
  for (let i = 0; i < PAGE_SIZE + 3; i++) await contact(db, `9198000${String(i).padStart(5, "0")}`, `Lead ${i}`);
  const first = await listLeads(db, owner, {});
  const second = await listLeads(db, owner, { page: 2 });
  expect([first.leads.length, first.hasMore]).toEqual([PAGE_SIZE, true]);
  expect([second.leads.length, second.hasMore]).toEqual([3, false]);
});
