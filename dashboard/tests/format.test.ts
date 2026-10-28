import { expect, it } from "vitest";
import { formatDay, formatPhone, formatTime, formatWhen, whatsappParts } from "@/lib/format";

const now = new Date("2026-10-28T06:00:00Z"); // 11:30 am in India

it("shows India time", () => {
  expect(formatTime("2026-10-28T05:35:00Z")).toBe("11:05 am");
  expect(formatWhen("2026-10-28T05:35:00Z", now)).toBe("11:05 am");
  expect(formatWhen("2026-10-26T10:00:00Z", now)).toBe("26 Oct");
  expect(formatWhen("2025-12-31T10:00:00Z", now)).toBe("31 Dec 2025");
  // 7:00 pm UTC on the 27th is already 12:30 am on the 28th in India
  expect(formatDay("2026-10-27T19:00:00Z", now)).toBe("Today");
  expect(formatDay("2026-10-27T10:00:00Z", now)).toBe("Yesterday");
});

it("formats Indian numbers", () => {
  expect(formatPhone("919812345678")).toBe("+91 98123 45678");
  expect(formatPhone("447700900123")).toBe("+447700900123");
});

it("splits WhatsApp formatting without HTML", () => {
  expect(whatsappParts("*Green Valley*\n\n2BHK: _5 left_ <b>x</b>")).toEqual([
    { text: "Green Valley", style: "bold" },
    { text: "\n\n2BHK: " },
    { text: "5 left", style: "italic" },
    { text: " <b>x</b>" },
  ]);
});
