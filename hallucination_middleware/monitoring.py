"""
Monitoring Module — Comprehensive observability for the hallucination detection system.

Provides:
- Metrics collection and aggregation
- Health checks and status monitoring
- Performance tracking (latency, throughput)
- Error tracking and alerting
- Resource utilization monitoring
- Distributed tracing support
"""
import asyncio
import logging
import time
import json
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from collections import defaultdict
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


@dataclass
class MetricPoint:
    """Single metric data point."""
    timestamp: float
    value: float
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class MetricSeries:
    """Time series of metric data points."""
    name: str
    description: str
    unit: str
    points: List[MetricPoint] = field(default_factory=list)
    
    def add(self, value: float, labels: Dict[str, str] = None) -> None:
        """Add a data point to the series."""
        self.points.append(MetricPoint(
            timestamp=time.time(),
            value=value,
            labels=labels or {}
        ))
    
    def get_recent(self, seconds: int = 300) -> List[MetricPoint]:
        """Get data points from the last N seconds."""
        cutoff = time.time() - seconds
        return [p for p in self.points if p.timestamp >= cutoff]
    
    def avg(self, seconds: int = 300) -> float:
        """Calculate average value over the last N seconds."""
        recent = self.get_recent(seconds)
        if not recent:
            return 0.0
        return sum(p.value for p in recent) / len(recent)
    
    def max(self, seconds: int = 300) -> float:
        """Get maximum value over the last N seconds."""
        recent = self.get_recent(seconds)
        if not recent:
            return 0.0
        return max(p.value for p in recent)
    
    def min(self, seconds: int = 300) -> float:
        """Get minimum value over the last N seconds."""
        recent = self.get_recent(seconds)
        if not recent:
            return 0.0
        return min(p.value for p in recent)
    
    def count(self, seconds: int = 300) -> int:
        """Count data points in the last N seconds."""
        return len(self.get_recent(seconds))
    
    def percentile(self, percentile: float, seconds: int = 300) -> float:
        """Calculate percentile value over the last N seconds."""
        recent = self.get_recent(seconds)
        if not recent:
            return 0.0
        values = sorted(p.value for p in recent)
        index = int(len(values) * percentile / 100)
        return values[min(index, len(values) - 1)]


