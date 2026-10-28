-- Tables for the lead dashboard. The bot (history.py) writes contacts, messages and events;
-- the dashboard reads them and manages team.
-- Safe to run again: the dashboard applies this file automatically the first time it uses the database.
-- Change it only by adding (new tables, or ALTER TABLE ... ADD COLUMN IF NOT EXISTS at the end).

CREATE TABLE IF NOT EXISTS contacts (
  phone       text PRIMARY KEY,                    -- WhatsApp number as Meta sends it: digits only, e.g. 919812345678
  name        text NOT NULL DEFAULT '',            -- WhatsApp profile name
  first_seen  timestamptz NOT NULL DEFAULT now(),
  last_seen   timestamptz NOT NULL DEFAULT now()   -- the customer's latest message
);
CREATE INDEX IF NOT EXISTS contacts_last_seen ON contacts (last_seen DESC);

-- Messages and events share one id counter, so a conversation sorts in the exact order things happened.
CREATE SEQUENCE IF NOT EXISTS timeline_seq;

CREATE TABLE IF NOT EXISTS messages (
  id             bigint PRIMARY KEY DEFAULT nextval('timeline_seq'),
  phone          text NOT NULL,
  direction      text NOT NULL CHECK (direction IN ('in', 'out')),
  kind           text NOT NULL,                    -- Meta's message type: text, interactive, location, contacts, audio, image...
  body           text NOT NULL DEFAULT '',         -- readable text, for previews and search
  payload        jsonb NOT NULL DEFAULT '{}',      -- the message as received from / sent to Meta
  wa_message_id  text UNIQUE,
  status         text NOT NULL DEFAULT '',         -- in: received; out: sent, delivered, read or failed
  error          text NOT NULL DEFAULT '',         -- why Meta couldn't deliver it
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS messages_phone_time ON messages (phone, created_at);

CREATE TABLE IF NOT EXISTS events (
  id          bigint PRIMARY KEY DEFAULT nextval('timeline_seq'),
  phone       text NOT NULL,
  site_id     text NOT NULL DEFAULT '',
  site_name   text NOT NULL DEFAULT '',
  event       text NOT NULL,                       -- the Leads tab's events, plus sales_alerted
  detail      text NOT NULL DEFAULT '',
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS events_phone_time ON events (phone, created_at);
CREATE INDEX IF NOT EXISTS events_site_phone ON events (site_id, phone);

CREATE TABLE IF NOT EXISTS team (
  email       text PRIMARY KEY,                    -- lower case: the Google account they sign in with
  name        text NOT NULL DEFAULT '',
  role        text NOT NULL CHECK (role IN ('owner', 'sales')),
  site_ids    text[] NOT NULL DEFAULT '{}',        -- sales: the projects whose leads they see
  created_at  timestamptz NOT NULL DEFAULT now()
);
