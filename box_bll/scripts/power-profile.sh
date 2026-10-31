#!/system/bin/sh
export PATH="/data/adb/box_bll/bin:$PATH"
# Emit a complete optional configuration; never modify the input in place.
config="${1:-/data/adb/box_bll/clash/config.yaml}"
[ -r "$config" ] || { echo "Cannot read configuration: $config" >&2; exit 1; }
awk '
    /^find-process-mode:[[:space:]]*/ { print "find-process-mode: strict"; next }
    /^[[:space:]]*health-check:[[:space:]]*$/ {
        match($0, /[^ ]/); health_indent = RSTART; health = 1; print; next
    }
    health && /^[[:space:]]*[^[:space:]#]/ {
        match($0, /[^ ]/)
        if (RSTART <= health_indent) health = 0
    }
    health && /^[[:space:]]*interval:[[:space:]]*[0-9]+[[:space:]]*(#.*)?$/ {
        # Keep already less frequent checks and disabled periodic checks intact.
        value = $0; sub(/^[[:space:]]*interval:[[:space:]]*/, "", value)
        value += 0
        if (value > 0 && value < 900) sub(/interval:[[:space:]]*[0-9]+/, "interval: 900")
    }
    { print }
' "$config"
