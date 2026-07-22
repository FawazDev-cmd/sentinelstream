# SentinelStream — Current State

## Current Status

Days 1–4 are complete. SentinelStream currently provides validated single-event ingestion into a bounded, non-durable, in-process asynchronous queue.

## Day 4 — Asynchronous Queue and Worker Lifecycle

The implemented flow is:

```text
HTTP JSON request
        ↓
Pydantic request validation
        ↓
IngestionService normalization and LogEvent construction
        ↓
Non-blocking publication to bounded in-process queue
        ↓
One lifespan-managed background worker
        ↓
Injected asynchronous EventProcessor
```

HTTP 202 means the trusted event successfully entered the in-process queue. It does not mean processing or persistence completed. Queue exhaustion returns HTTP 503 without dropping or replacing an already queued event.

The worker isolates and safely logs ordinary processor failures, marks every dequeued item complete, and continues with later events. Shutdown attempts graceful queue draining for the configured bounded duration, then cancels and awaits the worker cleanly.

The queue is not durable or distributed. Queued or processing events may be lost on process crashes or forced termination. There is no persistence, anomaly detection, incident generation, retry, dead-letter queue, or Day 5 functionality.
