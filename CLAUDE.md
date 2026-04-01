# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This repo fetches `type/bug` issues from the `grafana/grafana` GitHub repo, extracts the Grafana version each bug was found in (from issue body templates), and generates reports grouped by version. It runs weekly via GitHub Actions.

## Running

Requires `GH_TOKEN` environment variable (GitHub personal access token or app token).

```bash
# Set up virtualenv
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Full run (fetch new issues from GitHub + regenerate all reports)
GH_TOKEN=<token> python main.py --no-cache

# Regenerate reports from cached JSON files (no GitHub API calls)
python main.py
```

## Data Pipeline

All logic is in `main.py`. The pipeline runs sequentially:

1. **`fetch_github_issues`** — paginates GitHub GraphQL API for `type/bug` issues → `issues.json`
2. **`find_fixed_in_version`** — for closed issues, follows connected events to linked PRs/issues, gets milestone → `issues-with_fixed.json`
3. **`find_grafana_version`** — extracts version from `Grafana:` / `Grafana Version:` line in issue body → `issues_with_found_in.json`
4. **`organize_issues_by_version`** — groups issues by version string → `issues_by_version.json`
5. **`log_stats`** / **`create_report_md`** / **`review_release_info`** — write output to `reports/`

## Output Files

| File | Description |
|------|-------------|
| `issues.json` | Raw issues from GitHub |
| `issues-with_fixed.json` | Issues enriched with `fixed_in` milestone |
| `issues_with_found_in.json` | Issues enriched with `found_in` version |
| `issues_by_version.json` | Issues grouped by version |
| `reports/open_report.md` | Open bugs by version |
| `reports/closed_report.md` | Closed bugs by version |
| `reports/all_report.md` | All bugs by version |
| `reports/stats_by_version.csv` | Per-patch-version counts |
| `reports/stats_by_major_minor_version.csv` | Per major.minor counts |
| `reports/release_stats.csv` | Per-release counts + commit delta |
| `reports/major_minor_release_stats.csv` | Per major.minor release counts + commits |
| `stats.txt` | Summary stats (also printed to stdout) |

## GitHub Actions

The workflow (`.github/workflows/cron-generate-bug-report.yaml`) runs every Wednesday at 15:00 UTC. It uses a GitHub App token (`GH_REPORT_GITHUB_APP_ID` / `GH_REPORT_GITHUB_APP_PRIVATE_KEY_PEM` secrets) to authenticate, then opens and auto-merges a PR with the updated reports.

To test the workflow locally, use [act](https://github.com/nektos/act) — the workflow skips the PR creation/merge steps when `ACT` env var is set.

## Caching

`fetch_a_list_of_tags_from_github` caches results to `tags.json`. Pass `--no-cache` to bypass all caches and re-fetch from GitHub. Without `--no-cache`, `main.py` skips GitHub API calls and regenerates reports from existing JSON files.
