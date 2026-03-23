package middleware

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
)

const testSecret = "test-secret-key-for-ci"

func init() {
	gin.SetMode(gin.TestMode)
}

// helper to create a valid token.
func makeToken(userID int, username string, exp time.Time, method jwt.SigningMethod) string {
	claims := jwt.MapClaims{
		"sub":      fmt.Sprintf("%d", userID),
		"username": username,
		"exp":      exp.Unix(),
	}
	token := jwt.NewWithClaims(method, claims)
	signed, _ := token.SignedString([]byte(testSecret))
	return signed
}

func setupAuthRouter() *gin.Engine {
	r := gin.New()
	r.Use(JWTAuth(testSecret))
	r.GET("/protected", func(c *gin.Context) {
		userID, _ := c.Get(CtxUserID)
		username, _ := c.Get(CtxUsername)
		c.JSON(http.StatusOK, gin.H{
			"user_id":  userID,
			"username": username,
		})
	})
	return r
}

func TestJWTAuthMissingHeader(t *testing.T) {
	r := setupAuthRouter()

	req := httptest.NewRequest(http.MethodGet, "/protected", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("expected 401, got %d", w.Code)
	}
}

func TestJWTAuthInvalidFormat(t *testing.T) {
	r := setupAuthRouter()

	// No "Bearer " prefix.
	req := httptest.NewRequest(http.MethodGet, "/protected", nil)
	req.Header.Set("Authorization", "Token some-token")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("expected 401, got %d", w.Code)
	}
}

func TestJWTAuthInvalidBearerOnlyOneWord(t *testing.T) {
	r := setupAuthRouter()

	req := httptest.NewRequest(http.MethodGet, "/protected", nil)
	req.Header.Set("Authorization", "BearerNoSpace")
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("expected 401, got %d", w.Code)
	}
}

func TestJWTAuthExpiredToken(t *testing.T) {
	r := setupAuthRouter()
	token := makeToken(1, "alice", time.Now().Add(-time.Hour), jwt.SigningMethodHS256)

	req := httptest.NewRequest(http.MethodGet, "/protected", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("expected 401, got %d", w.Code)
	}
}

func TestJWTAuthWrongSecret(t *testing.T) {
	r := setupAuthRouter()
	claims := jwt.MapClaims{
		"sub":      "1",
		"username": "alice",
		"exp":      time.Now().Add(time.Hour).Unix(),
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	signed, _ := token.SignedString([]byte("wrong-secret"))

	req := httptest.NewRequest(http.MethodGet, "/protected", nil)
	req.Header.Set("Authorization", "Bearer "+signed)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("expected 401, got %d", w.Code)
	}
}

func TestJWTAuthWrongSigningMethod(t *testing.T) {
	r := setupAuthRouter()

	// Create token with RSA header but HMAC signature (algorithm confusion attack).
	claims := jwt.MapClaims{
		"sub":      "1",
		"username": "alice",
		"exp":      time.Now().Add(time.Hour).Unix(),
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	// Manually set the algorithm to RS256 to simulate algorithm confusion.
	token.Header["alg"] = "RS256"
	signed, _ := token.SignedString([]byte(testSecret))

	req := httptest.NewRequest(http.MethodGet, "/protected", nil)
	req.Header.Set("Authorization", "Bearer "+signed)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("expected 401 for wrong signing method, got %d", w.Code)
	}
}

func TestJWTAuthMissingSub(t *testing.T) {
	r := setupAuthRouter()
	claims := jwt.MapClaims{
		"username": "alice",
		"exp":      time.Now().Add(time.Hour).Unix(),
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	signed, _ := token.SignedString([]byte(testSecret))

	req := httptest.NewRequest(http.MethodGet, "/protected", nil)
	req.Header.Set("Authorization", "Bearer "+signed)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("expected 401 for missing sub, got %d", w.Code)
	}
}

func TestJWTAuthNonNumericSub(t *testing.T) {
	r := setupAuthRouter()
	claims := jwt.MapClaims{
		"sub":      "not-a-number",
		"username": "alice",
		"exp":      time.Now().Add(time.Hour).Unix(),
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	signed, _ := token.SignedString([]byte(testSecret))

	req := httptest.NewRequest(http.MethodGet, "/protected", nil)
	req.Header.Set("Authorization", "Bearer "+signed)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("expected 401 for non-numeric sub, got %d", w.Code)
	}
}

func TestJWTAuthValidToken(t *testing.T) {
	r := setupAuthRouter()
	token := makeToken(42, "bob", time.Now().Add(time.Hour), jwt.SigningMethodHS256)

	req := httptest.NewRequest(http.MethodGet, "/protected", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}
}

func TestJWTAuthCaseInsensitiveBearer(t *testing.T) {
	r := setupAuthRouter()
	token := makeToken(1, "alice", time.Now().Add(time.Hour), jwt.SigningMethodHS256)

	req := httptest.NewRequest(http.MethodGet, "/protected", nil)
	req.Header.Set("Authorization", "BEARER "+token)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200 for case-insensitive Bearer, got %d", w.Code)
	}
}

func TestParseTokenFromStringValid(t *testing.T) {
	token := makeToken(5, "charlie", time.Now().Add(time.Hour), jwt.SigningMethodHS256)
	userID, username, err := ParseTokenFromString(token, testSecret)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if userID != 5 {
		t.Errorf("expected user_id 5, got %d", userID)
	}
	if username != "charlie" {
		t.Errorf("expected username 'charlie', got %q", username)
	}
}

func TestParseTokenFromStringExpired(t *testing.T) {
	token := makeToken(1, "alice", time.Now().Add(-time.Hour), jwt.SigningMethodHS256)
	_, _, err := ParseTokenFromString(token, testSecret)
	if err == nil {
		t.Error("expected error for expired token")
	}
}

func TestParseTokenFromStringWrongSecret(t *testing.T) {
	token := makeToken(1, "alice", time.Now().Add(time.Hour), jwt.SigningMethodHS256)
	_, _, err := ParseTokenFromString(token, "wrong-secret")
	if err == nil {
		t.Error("expected error for wrong secret")
	}
}
