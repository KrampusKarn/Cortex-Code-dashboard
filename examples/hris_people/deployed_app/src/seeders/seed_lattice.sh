#!/usr/bin/env bash
# Seed the Lattice-sourced tables (performance reviews + HR notes) for DASHBOARD_SPS.
# Run AFTER seed_omnihr.sh — these reference EMPLOYEES (drawn live from the DB).
#   ./seed_lattice.sh [--reset] [--dry-run] [--connection C] [--rows N]
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_seed_common.sh"

LATTICE_TABLES="PERFORMANCE_REVIEWS,EMPLOYEE_NOTES"

parse_args "$@"
run_seed "lattice" "profiles_lattice.json" "$LATTICE_TABLES"
