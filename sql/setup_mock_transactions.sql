-- Mock transaction ledger for the agent tools (check_transaction_status, initiate_refund).
-- Entirely simulated for this portfolio project — no real payments, no real PII.

CREATE TABLE mock_transactions (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL,             -- 'succeeded' | 'failed' | 'pending' | 'refunded'
  transaction_type TEXT NOT NULL,   -- 'payment' | 'payout'
  amount_cents INTEGER NOT NULL,
  currency TEXT NOT NULL,
  customer_email TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL,
  fee_cents INTEGER NOT NULL
);

-- Seed data
INSERT INTO mock_transactions (id, status, transaction_type, amount_cents, currency, customer_email, created_at, fee_cents) VALUES
  ('TX-4521', 'failed',    'payment', 1999,  'USD', 'anna.reyes@example.com',   '2026-07-28 09:12:00', 0),
  ('TX-8832', 'succeeded', 'payment', 5000,  'EUR', 'ben.oduya@example.com',    '2026-07-29 14:03:00', 175),
  ('TX-1190', 'succeeded', 'payment', 12000, 'USD', 'carla.nguyen@example.com', '2026-07-30 11:47:00', 378),
  ('TX-3307', 'pending',   'payment', 4500,  'GBP', 'daniel.kowalski@example.com', '2026-07-31 08:20:00', 0),
  ('TX-6654', 'refunded',  'payment', 2500,  'USD', 'elin.johansson@example.com', '2026-07-25 16:55:00', 103),
  ('TX-2298', 'succeeded', 'payment', 8999,  'USD', 'farid.haidari@example.com', '2026-07-26 10:31:00', 291),
  ('TX-7743', 'failed',    'payment', 3200,  'EUR', 'grace.omondi@example.com', '2026-07-27 19:08:00', 0),
  ('TX-5561', 'succeeded', 'payment', 15000, 'CHF', 'hugo.fernandez@example.com', '2026-08-01 07:44:00', 465),
  ('TX-9902', 'succeeded', 'payout',  50000, 'USD', 'ines.moreau@example.com',  '2026-07-24 13:15:00', 0),
  ('TX-4118', 'pending',   'payment', 999,   'SEK', 'jonas.lindqvist@example.com', '2026-08-01 06:02:00', 0),
  -- v2: Carla's second charge, newer than TX-1190 and with no dispute against it, so T09's
  -- "last charge" resolves here instead of colliding with T08's disputed TX-1190 (see POSTMORTEM.md E13).
  ('TX-1191', 'succeeded', 'payment', 7500,  'USD', 'carla.nguyen@example.com', '2026-08-03 09:15:00', 248);
