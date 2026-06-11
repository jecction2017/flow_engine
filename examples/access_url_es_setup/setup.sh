#!/usr/bin/env bash
# 为 example_11_access_url_feature_pipeline 准备 Elasticsearch 测试数据
#
# 用法:
#   ./setup.sh
#   ES_HOST=http://127.0.0.1:9200 RECREATE=1 ./setup.sh

set -euo pipefail

ES_HOST="${ES_HOST:-http://127.0.0.1:9200}"
RECREATE="${RECREATE:-0}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Checking Elasticsearch at ${ES_HOST} ..."
curl -fsS "${ES_HOST}" >/dev/null

create_index() {
  local name="$1"
  local body="$2"
  if [[ "${RECREATE}" == "1" ]]; then
    curl -fsS -X DELETE "${ES_HOST}/${name}" >/dev/null 2>&1 || true
    echo "Deleted index (if existed): ${name}"
  fi
  curl -fsS -X PUT "${ES_HOST}/${name}" \
    -H "Content-Type: application/json" \
    -d "${body}" >/dev/null
  echo "Created index: ${name}"
}

create_index "access-log-demo" '{
  "settings": {"number_of_shards": 1, "number_of_replicas": 0},
  "mappings": {
    "properties": {
      "@timestamp": {"type": "date"},
      "subject_account": {"type": "keyword"},
      "subject_ip": {"type": "keyword"},
      "url_pattern": {"type": "keyword"},
      "count": {"type": "long"},
      "status_freq_dict": {"type": "object", "enabled": true},
      "method_freq_dict": {"type": "object", "enabled": true},
      "xff_freq_dict": {"type": "object", "enabled": true},
      "is_intranet": {"type": "keyword"},
      "response_length_max": {"type": "double"},
      "high_worth_api_type": {"type": "keyword"},
      "attack_hw_target": {"type": "keyword"},
      "ai_app_type": {"type": "keyword"},
      "appid": {"type": "keyword"}
    }
  }
}'

create_index "t_url_info" '{
  "settings": {"number_of_shards": 1, "number_of_replicas": 0},
  "mappings": {
    "properties": {
      "url_pattern": {"type": "keyword"},
      "latest_7d_resp_size_avg": {"type": "double"},
      "latest_7d_count": {"type": "double"},
      "latest_24h_count": {"type": "double"},
      "ip_7d_dc": {"type": "double"},
      "top_methods": {"type": "text"},
      "top_status_codes": {"type": "text"},
      "create_time": {"type": "date"},
      "app_id": {"type": "keyword"}
    }
  }
}'

create_index "t_int_ip_info" '{
  "settings": {"number_of_shards": 1, "number_of_replicas": 0},
  "mappings": {
    "properties": {
      "ip": {"type": "keyword"},
      "network_area": {"type": "keyword"}
    }
  }
}'

NOW_ISO="$(date -u +"%Y-%m-%dT%H:%M:%S.000Z")"
WEEK_AGO_ISO="$(date -u -d "7 days ago" +"%Y-%m-%dT%H:%M:%S.000Z" 2>/dev/null || date -u -v-7d +"%Y-%m-%dT%H:%M:%S.000Z")"
BULK_TMP="$(mktemp)"
sed \
  -e "s/\"@timestamp\":\"now\"/\"@timestamp\":\"${NOW_ISO}\"/g" \
  -e "s/\"create_time\":\"now-7d\"/\"create_time\":\"${WEEK_AGO_ISO}\"/g" \
  "${ROOT}/02_bulk_documents.ndjson" > "${BULK_TMP}"

echo "Bulk indexing (timestamps -> ${NOW_ISO}) ..."
BULK_RESP="$(curl -fsS -X POST "${ES_HOST}/_bulk?refresh=wait_for" \
  -H "Content-Type: application/x-ndjson" \
  --data-binary @"${BULK_TMP}")"
rm -f "${BULK_TMP}"

if echo "${BULK_RESP}" | grep -q '"errors":true'; then
  echo "${BULK_RESP}" | head -c 4000
  echo ""
  echo "Bulk indexing reported errors (see above)."
  exit 1
fi

echo ""
echo "Done."
echo "  access-log-demo docs: $(curl -fsS "${ES_HOST}/access-log-demo/_count" | sed -n 's/.*"count":\([0-9]*\).*/\1/p')"
echo "  t_url_info docs:      $(curl -fsS "${ES_HOST}/t_url_info/_count" | sed -n 's/.*"count":\([0-9]*\).*/\1/p')"
echo "  t_int_ip_info docs:   $(curl -fsS "${ES_HOST}/t_int_ip_info/_count" | sed -n 's/.*"count":\([0-9]*\).*/\1/p')"
echo ""
echo "Run example_11 with initial_context.es_index = access-log-* (default matches access-log-demo)."
