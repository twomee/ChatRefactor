package metrics

import (
	"testing"

	"github.com/prometheus/client_golang/prometheus"
	dto "github.com/prometheus/client_model/go"
)

// collectGauge is a test helper that collects the current value from a Gauge.
func collectGauge(g prometheus.Gauge) float64 {
	ch := make(chan prometheus.Metric, 1)
	g.Collect(ch)
	m := <-ch
	var d dto.Metric
	_ = m.Write(&d)
	return d.GetGauge().GetValue()
}

// collectCounter is a test helper that collects the current value from a Counter.
func collectCounter(c prometheus.Counter) float64 {
	ch := make(chan prometheus.Metric, 1)
	c.Collect(ch)
	m := <-ch
	var d dto.Metric
	_ = m.Write(&d)
	return d.GetCounter().GetValue()
}

// ---- HTTP metrics ----

func TestHTTPRequestsTotalRegistered(t *testing.T) {
	counter := HTTPRequestsTotal.WithLabelValues("GET", "/api/test", "200")
	before := collectCounter(counter)

	counter.Inc()
	after := collectCounter(counter)

	if after != before+1 {
		t.Errorf("expected counter to increment by 1, got before=%f after=%f", before, after)
	}
}

func TestHTTPRequestsTotalMultipleLabelCombinations(t *testing.T) {
	// Different label combinations should produce independent counters.
	c1 := HTTPRequestsTotal.WithLabelValues("GET", "/a", "200")
	c2 := HTTPRequestsTotal.WithLabelValues("POST", "/b", "201")

	before1 := collectCounter(c1)
	before2 := collectCounter(c2)

	c1.Inc()
	c2.Add(3)

	after1 := collectCounter(c1)
	after2 := collectCounter(c2)

	if after1 != before1+1 {
		t.Errorf("c1: expected +1, got before=%f after=%f", before1, after1)
	}
	if after2 != before2+3 {
		t.Errorf("c2: expected +3, got before=%f after=%f", before2, after2)
	}
}

func TestHTTPRequestDurationRegistered(t *testing.T) {
	// Verify Observe does not panic and the histogram is usable.
	observer := HTTPRequestDuration.WithLabelValues("GET", "/api/test")
	observer.Observe(0.05)
	observer.Observe(0.5)
	observer.Observe(2.0)

	// Collect and verify the metric was written.
	h := observer.(prometheus.Histogram)
	ch := make(chan prometheus.Metric, 1)
	h.Collect(ch)
	m := <-ch
	var d dto.Metric
	if err := m.Write(&d); err != nil {
		t.Fatalf("failed to write metric: %v", err)
	}
	if d.GetHistogram().GetSampleCount() < 3 {
		t.Errorf("expected at least 3 observations, got %d", d.GetHistogram().GetSampleCount())
	}
}

func TestHTTPRequestDurationBuckets(t *testing.T) {
	// Verify the histogram has the expected number of buckets.
	// The metrics.go file defines 11 buckets: .005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5, 10
	observer := HTTPRequestDuration.WithLabelValues("GET", "/buckets-test")
	observer.Observe(0.001) // below first bucket

	h := observer.(prometheus.Histogram)
	ch := make(chan prometheus.Metric, 1)
	h.Collect(ch)
	m := <-ch
	var d dto.Metric
	if err := m.Write(&d); err != nil {
		t.Fatalf("failed to write metric: %v", err)
	}

	expectedBuckets := 11
	gotBuckets := len(d.GetHistogram().GetBucket())
	if gotBuckets != expectedBuckets {
		t.Errorf("expected %d buckets, got %d", expectedBuckets, gotBuckets)
	}
}

func TestHTTPRequestsInFlightRegistered(t *testing.T) {
	before := collectGauge(HTTPRequestsInFlight)

	HTTPRequestsInFlight.Inc()
	HTTPRequestsInFlight.Inc()
	afterInc := collectGauge(HTTPRequestsInFlight)

	if afterInc != before+2 {
		t.Errorf("expected gauge to be %f after Inc, got %f", before+2, afterInc)
	}

	HTTPRequestsInFlight.Dec()
	afterDec := collectGauge(HTTPRequestsInFlight)

	if afterDec != before+1 {
		t.Errorf("expected gauge to be %f after Dec, got %f", before+1, afterDec)
	}

	// Reset to original value for test isolation.
	HTTPRequestsInFlight.Dec()
}

// ---- WebSocket metrics ----

func TestWSConnectionsActiveRegistered(t *testing.T) {
	gauge := WSConnectionsActive.WithLabelValues("room")

	before := collectGauge(gauge)
	gauge.Inc()
	after := collectGauge(gauge)

	if after != before+1 {
		t.Errorf("expected gauge +1, got before=%f after=%f", before, after)
	}

	gauge.Dec()
}

func TestWSConnectionsTotalRegistered(t *testing.T) {
	counter := WSConnectionsTotal.WithLabelValues("room")

	before := collectCounter(counter)
	counter.Inc()
	after := collectCounter(counter)

	if after != before+1 {
		t.Errorf("expected counter +1, got before=%f after=%f", before, after)
	}
}

func TestWSMessagesTotalRegistered(t *testing.T) {
	inbound := WSMessagesTotal.WithLabelValues("room", "inbound")
	outbound := WSMessagesTotal.WithLabelValues("room", "outbound")

	beforeIn := collectCounter(inbound)
	beforeOut := collectCounter(outbound)

	inbound.Inc()
	outbound.Add(5)

	afterIn := collectCounter(inbound)
	afterOut := collectCounter(outbound)

	if afterIn != beforeIn+1 {
		t.Errorf("inbound: expected +1, got before=%f after=%f", beforeIn, afterIn)
	}
	if afterOut != beforeOut+5 {
		t.Errorf("outbound: expected +5, got before=%f after=%f", beforeOut, afterOut)
	}
}

