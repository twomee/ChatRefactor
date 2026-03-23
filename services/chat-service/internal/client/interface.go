package client

import "context"

// UserLookup defines the interface for looking up users from the auth service.
// Handlers depend on this interface so the auth client can be mocked in tests.
type UserLookup interface {
	GetUserByUsername(ctx context.Context, username string) (*UserResponse, error)
	Ping(ctx context.Context) error
}

// Compile-time check that AuthClient implements UserLookup.
var _ UserLookup = (*AuthClient)(nil)
