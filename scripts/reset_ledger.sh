#!/bin/bash
cd /workspace/llm-agent-mcp-eval
su postgres -c "psql -q -d nexuspay_rag -c \"DROP TABLE IF EXISTS mock_transactions;\"" >/dev/null 2>&1
su postgres -c "psql -q -d nexuspay_rag -f sql/setup_mock_transactions.sql" >/dev/null 2>&1
su postgres -c "psql -q -d nexuspay_rag -f sql/setup_mock_extended.sql" >/dev/null 2>&1
