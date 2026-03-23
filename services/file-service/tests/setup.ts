// tests/setup.ts — Global test setup
//
// Set environment variables before any module is imported so that
// config/env.config.ts reads test-friendly defaults.

process.env.NODE_ENV = "test";
process.env.SECRET_KEY = "test-secret-key-for-jwt-signing";
process.env.DATABASE_URL = "postgresql://test:test@localhost:5432/test";
process.env.KAFKA_BOOTSTRAP_SERVERS = "localhost:9092";
process.env.UPLOAD_DIR = "/tmp/file-service-test-uploads";
process.env.PORT = "0"; // Let OS pick a free port
