// Package middleware provides Gin middleware for auth, correlation, etc.
package middleware

import (
	"context"
	"fmt"
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"github.com/redis/go-redis/v9"
)

// contextKey constants for values stored in Gin context.
const (
	CtxUserID   = "user_id"
	CtxUsername = "username"
)

// JWTAuth returns a Gin middleware that validates Bearer tokens using the
// shared HS256 secret. On success it sets user_id (int) and username (string)
// in the Gin context so downstream handlers can access them.
//
// If rdb is non-nil, the token is also checked against the Redis blacklist so
// that tokens revoked by the auth-service on logout are rejected here too.
// When Redis is unavailable:
//   - isProd=true  → fail closed (reject the request)
//   - isProd=false → fail open  (log a warning and continue)
//
// The token payload follows the monolith convention:
//
//	{ "sub": "<user_id>", "username": "<username>", ... }
func JWTAuth(secretKey string, rdb *redis.Client, isProd bool) gin.HandlerFunc {
	return func(c *gin.Context) {
		authHeader := c.GetHeader("Authorization")
		if authHeader == "" {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{
				"detail": "Missing Authorization header",
			})
			return
		}

		parts := strings.SplitN(authHeader, " ", 2)
		if len(parts) != 2 || !strings.EqualFold(parts[0], "bearer") {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{
				"detail": "Invalid Authorization header format",
			})
			return
		}

		tokenStr := parts[1]
		claims, err := parseToken(tokenStr, secretKey)
		if err != nil {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{
				"detail": "Invalid or expired token",
			})
			return
		}

		// Check Redis blacklist — rejects tokens revoked on logout
		if rdb != nil {
			if blacklisted := isBlacklisted(c.Request.Context(), rdb, tokenStr, isProd); blacklisted {
				c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{
					"detail": "Token has been revoked",
				})
				return
			}
		}

		c.Set(CtxUserID, claims.UserID)
		c.Set(CtxUsername, claims.Username)
		c.Next()
	}
}

// isBlacklisted checks whether the token exists in the Redis blacklist.
// Returns true if the token should be rejected (either blacklisted or Redis error in prod).
func isBlacklisted(ctx context.Context, rdb *redis.Client, tokenStr string, isProd bool) bool {
	_, err := rdb.Get(ctx, "blacklist:"+tokenStr).Result()
	if err == nil {
		// Key found — token is revoked
		return true
	}
	if err == redis.Nil {
		// Key not found — token is valid
		return false
	}
	// Redis connection error
	if isProd {
		return true // fail closed in production
	}
	return false // fail open in dev/staging
}

// ChatClaims holds the fields we extract from the JWT payload.
type ChatClaims struct {
	jwt.RegisteredClaims
	Username string `json:"username"`
	UserID   int    // parsed from "sub"
}

// parseToken validates a JWT string and extracts ChatClaims.
func parseToken(tokenStr, secret string) (*ChatClaims, error) {
	token, err := jwt.ParseWithClaims(tokenStr, &ChatClaims{}, func(t *jwt.Token) (interface{}, error) {
		if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", t.Header["alg"])
		}
		return []byte(secret), nil
	})
	if err != nil {
		return nil, err
	}

	claims, ok := token.Claims.(*ChatClaims)
	if !ok || !token.Valid {
		return nil, fmt.Errorf("invalid token claims")
	}

	// The monolith stores user_id in the "sub" claim as a string.
	sub, err := claims.GetSubject()
	if err != nil || sub == "" {
		return nil, fmt.Errorf("missing sub claim")
	}

	var userID int
	if _, err := fmt.Sscanf(sub, "%d", &userID); err != nil {
		return nil, fmt.Errorf("sub is not a valid user ID: %w", err)
	}
	claims.UserID = userID

	return claims, nil
}

// ParseTokenFromString is exported for WebSocket handlers that receive the
// token via query parameter rather than Authorization header.
func ParseTokenFromString(tokenStr, secret string) (int, string, error) {
	claims, err := parseToken(tokenStr, secret)
	if err != nil {
		return 0, "", err
	}
	return claims.UserID, claims.Username, nil
}

// CheckBlacklist checks a token string against the Redis blacklist.
// Used by WebSocket handlers that authenticate via query param (not middleware).
// Returns true if the token is revoked and the connection should be refused.
func CheckBlacklist(ctx context.Context, rdb *redis.Client, tokenStr string, isProd bool) bool {
	if rdb == nil {
		return false
	}
	return isBlacklisted(ctx, rdb, tokenStr, isProd)
}
