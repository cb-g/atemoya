#!/usr/bin/env bash
# Start Theta Terminal, reading credentials from .env
# Usage: ./lib/thetadata/start_terminal.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
JAR="$SCRIPT_DIR/ThetaTerminalv3.jar"

if [[ ! -f "$JAR" ]]; then
    echo "Error: ThetaTerminalv3.jar not found in $SCRIPT_DIR"
    echo "Download: curl -L -o $JAR https://download-unstable.thetadata.us/ThetaTerminalv3.jar"
    exit 1
fi

# Read credentials from .env
EMAIL=""
PASSWORD=""
if [[ -f "$PROJECT_ROOT/.env" ]]; then
    EMAIL=$(grep '^THETADATA_EMAIL=' "$PROJECT_ROOT/.env" | cut -d= -f2-)
    PASSWORD=$(grep '^THETADATA_PASSWORD=' "$PROJECT_ROOT/.env" | cut -d= -f2-)
fi

if [[ -z "$EMAIL" || -z "$PASSWORD" ]]; then
    echo "Error: THETADATA_EMAIL and THETADATA_PASSWORD must be set in .env"
    exit 1
fi

# Write temporary creds file to /tmp (outside repo)
CREDS="/tmp/thetadata_creds.txt"
printf '%s\n%s\n' "$EMAIL" "$PASSWORD" > "$CREDS"
chmod 600 "$CREDS"

# Clean up creds on exit
cleanup() { rm -f "$CREDS"; }
trap cleanup EXIT INT TERM

echo "Starting Theta Terminal..."
java -jar "$JAR" --creds-file "$CREDS"
