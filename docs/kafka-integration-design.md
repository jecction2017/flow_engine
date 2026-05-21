# Kafka integration (unified connector)

Kafka is integrated through the same **connectors** layer as Elasticsearch: configuration in the data dictionary, `ConnectorRegistry` binding, Starlark builtins, and subscription ingress.

## Dictionary layout

Module code: `middleware.kafka`

```yaml
middleware:
  kafka:
    defaults:
      protection:
        max_in_flight: 16
        max_rps: 100
        max_result_docs: 100
      consumer_params:
        enable_auto_commit: false
      producer_params:
        acks: all
    instances:
      soc_cluster_a:
        bootstrap_servers: ["kafka:9092"]
        auth:
          type: sasl_plaintext
          username: app
          password: secret://kafka_pwd
        topics:
          alerts:
            consumers:
              ingress:
                group_id: flow-alert-ingress
                serializers: { key: string, value: json }
                strategy: default
                params: { auto_offset_reset: latest }
            producers:
              dlq:
                serializers: { value: bytes }
      memory:
        transport: memory
        topics:
          alerts:
            consumers:
              default:
                group_id: g1
                strategy: earliest
```

### IDs

- **consumer_id**: `{cluster}.{topic}.{consumer_name}` — e.g. `soc_cluster_a.alerts.ingress`
- **producer_id**: `{cluster}.{topic}.{producer_name}` — e.g. `soc_cluster_a.alerts.dlq`

### Consume strategies

| strategy | Behaviour |
|----------|-----------|
| `default` | Consumer group committed offsets; else `auto_offset_reset` |
| `earliest` | Seek to beginning after assign |
| `latest` | Seek to end after assign |
| `offset` | Requires `offsets: {partition: offset}` |
| `timestamp` | Requires `timestamp_ms`; uses `offsets_for_times` |

Deployment `subscription.start_position` overrides the dictionary strategy.

## Starlark builtins

- `kafka_receive(consumer_id, max_records=10, timeout_ms=1000, partitions=None, strategy=None)` — bounded poll; returns envelope `{ok, data: {messages: [...]}}`
- `kafka_send(producer_id, value, key=None, partition=None, headers=None)` — produce one record

Requires optional dependency: `pip install aiokafka` or `pip install -e ".[integrations]"` for real clusters. `transport: memory` needs no broker.

## Subscription

`schedule_config.subscription.consumer_id` references the dictionary consumer. Optional overrides: `partitions`, `start_position`, `producer_id`. DLQ: `consumption.dlq.producer_id`.

## Reliability

- `ProtectionPipeline` per cluster (rate limit, concurrency, circuit breaker, timeout)
- `enable_auto_commit=false` for subscription; commit on successful run
- `ConnectorRegistry.close_all()` on dictionary re-bind / scope exit

## Monitoring

- Result envelopes include `meta.took_ms`, `consumer_id` / `producer_id`
- Structured log `business_kafka_send` on produce
- Errors use `correlation_id` from the active flow run