class MetricsCollector:
    """
    Central metrics collection system.
    
    Tracks:
    - Request latency (p50, p95, p99)
    - Throughput (requests/second, claims/second)
    - Error rates
    - Cache hit rates
    - LLM API call counts and costs
    - Knowledge base statistics
    """
    
    def __init__(self, max_points_per_series: int = 10000):
        self.max_points = max_points_per_series
        self._series: Dict[str, MetricSeries] = {}
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = {}
        self._lock = asyncio.Lock()
        
        # Initialize standard metrics
        self._init_standard_metrics()
    
    def _init_standard_metrics(self) -> None:
        """Initialize standard metric series."""
        self._series["request_latency_ms"] = MetricSeries(
            name="request_latency_ms",
            description="Request processing latency in milliseconds",
            unit="ms"
        )
        self._series["claims_per_request"] = MetricSeries(
            name="claims_per_request",
            description="Number of claims extracted per request",
            unit="claims"
        )
        self._series["verification_time_ms"] = MetricSeries(
            name="verification_time_ms",
            description="Time spent on claim verification",
            unit="ms"
        )
        self._series["llm_call_duration_ms"] = MetricSeries(
            name="llm_call_duration_ms",
            description="LLM API call duration",
            unit="ms"
        )
        self._series["cache_hit_rate"] = MetricSeries(
            name="cache_hit_rate",
            description="Cache hit rate percentage",
            unit="%"
        )
        self._series["error_rate"] = MetricSeries(
            name="error_rate",
            description="Error rate percentage",
            unit="%"
        )
        self._series["throughput_rps"] = MetricSeries(
            name="throughput_rps",
            description="Requests per second",
            unit="req/s"
        )
        self._series["llm_cost_usd"] = MetricSeries(
            name="llm_cost_usd",
            description="Estimated LLM API costs",
            unit="USD"
        )
    
    def record_latency(self, latency_ms: float, labels: Dict[str, str] = None) -> None:
        """Record request latency."""
        self._series["request_latency_ms"].add(latency_ms, labels)
    
    def record_claims(self, count: int) -> None:
        """Record number of claims in a request."""
        self._series["claims_per_request"].add(count)
    
    def record_verification_time(self, time_ms: float) -> None:
        """Record verification processing time."""
        self._series["verification_time_ms"].add(time_ms)
    
    def record_llm_call(self, duration_ms: float, provider: str = None) -> None:
        """Record LLM API call duration."""
        labels = {"provider": provider} if provider else None
        self._series["llm_call_duration_ms"].add(duration_ms, labels)
    
    def record_cache_hit_rate(self, rate: float) -> None:
        """Record cache hit rate."""
        self._series["cache_hit_rate"].add(rate)
    
    def record_error(self, error_type: str = None) -> None:
        """Record an error occurrence."""
        self._counters["total_errors"] += 1
        if error_type:
            self._counters[f"errors_{error_type}"] += 1
    
    def record_request(self) -> None:
        """Record a request."""
        self._counters["total_requests"] += 1
    
    def record_cache_hit(self) -> None:
        """Record a cache hit."""
        self._counters["cache_hits"] += 1
    
    def record_cache_miss(self) -> None:
        """Record a cache miss."""
        self._counters["cache_misses"] += 1
    
    def record_llm_cost(self, cost_usd: float, provider: str = None) -> None:
        """Record LLM API cost."""
        labels = {"provider": provider} if provider else None
        self._series["llm_cost_usd"].add(cost_usd, labels)
        self._counters["total_llm_cost"] += cost_usd
    
    def set_gauge(self, name: str, value: float) -> None:
        """Set a gauge value."""
        self._gauges[name] = value
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics."""
        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "latency": {
                "p50_ms": self._series["request_latency_ms"].percentile(50),
                "p95_ms": self._series["request_latency_ms"].percentile(95),
                "p99_ms": self._series["request_latency_ms"].percentile(99),
                "avg_ms": self._series["request_latency_ms"].avg(),
            },
            "throughput": {
                "requests_total": self._counters.get("total_requests", 0),
                "requests_per_second": self._series["throughput_rps"].avg(60),
            },
            "cache": {
                "hits": self._counters.get("cache_hits", 0),
                "misses": self._counters.get("cache_misses", 0),
                "hit_rate": self._calculate_cache_hit_rate(),
            },
            "errors": {
                "total": self._counters.get("total_errors", 0),
                "by_type": {
                    k.replace("errors_", ""): v 
                    for k, v in self._counters.items() 
                    if k.startswith("errors_")
                },
            },
            "costs": {
                "total_usd": self._counters.get("total_llm_cost", 0.0),
                "recent_usd": self._series["llm_cost_usd"].avg(3600),  # Last hour
            },
        }
    
    def _calculate_cache_hit_rate(self) -> float:
        """Calculate current cache hit rate."""
        hits = self._counters.get("cache_hits", 0)
        misses = self._counters.get("cache_misses", 0)
        total = hits + misses
        if total == 0:
            return 0.0
        return hits / total
    
    def get_health(self) -> Dict[str, Any]:
        """Get health status."""
        stats = self.get_stats()
        
        # Determine health status
        error_rate = 0.0
        if stats["throughput"]["requests_total"] > 0:
            error_rate = stats["errors"]["total"] / stats["throughput"]["requests_total"]
        
        status = "healthy"
        if error_rate > 0.1:  # >10% error rate
            status = "degraded"
        if error_rate > 0.25:  # >25% error rate
            status = "unhealthy"
        
        return {
            "status": status,
            "error_rate": error_rate,
            "latency_p95_ms": stats["latency"]["p95_ms"],
            "cache_hit_rate": stats["cache"]["hit_rate"],
            "requests_total": stats["throughput"]["requests_total"],
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }


class AlertManager:
    """
    Alert management system for monitoring and notification.
    
    Features:
    - Threshold-based alerts
    - Rate-of-change alerts
    - Alert deduplication
    - Alert history
    """
    
    def __init__(self, metrics: MetricsCollector):
        self.metrics = metrics
        self._alerts: Dict[str, Dict[str, Any]] = {}
        self._alert_history: List[Dict[str, Any]] = []
        self._callbacks: List[Callable] = []
        self._lock = asyncio.Lock()
        
        # Default alert thresholds
        self.thresholds = {
            "error_rate": 0.10,  # 10% error rate
            "latency_p95_ms": 30000,  # 30 seconds
            "cache_hit_rate_low": 0.20,  # <20% cache hit rate
            "llm_cost_per_hour": 10.0,  # $10/hour
        }
    
    def add_callback(self, callback: Callable) -> None:
        """Add alert callback function."""
        self._callbacks.append(callback)
    
    async def check_alerts(self) -> List[Dict[str, Any]]:
        """Check all alert conditions and trigger alerts."""
        alerts = []
        stats = self.metrics.get_stats()
        health = self.metrics.get_health()
        
        async with self._lock:
            # Error rate alert
            if health["error_rate"] > self.thresholds["error_rate"]:
                alert = self._create_alert(
                    "high_error_rate",
                    f"Error rate is {health['error_rate']:.1%} (threshold: {self.thresholds['error_rate']:.1%})",
                    "critical"
                )
                alerts.append(alert)
            
            # Latency alert
            if health["latency_p95_ms"] > self.thresholds["latency_p95_ms"]:
                alert = self._create_alert(
                    "high_latency",
                    f"P95 latency is {health['latency_p95_ms']:.0f}ms (threshold: {self.thresholds['latency_p95_ms']:.0f}ms)",
                    "warning"
                )
                alerts.append(alert)
            
            # Cache hit rate alert
            if stats["cache"]["hit_rate"] < self.thresholds["cache_hit_rate_low"]:
                alert = self._create_alert(
                    "low_cache_hit_rate",
                    f"Cache hit rate is {stats['cache']['hit_rate']:.1%} (threshold: {self.thresholds['cache_hit_rate_low']:.1%})",
                    "warning"
                )
                alerts.append(alert)
            
            # Cost alert
            if stats["costs"]["recent_usd"] > self.thresholds["llm_cost_per_hour"]:
                alert = self._create_alert(
                    "high_cost",
                    f"LLM cost is ${stats['costs']['recent_usd']:.2f}/hour (threshold: ${self.thresholds['llm_cost_per_hour']:.2f}/hour)",
                    "warning"
                )
                alerts.append(alert)
            
            # Trigger callbacks for new alerts
            for alert in alerts:
                if alert["is_new"]:
                    for callback in self._callbacks:
                        try:
                            if asyncio.iscoroutinefunction(callback):
                                await callback(alert)
                            else:
                                callback(alert)
                        except Exception as exc:
                            logger.error(f"Alert callback failed: {exc}")
        
        return alerts
    
    def _create_alert(
        self, 
        alert_type: str, 
        message: str, 
        severity: str
    ) -> Dict[str, Any]:
        """Create an alert record."""
        is_new = alert_type not in self._alerts
        
        alert = {
            "type": alert_type,
            "message": message,
            "severity": severity,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "is_new": is_new,
            "first_seen": self._alerts.get(alert_type, {}).get("first_seen", datetime.utcnow().isoformat() + "Z"),
            "count": self._alerts.get(alert_type, {}).get("count", 0) + 1,
        }
        
        self._alerts[alert_type] = alert
        self._alert_history.append(alert)
        
        # Limit history size
        if len(self._alert_history) > 1000:
            self._alert_history = self._alert_history[-500:]
        
        return alert
    
    def get_alerts(self) -> List[Dict[str, Any]]:
        """Get current active alerts."""
        return list(self._alerts.values())
    
    def get_alert_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get alert history."""
        return self._alert_history[-limit:]
    
    def clear_alert(self, alert_type: str) -> None:
        """Clear a specific alert."""
        if alert_type in self._alerts:
            del self._alerts[alert_type]
    
    def clear_all_alerts(self) -> None:
        """Clear all alerts."""
        self._alerts.clear()


