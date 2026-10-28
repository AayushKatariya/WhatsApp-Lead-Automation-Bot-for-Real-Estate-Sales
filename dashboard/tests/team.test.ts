import { beforeAll, expect, it } from "vitest";
import { findUser, listTeam, parseEmails, parseMemberForm, removeMember, saveMember } from "@/lib/team";
import { testDb } from "./db";

let db: Awaited<ReturnType<typeof testDb>>;
beforeAll(async () => {
  db = await testDb();
});

function form(fields: Record<string, string | string[]>) {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) for (const v of [value].flat()) data.append(key, v);
  return data;
}

it("reads OWNER_EMAILS", () => {
  expect(parseEmails(" Boss@Gmail.com, x ; second@y.in\nboss@gmail.com")).toEqual(["boss@gmail.com", "second@y.in"]);
});

it("checks the Team form", () => {
  expect(parseMemberForm(form({ email: " Rahul@Gmail.com ", name: "Rahul", role: "sales", sites: ["GV"], other_sites: "SH, GV" })))
    .toEqual({ email: "rahul@gmail.com", name: "Rahul", role: "sales", siteIds: ["GV", "SH"] });
  expect(parseMemberForm(form({ email: "a@b.co", role: "owner", sites: "GV" }))).toMatchObject({ role: "owner", siteIds: [] });
  expect(parseMemberForm(form({ email: "nope", role: "sales", sites: "GV" }))).toHaveProperty("error");
  expect(parseMemberForm(form({ email: "a@b.co", role: "admin" }))).toHaveProperty("error");
  expect(parseMemberForm(form({ email: "a@b.co", role: "sales" }))).toEqual({ error: "Tick at least one project for a sales rep." });
  expect(parseMemberForm(form({ email: "a@b.co", role: "sales", other_sites: "G V'; DROP" }))).toHaveProperty("error");
});

it("lets in owners from the settings and people on the team list, nobody else", async () => {
  await saveMember(db, { email: "rahul@gmail.com", name: "Rahul", role: "sales", siteIds: ["GV"] });
  expect(await findUser(db, "boss@gmail.com", ["boss@gmail.com"])).toMatchObject({ role: "owner" });
  expect(await findUser(db, "RAHUL@gmail.com", [])).toEqual({
    email: "rahul@gmail.com",
    name: "Rahul",
    role: "sales",
    siteIds: ["GV"],
  });
  expect(await findUser(db, "stranger@gmail.com", ["boss@gmail.com"])).toBeNull();

  await saveMember(db, { email: "rahul@gmail.com", name: "Rahul P", role: "sales", siteIds: ["GV", "SH"] });
  expect(await listTeam(db)).toEqual([{ email: "rahul@gmail.com", name: "Rahul P", role: "sales", site_ids: ["GV", "SH"] }]);
  await removeMember(db, "Rahul@Gmail.com");
  expect(await findUser(db, "rahul@gmail.com", [])).toBeNull();
});
