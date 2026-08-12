-- Schema
CREATE TABLE api_facts (
  id SERIAL PRIMARY KEY,
  fact_type TEXT NOT NULL,
  keywords TEXT[] NOT NULL,
  value JSONB NOT NULL,
  source_file TEXT
);

CREATE INDEX idx_api_facts_type ON api_facts(fact_type);
CREATE INDEX idx_api_facts_keywords ON api_facts USING GIN(keywords);

-- Seed data
INSERT INTO api_facts (fact_type, keywords, value) VALUES
  ('rate_limit', ARRAY['free','requests','minute'],       '{"limit": 60, "window": "minute", "plan": "free"}'),
  ('rate_limit', ARRAY['free','requests','day'],          '{"limit": 1000, "window": "day", "plan": "free"}'),
  ('rate_limit', ARRAY['free','webhook','endpoints'],     '{"limit": 2, "plan": "free"}'),
  ('rate_limit', ARRAY['starter','requests','minute'],    '{"limit": 300, "window": "minute", "plan": "starter"}'),
  ('rate_limit', ARRAY['starter','requests','day'],       '{"limit": 10000, "window": "day", "plan": "starter"}'),
  ('rate_limit', ARRAY['starter','webhook','endpoints'],  '{"limit": 10, "plan": "starter"}'),
  ('rate_limit', ARRAY['pro','requests','minute'],        '{"limit": 1000, "window": "minute", "plan": "pro"}'),
  ('rate_limit', ARRAY['pro','requests','day'],           '{"limit": 100000, "window": "day", "plan": "pro"}'),
  ('rate_limit', ARRAY['pro','concurrent','connections'], '{"limit": 50, "plan": "pro"}'),
  ('rate_limit', ARRAY['pro','webhook','endpoints'],      '{"limit": 50, "plan": "pro"}'),
  ('rate_limit', ARRAY['enterprise','requests','minute'], '{"limit": 10000, "window": "minute", "plan": "enterprise"}'),
  ('rate_limit', ARRAY['enterprise','burst','limit'],     '{"limit": 20000, "window": "10s", "plan": "enterprise"}'),
  ('rate_limit', ARRAY['ip','limit','requests','minute'], '{"limit": 5000, "window": "minute", "scope": "ip"}'),

  ('constraint', ARRAY['refund','maximum','payment'],               '{"limit": 5, "unit": "refunds_per_payment"}'),
  ('constraint', ARRAY['refund','days','window'],                   '{"limit": 180, "unit": "days"}'),
  ('constraint', ARRAY['partial','refund','minimum','amount'],      '{"limit": 50, "unit": "cents"}'),
  ('constraint', ARRAY['capture','window','days'],                  '{"limit": 7, "unit": "days"}'),
  ('constraint', ARRAY['trial','maximum','days','subscription'],    '{"limit": 90, "unit": "days"}'),
  ('constraint', ARRAY['currency','supported'],                     '{"currencies": ["EUR","USD","GBP","CHF","SEK","NOK","DKK"]}'),
  ('constraint', ARRAY['metadata','maximum','keys'],                '{"max_keys": 50, "max_key_length": 40}'),
  ('constraint', ARRAY['description','maximum','characters','payment'], '{"limit": 255, "unit": "characters"}'),
  ('constraint', ARRAY['webhook','url','maximum','length'],         '{"limit": 2048, "unit": "characters"}'),
  ('constraint', ARRAY['webhook','retry','failed','delivery'],      '{"retries": 5, "backoff": ["1min","5min","30min","2h","8h"]}'),
  ('constraint', ARRAY['pagination','limit','maximum'],             '{"max": 100, "default": 10}'),
  ('constraint', ARRAY['idempotency','key','expiration'],           '{"expiration": 24, "unit": "hours"}'),

  ('error_code', ARRAY['rate','limit','exceeded','429'],  '{"http_status": 429, "code": "rate_limit_exceeded"}'),
  ('error_code', ARRAY['revoked','api','key'],            '{"http_status": 401, "code": "revoked_api_key"}'),
  ('error_code', ARRAY['refund','window','expired'],      '{"http_status": 422, "code": "refund_window_expired"}'),
  ('error_code', ARRAY['capture','window','expired'],     '{"http_status": 422, "code": "capture_window_expired"}'),
  ('error_code', ARRAY['not','found','404'],              '{"http_status": 404, "code": "not_found"}'),

  ('version', ARRAY['api','version','current'],    '{"version": "v2", "released": "2025-01-15"}'),
  ('version', ARRAY['v1','sunset','deprecated'],   '{"version": "v1", "deprecated": "2025-07-01", "sunset": "2026-01-15"}');
