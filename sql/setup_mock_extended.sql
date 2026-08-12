-- Extended mock ledger for the larger tool catalogue (phase: tool-count degradation study).
-- Entirely simulated, same as sql/setup_mock_transactions.sql — no real payments, no real PII.
--
-- These tables exist so the extra tools have something real to read and write, and so the
-- "confusable write tools" (refund vs void vs accept_dispute vs cancel_subscription) each
-- have a state machine that only they can legally act on. Customer emails match the ones
-- already seeded in mock_transactions.

DROP TABLE IF EXISTS mock_authorizations;
DROP TABLE IF EXISTS mock_disputes;
DROP TABLE IF EXISTS mock_subscriptions;
DROP TABLE IF EXISTS mock_customers;
DROP TABLE IF EXISTS mock_webhook_deliveries;
DROP TABLE IF EXISTS mock_idempotency_keys;

-- Authorizations: money is HELD, not captured. Refunding one is wrong — you void it.
-- See docs/guides/auth_capture_flow.md
CREATE TABLE mock_authorizations (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL,             -- 'authorized' | 'captured' | 'voided' | 'expired'
  amount_cents INTEGER NOT NULL,    -- the authorized (maximum) amount
  captured_cents INTEGER NOT NULL DEFAULT 0,
  currency TEXT NOT NULL,
  customer_email TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL,
  expires_at TIMESTAMP NOT NULL
);

INSERT INTO mock_authorizations VALUES
  ('AUTH-2001', 'authorized', 20000, 0,     'EUR', 'anna.reyes@example.com',       '2026-08-02 10:00:00', '2026-08-09 10:00:00'),
  ('AUTH-2002', 'authorized', 45000, 0,     'USD', 'ben.oduya@example.com',        '2026-08-03 15:30:00', '2026-08-10 15:30:00'),
  ('AUTH-2003', 'captured',   30000, 27500, 'GBP', 'carla.nguyen@example.com',     '2026-07-28 09:00:00', '2026-08-04 09:00:00'),
  ('AUTH-2004', 'voided',     15000, 0,     'EUR', 'daniel.kowalski@example.com',  '2026-07-26 12:00:00', '2026-08-02 12:00:00'),
  ('AUTH-2005', 'expired',    8000,  0,     'USD', 'elin.johansson@example.com',   '2026-07-20 08:00:00', '2026-07-27 08:00:00'),
  -- v2: rows below give the write tasks that used to collide a row of their own, so the dataset
  -- is correct even when tasks are not reset in between (see POSTMORTEM.md E13).
  ('AUTH-2006', 'authorized', 45000, 0,     'USD', 'ben.oduya@example.com',        '2026-08-03 16:00:00', '2026-08-10 16:00:00'),
  ('AUTH-2007', 'authorized', 12500, 0,     'EUR', 'farid.haidari@example.com',    '2026-08-04 09:20:00', '2026-08-11 09:20:00');

-- Disputes (chargebacks). Accepting one is NOT the same as refunding.
-- See docs/guides/disputes_guide.md
CREATE TABLE mock_disputes (
  id TEXT PRIMARY KEY,
  transaction_id TEXT NOT NULL,
  status TEXT NOT NULL,             -- 'needs_response' | 'under_review' | 'won' | 'lost' | 'accepted'
  reason TEXT NOT NULL,             -- 'fraudulent' | 'product_not_received' | 'duplicate' | 'subscription_canceled'
  amount_cents INTEGER NOT NULL,
  currency TEXT NOT NULL,
  evidence_due_by TIMESTAMP,
  evidence_submitted BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMP NOT NULL
);

INSERT INTO mock_disputes VALUES
  ('DIS-3001', 'TX-1190', 'needs_response', 'fraudulent',            12000, 'USD', '2026-08-09 23:59:00', FALSE, '2026-08-01 11:00:00'),
  ('DIS-3002', 'TX-2298', 'needs_response', 'product_not_received',   8999, 'USD', '2026-08-07 23:59:00', FALSE, '2026-07-31 14:20:00'),
  ('DIS-3003', 'TX-5561', 'under_review',   'duplicate',             15000, 'CHF', '2026-08-04 23:59:00', TRUE,  '2026-07-29 09:15:00'),
  ('DIS-3004', 'TX-6654', 'lost',           'fraudulent',             2500, 'USD', '2026-07-28 23:59:00', TRUE,  '2026-07-22 16:40:00'),
  ('DIS-3005', 'TX-8832', 'won',            'subscription_canceled',  5000, 'EUR', '2026-07-30 23:59:00', TRUE,  '2026-07-24 10:05:00'),
  ('DIS-3006', 'TX-4118', 'needs_response', 'product_not_received',    999, 'SEK', '2026-08-08 23:59:00', FALSE, '2026-08-02 08:30:00');

