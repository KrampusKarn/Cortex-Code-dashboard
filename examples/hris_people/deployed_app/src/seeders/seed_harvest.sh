#!/usr/bin/env bash
# Seed the Harvest-sourced tables (project delivery / time / billing) for DASHBOARD_SPS.
# Run AFTER seed_omnihr.sh — these tables reference EMPLOYEES (drawn live from the DB).
#   ./seed_harvest.sh [--reset] [--dry-run] [--connection C] [--rows N]
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_seed_common.sh"

HARVEST_TABLES="CLIENTS,PROJECTS,TASKS,HARVEST_USERS,PROJECT_ASSIGNMENTS,PROJECT_BUDGETS,PROJECT_TASKS,USER_ASSIGNMENTS,TIME_ENTRIES,EXPENSE_ENTRIES,AVAILABILITY,UTILIZATION,INVOICES,INVOICE_LINE_ITEMS,ESTIMATES"

parse_args "$@"
run_seed "harvest" "profiles_harvest.json" "$HARVEST_TABLES"
