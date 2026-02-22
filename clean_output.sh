#!/bin/bash
# clean_output.sh - Clear regeneratable model output, logs, and fetched data
#
# Targets output/ and log/ directories under pricing/, valuation/, monitoring/.
# With --clean-data, also deletes re-fetchable data (preserving snapshots and config).
#
# Usage:
#   ./clean_output.sh --all                    Delete all output and log files
#   ./clean_output.sh --all --keep-logs        Delete output only, preserve logs
#   ./clean_output.sh --all --clean-data       Delete output, logs, and fetched data
#   ./clean_output.sh --keep-showcase          Delete all except README showcase SVGs
#   ./clean_output.sh --dry-run --all          Preview what --all would delete
#   ./clean_output.sh --dry-run --keep-showcase  Preview with showcase preservation

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

MODE=""
DRY_RUN=false
SKIP_CONFIRM=false
KEEP_LOGS=false
CLEAN_DATA=false

usage() {
    echo "Usage: $0 [--dry-run] [--yes] [--keep-logs] [--clean-data] <--all | --keep-showcase>"
    echo ""
    echo "Modes:"
    echo "  --all            Delete all files in output/ and log/ directories"
    echo "  --keep-showcase  Delete all except README-referenced showcase SVGs"
    echo ""
    echo "Options:"
    echo "  --keep-logs      Preserve log/ directories (only delete output/)"
    echo "  --clean-data     Also delete re-fetchable data in data/ directories"
    echo "                   Preserves: snapshots/, git-tracked files, config files"
    echo "  --dry-run        Preview what would be deleted without deleting"
    echo "  --yes            Skip confirmation prompt"
    echo ""
    echo "Targets output/ and log/ directories under pricing/, valuation/, monitoring/."
    echo "Config files, snapshots, and git-tracked data are never deleted."
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --all) MODE="all"; shift ;;
        --keep-showcase) MODE="keep-showcase"; shift ;;
        --keep-logs) KEEP_LOGS=true; shift ;;
        --clean-data) CLEAN_DATA=true; shift ;;
        --dry-run) DRY_RUN=true; shift ;;
        --yes|-y) SKIP_CONFIRM=true; shift ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $1"; usage ;;
    esac
done

[[ -z "$MODE" ]] && usage

# Extract showcase SVG paths from README.md (relative to project root)
get_showcase_files() {
    grep -oP 'src="\./([^"]+)"' README.md 2>/dev/null | sed 's/src="\.\/\(.*\)"/\1/' || true
}

