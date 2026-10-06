#!/bin/sh
# Runs every suite against fresh servers/databases.
cd "$(dirname "$0")" || exit 1
for t in test_flow test_violations test_push test_mobile test_demo; do python3 $t.py || exit 1; done
start() { TALBISTA_DB=/tmp/tb.db ADMIN_PASSWORD=AdminPass123 python3 server.py >/dev/null 2>&1 & P=$!; sleep 1.5; }
for t in test_admin test_driver test_security test_dispatch test_registration test_store test_gps_ui; do
  rm -f /tmp/tb.db /tmp/tb.db-wal /tmp/tb.db-shm; start; python3 $t.py || { kill $P; exit 1; }; kill $P; wait $P 2>/dev/null
done
rm -f /tmp/tb.db /tmp/tb.db-wal /tmp/tb.db-shm; start; python3 test_restart.py 1 || { kill $P; exit 1; }; kill $P; wait $P 2>/dev/null
start; python3 test_restart.py 2 || { kill $P; exit 1; }; kill $P; wait $P 2>/dev/null
echo ALL SUITES PASSED
