#!/usr/bin/env bash
# Set / view AI image generation provider config in the ``configs`` table.
#
# Usage:
#   ./scripts/set_ai_config.sh                     # show all 5 keys (api_key masked)
#   ./scripts/set_ai_config.sh url <value>         # set ai_image.api_url
#   ./scripts/set_ai_config.sh key <value>         # set ai_image.api_key
#   ./scripts/set_ai_config.sh model <value>       # set ai_image.default_model
#   ./scripts/set_ai_config.sh cost <int>          # set ai_image.credit_cost (≥1)
#   ./scripts/set_ai_config.sh timeout <int>       # set ai_image.timeout_seconds (5..300)
#   ./scripts/set_ai_config.sh enabled true|false  # set ai_image.enabled (feature flag)
#
# Configs are read by app/services/ai_service.py::load_ai_config() at request time,
# so changes apply immediately — no container rebuild needed.
set -euo pipefail

# Pick the same MySQL credentials docker-compose uses. Override via env if needed.
MYSQL_USER="${MYSQL_USER:-imageurl}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-imageurl_pwd}"
MYSQL_DATABASE="${MYSQL_DATABASE:-imageurl}"
MYSQL_HOST_PORT="${MYSQL_HOST_PORT:-3308}"
MYSQL_CONTAINER="${MYSQL_CONTAINER:-mysql}"

# Run mysql client inside the container so we don't need a local client.
mysql_exec() {
  docker compose exec -T "$MYSQL_CONTAINER" \
    mysql -N -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" -e "$1"
}

show() {
  echo "AI image provider config:"
  echo "--------------------------"
  # Key + description + value (api_key masked). Use \G to avoid wide-table wrap.
  mysql_exec "SELECT config_key, description, config_value FROM configs WHERE config_key LIKE 'ai_image.%' ORDER BY config_key" \
    | awk -F'\t' '{
        key=$1; desc=$2; val=$3;
        if (key=="ai_image.api_key" && length(val)>12) {
          masked=substr(val,1,4) "****" substr(val,length(val)-3);
          val=masked " (masked)";
        }
        printf "  %-30s = %s\n     └─ %s\n", key, val, desc;
      }'
}

update_key() {
  local key="$1" value="$2"
  # Validate per-key
  case "$key" in
    ai_image.credit_cost)
      if ! [[ "$value" =~ ^[0-9]+$ ]] || [ "$value" -lt 1 ]; then
        echo "credit_cost must be a positive integer (got: $value)" >&2; exit 1
      fi
      ;;
    ai_image.timeout_seconds)
      if ! [[ "$value" =~ ^[0-9]+$ ]] || [ "$value" -lt 5 ] || [ "$value" -gt 300 ]; then
        echo "timeout_seconds must be 5..300 (got: $value)" >&2; exit 1
      fi
      ;;
    ai_image.api_url)
      if ! [[ "$value" =~ ^https?:// ]]; then
        echo "api_url must start with http:// or https:// (got: $value)" >&2; exit 1
      fi
      ;;
    ai_image.enabled)
      lc=$(echo "$value" | tr '[:upper:]' '[:lower:]')
      if [[ "$lc" != "true" && "$lc" != "false" && "$lc" != "1" && "$lc" != "0" && "$lc" != "yes" && "$lc" != "no" && "$lc" != "on" && "$lc" != "off" ]]; then
        echo "enabled must be true/false (got: $value)" >&2; exit 1
      fi
      ;;
  esac

  # Atomic update; description is preserved.
  mysql_exec "UPDATE configs SET config_value='${value//\'/\'\'}' WHERE config_key='$key'"
  echo "✓ $key updated"
}

case "${1:-}" in
  ""|show|list)
    show
    ;;
  url)
    [ -z "${2:-}" ] && { echo "usage: $0 url <value>"; exit 1; }
    update_key "ai_image.api_url" "$2"
    ;;
  key|apikey|api_key)
    [ -z "${2:-}" ] && { echo "usage: $0 key <value>"; exit 1; }
    update_key "ai_image.api_key" "$2"
    ;;
  model)
    [ -z "${2:-}" ] && { echo "usage: $0 model <value>"; exit 1; }
    update_key "ai_image.default_model" "$2"
    ;;
  cost)
    [ -z "${2:-}" ] && { echo "usage: $0 cost <int>"; exit 1; }
    update_key "ai_image.credit_cost" "$2"
    ;;
  timeout)
    [ -z "${2:-}" ] && { echo "usage: $0 timeout <int>"; exit 1; }
    update_key "ai_image.timeout_seconds" "$2"
    ;;
  enabled|enable|on)
    [ -z "${2:-}" ] && { echo "usage: $0 enabled true|false"; exit 1; }
    update_key "ai_image.enabled" "$2"
    ;;
  *)
    echo "Unknown command: $1" >&2
    echo "Run '$0' for usage." >&2
    exit 1
    ;;
esac