# SentryGrid — Industrial Sensor Monitoring

SentryGrid monitors thousands of sensors across an industrial facility, turning raw
telemetry into health signals, anomaly alerts, and operator dashboards in real time.

## Requirements

- Sensors stream telemetry readings continuously; each reading is tagged with a sensor id and timestamp.
- Readings are aggregated per sensor over rolling time windows to compute health metrics (mean, variance, trend).
- An anomaly is flagged only when a metric crosses a threshold and stays across it for a sustained window — a single transient spike must not trigger an alert.
- Duplicate or flapping alerts for the same sensor are suppressed within a cooldown period so operators aren't overwhelmed.
- A critical anomaly is escalated to the on-call engineer; if it is not acknowledged within a short window, it escalates to the next on-call tier.
- Operators can update alert thresholds and sensor calibration parameters independently, without interrupting the stream.
- If a sensor stops reporting for a defined period, it is marked offline and its last known state is frozen.
- A daily rollup summarizes anomaly counts and uptime per facility zone.
