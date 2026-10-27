#!/bin/bash

if [ -f .env ]; then
    set -a
    source .env
    set +a
else
    echo "Error: .env file not found!"
    exit 1
fi

echo "Starting Load Test: $TOTAL_REQUESTS requests with concurrency $CONCURRENCY"

cat <<EOF > payload.json
{"prompt": "$PROMPT", "max_new_tokens": $MAX_TOKENS}
EOF
echo "Payload prepared: $(cat payload.json)"

start_time=$(date +%s)

seq 1 $TOTAL_REQUESTS | xargs -n 1 -P $CONCURRENCY -I {} \
    curl -s -w "Request {}: HTTP %{http_code} | Time: %{time_total}s\n" \
    -X POST "$URL" \
    -H "Content-Type: application/json" \
    -d @payload.json

end_time=$(date +%s)
echo "------------------------------"
echo "Test Completed in $((end_time - start_time)) seconds."

rm payload.json