-- Subscriptions. Cancelling stops FUTURE billing; it does not refund past charges.
-- See docs/guides/subscriptions_guide.md
CREATE TABLE mock_subscriptions (
  id TEXT PRIMARY KEY,
  customer_email TEXT NOT NULL,
  plan_name TEXT NOT NULL,
  status TEXT NOT NULL,             -- 'active' | 'past_due' | 'canceled' | 'trialing' | 'paused'
  amount_cents INTEGER NOT NULL,
  currency TEXT NOT NULL,
  interval TEXT NOT NULL,           -- 'month' | 'year'
  current_period_end TIMESTAMP NOT NULL,
  cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE
);

INSERT INTO mock_subscriptions VALUES
  ('SUB-5001', 'anna.reyes@example.com',      'Pro Monthly',      'active',   2900, 'EUR', 'month', '2026-08-28 00:00:00', FALSE),
  ('SUB-5002', 'ben.oduya@example.com',       'Enterprise Annual','active',  49900, 'EUR', 'year',  '2027-03-15 00:00:00', FALSE),
  ('SUB-5003', 'carla.nguyen@example.com',    'Pro Monthly',      'past_due', 2900, 'USD', 'month', '2026-08-10 00:00:00', FALSE),
  ('SUB-5004', 'daniel.kowalski@example.com', 'Starter Monthly',  'trialing',  900, 'GBP', 'month', '2026-08-20 00:00:00', FALSE),
  ('SUB-5005', 'elin.johansson@example.com',  'Pro Monthly',      'canceled', 2900, 'USD', 'month', '2026-07-15 00:00:00', TRUE);

-- Customers. See docs/guides/customers_guide.md
CREATE TABLE mock_customers (
  email TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  country TEXT NOT NULL,
  default_currency TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL,
  lifetime_value_cents INTEGER NOT NULL
);

INSERT INTO mock_customers VALUES
  ('anna.reyes@example.com',       'Anna Reyes',        'ES', 'EUR', '2025-11-03 10:00:00',  4899),
  ('ben.oduya@example.com',        'Ben Oduya',         'KE', 'EUR', '2025-08-14 12:30:00', 54900),
  ('carla.nguyen@example.com',     'Carla Nguyen',      'US', 'USD', '2026-01-22 09:15:00', 14900),
  ('daniel.kowalski@example.com',  'Daniel Kowalski',   'PL', 'GBP', '2026-06-30 17:45:00',  5400),
  ('elin.johansson@example.com',   'Elin Johansson',    'SE', 'USD', '2025-05-19 08:20:00', 11600),
  ('farid.haidari@example.com',    'Farid Haidari',     'AF', 'USD', '2026-02-11 14:05:00',  8999),
  ('grace.omondi@example.com',     'Grace Omondi',      'KE', 'EUR', '2026-03-08 11:11:00',     0),
  ('hugo.fernandez@example.com',   'Hugo Fernandez',    'CH', 'CHF', '2025-12-01 07:00:00', 15000),
  ('ines.moreau@example.com',      'Ines Moreau',       'FR', 'USD', '2025-09-25 16:40:00', 50000),
  ('jonas.lindqvist@example.com',  'Jonas Lindqvist',   'SE', 'SEK', '2026-07-30 06:00:00',     0);

-- Webhook deliveries. See docs/guides/webhooks_guide.md
CREATE TABLE mock_webhook_deliveries (
  id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  target_url TEXT NOT NULL,
  status TEXT NOT NULL,             -- 'delivered' | 'failed' | 'pending'
  response_code INTEGER,
  attempts INTEGER NOT NULL,
  last_attempt_at TIMESTAMP NOT NULL
);

INSERT INTO mock_webhook_deliveries VALUES
  ('WH-7001', 'payment.succeeded', 'https://api.merchant.example/hooks', 'delivered', 200, 1, '2026-08-01 12:00:00'),
  ('WH-7002', 'dispute.created',   'https://api.merchant.example/hooks', 'failed',    500, 4, '2026-08-02 09:30:00'),
  ('WH-7003', 'payment.failed',    'https://api.merchant.example/hooks', 'failed',    503, 6, '2026-08-02 15:45:00'),
  ('WH-7004', 'refund.succeeded',  'https://api.merchant.example/hooks', 'delivered', 200, 2, '2026-08-03 08:10:00'),
  ('WH-7005', 'subscription.updated','https://api.merchant.example/hooks','pending',  NULL, 0, '2026-08-03 18:22:00'),
  ('WH-7006', 'payment.succeeded', 'https://api.merchant.example/hooks', 'failed',    502, 3, '2026-08-04 11:05:00');

-- Idempotency keys: replayed keys must return the original result, never act twice.
-- See docs/guides/idempotency_guide.md
CREATE TABLE mock_idempotency_keys (
  key TEXT PRIMARY KEY,
  tool_name TEXT NOT NULL,
  response_json TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