# ── Request Tracing ────────────────────────────────────────────────────────

@dataclass
class TraceSpan:
    """Represents a span in a distributed trace."""
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    operation: str
    start_time: float
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    status: str = "ok"  # ok, error
    error: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)
    
    def finish(self, status: str = "ok", error: str = None) -> None:
        """Finish the span."""
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        self.status = status
        self.error = error


class Tracer:
    """
    Simple distributed tracer for request tracking.
    
    Features:
    - Trace ID propagation
    - Span creation and management
    - Context management
    """
    
    def __init__(self):
        self._active_spans: Dict[str, TraceSpan] = {}
        self._trace_history: List[TraceSpan] = []
        self._lock = asyncio.Lock()
    
    def start_trace(self, operation: str) -> TraceSpan:
        """Start a new trace."""
        import uuid
        trace_id = uuid.uuid4().hex[:16]
        span_id = uuid.uuid4().hex[:8]
        
        span = TraceSpan(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=None,
            operation=operation,
            start_time=time.time(),
        )
        
        self._active_spans[span_id] = span
        return span
    
    def start_span(self, operation: str, parent: TraceSpan) -> TraceSpan:
        """Start a child span."""
        import uuid
        span_id = uuid.uuid4().hex[:8]
        
        span = TraceSpan(
            trace_id=parent.trace_id,
            span_id=span_id,
            parent_span_id=parent.span_id,
            operation=operation,
            start_time=time.time(),
        )
        
        self._active_spans[span_id] = span
        return span
    
    def finish_span(self, span: TraceSpan, status: str = "ok", error: str = None) -> None:
        """Finish a span."""
        span.finish(status, error)
        
        if span.span_id in self._active_spans:
            del self._active_spans[span.span_id]
        
        self._trace_history.append(span)
        
        # Limit history size
        if len(self._trace_history) > 10000:
            self._trace_history = self._trace_history[-5000:]
    
    @asynccontextmanager
    async def trace(self, operation: str):
        """Context manager for tracing."""
        span = self.start_trace(operation)
        try:
            yield span
            self.finish_span(span, "ok")
        except Exception as exc:
            self.finish_span(span, "error", str(exc))
            raise
    
    @asynccontextmanager
    async def span(self, operation: str, parent: TraceSpan):
        """Context manager for child spans."""
        child = self.start_span(operation, parent)
        try:
            yield child
            self.finish_span(child, "ok")
        except Exception as exc:
            self.finish_span(child, "error", str(exc))
            raise
    
    def get_trace(self, trace_id: str) -> List[TraceSpan]:
        """Get all spans for a trace."""
        return [s for s in self._trace_history if s.trace_id == trace_id]


# ── Global Instances ───────────────────────────────────────────────────────

_metrics: Optional[MetricsCollector] = None
_alerts: Optional[AlertManager] = None
_tracer: Optional[Tracer] = None


def get_metrics() -> MetricsCollector:
    """Get or create global metrics collector."""
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics


def get_alerts() -> AlertManager:
    """Get or create global alert manager."""
    global _alerts
    if _alerts is None:
        _alerts = AlertManager(get_metrics())
    return _alerts


def get_tracer() -> Tracer:
    """Get or create global tracer."""
    global _tracer
    if _tracer is None:
        _tracer = Tracer()
    return _tracer


async def run_health_check() -> Dict[str, Any]:
    """Run comprehensive health check."""
    metrics = get_metrics()
    alerts = get_alerts()
    
    # Check alerts
    new_alerts = await alerts.check_alerts()
    
    # Get health status
    health = metrics.get_health()
    health["active_alerts"] = len(alerts.get_alerts())
    health["new_alerts"] = len(new_alerts)
    
    return health