func TestWSActiveRoomsRegistered(t *testing.T) {
	before := collectGauge(WSActiveRooms)

	WSActiveRooms.Set(10)
	after := collectGauge(WSActiveRooms)

	if after != 10 {
		t.Errorf("expected gauge to be 10, got %f", after)
	}

	// Restore.
	WSActiveRooms.Set(before)
}

// ---- Kafka metrics ----

func TestKafkaProduceTotalRegistered(t *testing.T) {
	success := KafkaProduceTotal.WithLabelValues("chat.messages", "success")
	failure := KafkaProduceTotal.WithLabelValues("chat.messages", "error")

	beforeSuccess := collectCounter(success)
	beforeFailure := collectCounter(failure)

	success.Inc()
	failure.Inc()

	afterSuccess := collectCounter(success)
	afterFailure := collectCounter(failure)

	if afterSuccess != beforeSuccess+1 {
		t.Errorf("success: expected +1, got before=%f after=%f", beforeSuccess, afterSuccess)
	}
	if afterFailure != beforeFailure+1 {
		t.Errorf("failure: expected +1, got before=%f after=%f", beforeFailure, afterFailure)
	}
}

func TestKafkaConsumeTotalRegistered(t *testing.T) {
	success := KafkaConsumeTotal.WithLabelValues("chat.messages", "success")
	failure := KafkaConsumeTotal.WithLabelValues("chat.messages", "error")

	beforeSuccess := collectCounter(success)
	beforeFailure := collectCounter(failure)

	success.Add(10)
	failure.Add(2)

	afterSuccess := collectCounter(success)
	afterFailure := collectCounter(failure)

	if afterSuccess != beforeSuccess+10 {
		t.Errorf("success: expected +10, got before=%f after=%f", beforeSuccess, afterSuccess)
	}
	if afterFailure != beforeFailure+2 {
		t.Errorf("failure: expected +2, got before=%f after=%f", beforeFailure, afterFailure)
	}
}

// ---- Database metrics ----

func TestDBPoolActiveConnsRegistered(t *testing.T) {
	DBPoolActiveConns.Set(5)
	val := collectGauge(DBPoolActiveConns)
	if val != 5 {
		t.Errorf("expected 5, got %f", val)
	}
}

func TestDBPoolIdleConnsRegistered(t *testing.T) {
	DBPoolIdleConns.Set(3)
	val := collectGauge(DBPoolIdleConns)
	if val != 3 {
		t.Errorf("expected 3, got %f", val)
	}
}

func TestDBPoolTotalConnsRegistered(t *testing.T) {
	DBPoolTotalConns.Set(8)
	val := collectGauge(DBPoolTotalConns)
	if val != 8 {
		t.Errorf("expected 8, got %f", val)
	}
}

// ---- Business metrics ----

func TestRoomsCreatedTotalRegistered(t *testing.T) {
	before := collectCounter(RoomsCreatedTotal)
	RoomsCreatedTotal.Inc()
	after := collectCounter(RoomsCreatedTotal)

	if after != before+1 {
		t.Errorf("expected +1, got before=%f after=%f", before, after)
	}
}

func TestPMsSentTotalRegistered(t *testing.T) {
	before := collectCounter(PMsSentTotal)
	PMsSentTotal.Inc()
	after := collectCounter(PMsSentTotal)

	if after != before+1 {
		t.Errorf("expected +1, got before=%f after=%f", before, after)
	}
}

// ---- Cross-cutting tests ----

func TestAllMetricsDescribable(t *testing.T) {
	// Verify every metric can Describe itself without panicking.
	// This catches registration issues or duplicate metric names.
	collectors := []prometheus.Collector{
		HTTPRequestsTotal,
		HTTPRequestDuration,
		HTTPRequestsInFlight,
		WSConnectionsActive,
		WSConnectionsTotal,
		WSMessagesTotal,
		WSActiveRooms,
		KafkaProduceTotal,
		KafkaConsumeTotal,
		DBPoolActiveConns,
		DBPoolIdleConns,
		DBPoolTotalConns,
		RoomsCreatedTotal,
		PMsSentTotal,
	}

	for _, c := range collectors {
		ch := make(chan *prometheus.Desc, 10)
		c.Describe(ch)
		close(ch)

		count := 0
		for desc := range ch {
			if desc == nil {
				t.Error("got nil descriptor")
			}
			count++
		}
		if count == 0 {
			t.Error("collector produced zero descriptors")
		}
	}
}

func TestMetricNamesAreUnique(t *testing.T) {
	// Gather all descriptions and verify no duplicates.
	collectors := []prometheus.Collector{
		HTTPRequestsTotal,
		HTTPRequestDuration,
		HTTPRequestsInFlight,
		WSConnectionsActive,
		WSConnectionsTotal,
		WSMessagesTotal,
		WSActiveRooms,
		KafkaProduceTotal,
		KafkaConsumeTotal,
		DBPoolActiveConns,
		DBPoolIdleConns,
		DBPoolTotalConns,
		RoomsCreatedTotal,
		PMsSentTotal,
	}

	seen := make(map[string]bool)
	for _, c := range collectors {
		ch := make(chan *prometheus.Desc, 10)
		c.Describe(ch)
		close(ch)
		for desc := range ch {
			name := desc.String()
			if seen[name] {
				t.Errorf("duplicate metric descriptor: %s", name)
			}
			seen[name] = true
		}
	}
}
