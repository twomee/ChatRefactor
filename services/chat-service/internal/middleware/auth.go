// Package middleware provides Gin middleware for auth, correlation, etc.
package middleware

import (
	"fmt"
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
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
// The token payload follows the monolith convention:
//
//	{ "sub": "<user_id>", "username": "<username>", ... }
func JWTAuth(secretKey string) gin.HandlerFunc {
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

		c.Set(CtxUserID, claims.UserID)
		c.Set(CtxUsername, claims.Username)
		c.Next()
	}
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
