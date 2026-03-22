// Package config provides application configuration loaded from environment
// variables with Viper. Production fails fast on missing required values.
package config

import (
	"fmt"
	"strings"

	"github.com/spf13/viper"
)

// Config holds all service configuration values.
type Config struct {
	AppEnv   string `mapstructure:"APP_ENV"`
	Port     int    `mapstructure:"PORT"`
	LogLevel string `mapstructure:"LOG_LEVEL"`

	// Database
	DatabaseURL string `mapstructure:"DATABASE_URL"`

	// Redis
	RedisURL string `mapstructure:"REDIS_URL"`

	// Kafka
	KafkaBrokers string `mapstructure:"KAFKA_BOOTSTRAP_SERVERS"`

	// Security
	SecretKey string `mapstructure:"SECRET_KEY"`
	Algorithm string `mapstructure:"ALGORITHM"`

	// Downstream services
	AuthServiceURL    string `mapstructure:"AUTH_SERVICE_URL"`
	MessageServiceURL string `mapstructure:"MESSAGE_SERVICE_URL"`
}

// Load reads configuration from environment variables and .env file.
// It fails fast in production if required variables are missing.
func Load() (*Config, error) {
	v := viper.New()

	// Defaults for local development — production must set all required vars.
	v.SetDefault("APP_ENV", "dev")
	v.SetDefault("PORT", 8003)
	v.SetDefault("LOG_LEVEL", "info")
	v.SetDefault("ALGORITHM", "HS256")
	v.SetDefault("REDIS_URL", "redis://localhost:6379/0")
	v.SetDefault("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
	v.SetDefault("AUTH_SERVICE_URL", "http://localhost:8001")
	v.SetDefault("MESSAGE_SERVICE_URL", "http://localhost:8002")

	// Read .env file if present (not required).
	v.SetConfigName(".env")
	v.SetConfigType("env")
	v.AddConfigPath(".")
	v.AddConfigPath("../..")
	_ = v.ReadInConfig() // ignore missing .env — we fall through to env vars

	v.AutomaticEnv()

	var cfg Config
	if err := v.Unmarshal(&cfg); err != nil {
		return nil, fmt.Errorf("config unmarshal: %w", err)
	}

	if err := cfg.validate(); err != nil {
		return nil, err
	}

	return &cfg, nil
}

// validate enforces required configuration. In production, missing secrets
// cause an immediate, loud failure rather than a silent bad default.
func (c *Config) validate() error {
	isProd := strings.EqualFold(c.AppEnv, "prod")

	required := map[string]string{
		"SECRET_KEY":   c.SecretKey,
		"DATABASE_URL": c.DatabaseURL,
	}

	for key, val := range required {
		if val == "" && isProd {
			return fmt.Errorf("FATAL: required environment variable %q is not set", key)
		}
	}

	return nil
}

// IsProd returns true when running in production mode.
func (c *Config) IsProd() bool {
	return strings.EqualFold(c.AppEnv, "prod")
}

// KafkaBrokerList splits the comma-separated broker string into a slice.
func (c *Config) KafkaBrokerList() []string {
	brokers := strings.Split(c.KafkaBrokers, ",")
	out := make([]string, 0, len(brokers))
	for _, b := range brokers {
		if trimmed := strings.TrimSpace(b); trimmed != "" {
			out = append(out, trimmed)
		}
	}
	return out
}
