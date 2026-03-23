package config

import (
	"os"
	"testing"
)

func TestLoadDefaults(t *testing.T) {
	// Clear env to get defaults.
	os.Unsetenv("APP_ENV")
	os.Unsetenv("PORT")
	os.Unsetenv("SECRET_KEY")
	os.Unsetenv("DATABASE_URL")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if cfg.AppEnv != "dev" {
		t.Errorf("expected AppEnv 'dev', got %q", cfg.AppEnv)
	}
	if cfg.Port != 8003 {
		t.Errorf("expected Port 8003, got %d", cfg.Port)
	}
	if cfg.LogLevel != "info" {
		t.Errorf("expected LogLevel 'info', got %q", cfg.LogLevel)
	}
	if cfg.Algorithm != "HS256" {
		t.Errorf("expected Algorithm 'HS256', got %q", cfg.Algorithm)
	}
}

func TestLoadFromEnv(t *testing.T) {
	t.Setenv("APP_ENV", "test")
	t.Setenv("PORT", "9999")
	t.Setenv("SECRET_KEY", "test-secret")
	t.Setenv("DATABASE_URL", "postgres://localhost/test")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if cfg.AppEnv != "test" {
		t.Errorf("expected AppEnv 'test', got %q", cfg.AppEnv)
	}
	if cfg.SecretKey != "test-secret" {
		t.Errorf("expected SecretKey 'test-secret', got %q", cfg.SecretKey)
	}
	if cfg.DatabaseURL != "postgres://localhost/test" {
		t.Errorf("expected DatabaseURL, got %q", cfg.DatabaseURL)
	}
}

func TestValidateFailsInProdWithoutSecretKey(t *testing.T) {
	t.Setenv("APP_ENV", "prod")
	t.Setenv("SECRET_KEY", "")
	t.Setenv("DATABASE_URL", "postgres://localhost/prod")

	_, err := Load()
	if err == nil {
		t.Error("expected validation error for missing SECRET_KEY in prod")
	}
}

func TestValidateFailsInProdWithoutDatabaseURL(t *testing.T) {
	t.Setenv("APP_ENV", "prod")
	t.Setenv("SECRET_KEY", "some-secret")
	t.Setenv("DATABASE_URL", "")

	_, err := Load()
	if err == nil {
		t.Error("expected validation error for missing DATABASE_URL in prod")
	}
}

func TestValidatePassesInDevWithMissingSecrets(t *testing.T) {
	t.Setenv("APP_ENV", "dev")
	t.Setenv("SECRET_KEY", "")
	t.Setenv("DATABASE_URL", "")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("dev should not require secrets: %v", err)
	}
	if cfg.AppEnv != "dev" {
		t.Errorf("expected AppEnv 'dev', got %q", cfg.AppEnv)
	}
}

func TestValidatePassesInProdWithAllSecrets(t *testing.T) {
	t.Setenv("APP_ENV", "prod")
	t.Setenv("SECRET_KEY", "prod-secret")
	t.Setenv("DATABASE_URL", "postgres://localhost/prod")

	_, err := Load()
	if err != nil {
		t.Fatalf("expected no error with all prod secrets set: %v", err)
	}
}

func TestIsProd(t *testing.T) {
	tests := []struct {
		env    string
		expect bool
	}{
		{"prod", true},
		{"PROD", true},
		{"Prod", true},
		{"dev", false},
		{"staging", false},
		{"", false},
	}

	for _, tt := range tests {
		t.Run(tt.env, func(t *testing.T) {
			cfg := &Config{AppEnv: tt.env}
			if got := cfg.IsProd(); got != tt.expect {
				t.Errorf("IsProd(%q) = %v, want %v", tt.env, got, tt.expect)
			}
		})
	}
}

func TestKafkaBrokerList(t *testing.T) {
	tests := []struct {
		name    string
		brokers string
		want    int
	}{
		{"single broker", "localhost:9092", 1},
		{"multiple brokers", "host1:9092,host2:9092,host3:9092", 3},
		{"with whitespace", " host1:9092 , host2:9092 ", 2},
		{"empty string", "", 0},
		{"only commas", ",,", 0},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cfg := &Config{KafkaBrokers: tt.brokers}
			got := cfg.KafkaBrokerList()
			if len(got) != tt.want {
				t.Errorf("KafkaBrokerList() returned %d brokers, want %d", len(got), tt.want)
			}
		})
	}
}
