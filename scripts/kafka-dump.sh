#!/usr/bin/env bash
# Sink side: dump the whole lab topic with offset and record CreateTime to out/kafka-dump.txt.
# Line format: CreateTime:<ms>\tOffset:<n>\t<FlowPorts point JSON>
set -euo pipefail
cd "$(dirname "$0")/.."
TOPIC="${KAFKA_TOPIC:-$(sed -n 's/^KAFKA_TOPIC=\([^ #]*\).*/\1/p' .env 2>/dev/null)}"
TOPIC="${TOPIC:-lab-events}"
mkdir -p out
docker compose exec -T kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic "$TOPIC" --from-beginning --timeout-ms 15000 \
  --formatter-property print.timestamp=true --formatter-property print.offset=true > out/kafka-dump.txt 2> out/kafka-dump.err || true
echo "records: $(grep -c '^CreateTime:' out/kafka-dump.txt) -> out/kafka-dump.txt"
