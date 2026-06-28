#!/usr/bin/env bash
# Seed the OmniHR-sourced tables (HR / org / recruitment / leave) for DASHBOARD_SPS.
# Run this FIRST — Harvest and Lattice tables reference EMPLOYEES, which this creates.
#   ./seed_omnihr.sh [--reset] [--dry-run] [--connection C] [--rows N]
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_seed_common.sh"

OMNIHR_TABLES="BUSINESS_UNITS,DEPARTMENTS_DETAIL,SUB_DEPARTMENTS,TEAMS,EMPLOYEES,EMPLOYEE_FIELDS,EMPLOYEE_PII,EMPLOYEE_COMPENSATION_DETAILS,EMPLOYEE_CERTIFICATIONS,SALARY,EMPLOYEES_HISTORY,HEADCOUNT_PLAN,CANDIDATE_SOURCE_CATEGORIES,CANDIDATE_SOURCES,JOB_POSTINGS,CANDIDATES,ONBOARDING_TASKS,LEAVE_REQUESTS"

parse_args "$@"
run_seed "omnihr" "profiles_omnihr.json" "$OMNIHR_TABLES"