# Check if a data file is safe to delete (re-fetchable, not config/snapshot/tracked)
# Returns 0 (true) if deletable, 1 (false) if should be preserved
is_deletable_data_file() {
    local file="$1"

    # Never delete snapshots
    if [[ "$file" == */snapshots/* ]]; then
        return 1
    fi

    # Never delete git-tracked files
    if git ls-files --error-unmatch "$file" &>/dev/null; then
        return 1
    fi

    # Preserve config files (hand-curated, not re-fetchable — ALWAYS protected)
    local basename=$(basename "$file")
    case "$basename" in
        params.json|params_*.json|config.json|config_*.json) return 1 ;;
        tickers.json|holdings.json|targets.json) return 1 ;;
        bayesian_priors.json|og_reserves.json) return 1 ;;
        .last_tickers) return 1 ;;
        DATA_SOURCES.md|*.md) return 1 ;;
    esac

    # Everything else in data/ is considered re-fetchable
    return 0
}

# Find data directories under the three main module trees
find_data_dirs() {
    find pricing/ valuation/ monitoring/ alternative/ \
        -type d -name data \
        -not -path '*/_opam/*' \
        -not -path '*/.opam-switch/*' \
        -not -path '*/node_modules/*' \
        -not -path '*/snapshots/*' \
        2>/dev/null | sort
}

# Find target directories under the three main module trees
find_target_dirs() {
    if $KEEP_LOGS; then
        find pricing/ valuation/ monitoring/ alternative/ \
            -type d -name output \
            -not -path '*/_opam/*' \
            -not -path '*/.opam-switch/*' \
            -not -path '*/node_modules/*' \
            2>/dev/null | sort
    else
        find pricing/ valuation/ monitoring/ alternative/ \
            -type d \( -name output -o -name log \) \
            -not -path '*/_opam/*' \
            -not -path '*/.opam-switch/*' \
            -not -path '*/node_modules/*' \
            2>/dev/null | sort
    fi
}

# Build showcase file set for keep-showcase mode
declare -A SHOWCASE
showcase_count=0
if [[ "$MODE" == "keep-showcase" ]]; then
    while IFS= read -r f; do
        if [[ -n "$f" ]]; then
            SHOWCASE["$f"]=1
            showcase_count=$((showcase_count + 1))
        fi
    done < <(get_showcase_files)
fi

# First pass: count files
total=0
would_delete=0
would_keep=0
data_total=0
data_would_delete=0
data_would_keep=0

while IFS= read -r dir; do
    while IFS= read -r file; do
        [[ -z "$file" ]] && continue
        total=$((total + 1))
        rel="${file#./}"
        if [[ "$MODE" == "keep-showcase" && -n "${SHOWCASE[$rel]+x}" ]]; then
            would_keep=$((would_keep + 1))
        else
            would_delete=$((would_delete + 1))
        fi
    done < <(find "$dir" -type f 2>/dev/null)
done < <(find_target_dirs)

# Count data files if --clean-data
if $CLEAN_DATA; then
    while IFS= read -r dir; do
        while IFS= read -r file; do
            [[ -z "$file" ]] && continue
            data_total=$((data_total + 1))
            if is_deletable_data_file "$file"; then
                data_would_delete=$((data_would_delete + 1))
            else
                data_would_keep=$((data_would_keep + 1))
            fi
        done < <(find "$dir" -type f 2>/dev/null)
    done < <(find_data_dirs)
fi

if [[ $total -eq 0 && $data_total -eq 0 ]]; then
    echo -e "${GREEN}Nothing to clean — output directories are already empty.${NC}"
    exit 0
fi

# Summary before action
echo ""
if [[ "$MODE" == "all" ]]; then
    if $KEEP_LOGS; then
        echo -e "${BOLD}Mode: Delete ALL output (keeping logs)${NC}"
    else
        echo -e "${BOLD}Mode: Delete ALL output and logs${NC}"
    fi
else
    echo -e "${BOLD}Mode: Delete output, keep $showcase_count showcase SVGs${NC}"
    if $KEEP_LOGS; then
        echo -e "${BOLD}      (keeping logs)${NC}"
    fi
fi
if $CLEAN_DATA; then
    echo -e "${BOLD}      + delete re-fetchable data (preserving snapshots & config)${NC}"
fi
echo -e "  Output/log files found:   ${BOLD}$total${NC}"
echo -e "  Files to delete:          ${RED}$would_delete${NC}"
if [[ $would_keep -gt 0 ]]; then
    echo -e "  Showcase files to keep:   ${GREEN}$would_keep${NC}"
fi
if $CLEAN_DATA; then
    echo -e "  Data files found:         ${BOLD}$data_total${NC}"
    echo -e "  Fetched data to delete:   ${RED}$data_would_delete${NC}"
    echo -e "  Config/snapshots to keep: ${GREEN}$data_would_keep${NC}"
fi
echo ""

# Confirmation
if ! $DRY_RUN && ! $SKIP_CONFIRM; then
    total_deleting=$((would_delete + data_would_delete))
    echo -e "${YELLOW}${BOLD}WARNING: This will permanently delete $total_deleting files.${NC}"
    echo -e "${YELLOW}Output can be regenerated by re-running modules from the quickstart menu.${NC}"
    echo -ne "${YELLOW}Continue? (y/n): ${NC}"
    read -r confirm
    if [[ "$confirm" != "y" ]]; then
        echo -e "${BLUE}Cancelled.${NC}"
        exit 0
    fi
fi

# Second pass: delete (or dry-run report)
deleted=0
skipped=0

while IFS= read -r dir; do
    while IFS= read -r file; do
        [[ -z "$file" ]] && continue
        rel="${file#./}"

        if [[ "$MODE" == "keep-showcase" && -n "${SHOWCASE[$rel]+x}" ]]; then
            skipped=$((skipped + 1))
            $DRY_RUN && echo -e "  ${GREEN}[KEEP]${NC}   $rel"
            continue
        fi

        if $DRY_RUN; then
            echo -e "  ${RED}[DELETE]${NC} $rel"
        else
            rm -f "$file"
        fi
        deleted=$((deleted + 1))
    done < <(find "$dir" -type f 2>/dev/null)
done < <(find_target_dirs)

# Delete data files if --clean-data
data_deleted=0
data_skipped=0

if $CLEAN_DATA; then
    while IFS= read -r dir; do
        while IFS= read -r file; do
            [[ -z "$file" ]] && continue
            if ! is_deletable_data_file "$file"; then
                data_skipped=$((data_skipped + 1))
                $DRY_RUN && echo -e "  ${GREEN}[KEEP]${NC}   ${file#./} (config/snapshot/tracked)"
                continue
            fi
            if $DRY_RUN; then
                echo -e "  ${RED}[DELETE]${NC} ${file#./}"
            else
                rm -f "$file"
            fi
            data_deleted=$((data_deleted + 1))
        done < <(find "$dir" -type f 2>/dev/null)
    done < <(find_data_dirs)
fi

# Remove empty directories left behind
if ! $DRY_RUN; then
    while IFS= read -r dir; do
        find "$dir" -mindepth 1 -type d -empty -delete 2>/dev/null || true
    done < <(find_target_dirs)
    if $CLEAN_DATA; then
        while IFS= read -r dir; do
            find "$dir" -mindepth 1 -type d -empty -delete 2>/dev/null || true
        done < <(find_data_dirs)
    fi
fi

echo ""
if $DRY_RUN; then
    echo -e "${YELLOW}[DRY RUN]${NC} Would delete ${BOLD}$deleted${NC} of $total output/log files ($skipped kept)"
    if $CLEAN_DATA; then
        echo -e "${YELLOW}[DRY RUN]${NC} Would delete ${BOLD}$data_deleted${NC} of $data_total data files ($data_skipped preserved)"
    fi
else
    echo -e "${GREEN}Deleted ${BOLD}$deleted${NC}${GREEN} output/log files${NC}"
    if [[ $skipped -gt 0 ]]; then
        echo -e "${GREEN}Preserved ${BOLD}$skipped${NC}${GREEN} showcase files${NC}"
    fi
    if $CLEAN_DATA; then
        echo -e "${GREEN}Deleted ${BOLD}$data_deleted${NC}${GREEN} fetched data files${NC}"
        if [[ $data_skipped -gt 0 ]]; then
            echo -e "${GREEN}Preserved ${BOLD}$data_skipped${NC}${GREEN} config/snapshot/tracked files${NC}"
        fi
    fi
fi
