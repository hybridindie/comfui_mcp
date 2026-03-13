#!/usr/bin/env bash
# Post-tool hook: surface security warnings from node audit results.
# Reads tool output JSON from stdin. Exits 0 always (non-blocking).
#
# Matches on specific warning patterns from:
# - WorkflowInspector: "Dangerous node type", "Suspicious input"
# - NodeAuditor: "dangerous" key with count > 0
# Avoids false positives on JSON keys like "dangerous": {"count": 0}.

input=$(cat)

# Check for inspector warnings (plain text in tool output)
if echo "$input" | grep -qE "Dangerous node type|Suspicious input"; then
  echo "SECURITY: Dangerous node patterns detected. Review the audit results above before proceeding."
  exit 0
fi

# Check for node auditor results with actual findings (count > 0)
if echo "$input" | grep -qE '"dangerous":\s*\{\s*"count":\s*[1-9]'; then
  echo "SECURITY: Dangerous nodes found in audit. Review the results above before proceeding."
  exit 0
fi
