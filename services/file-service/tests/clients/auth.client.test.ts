// tests/clients/auth.client.test.ts — Unit tests for the Auth Service client
//
// Tests getUserByUsername caching behaviour and HTTP handling.
// Uses vi.stubGlobal to replace the global fetch without touching the network.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { getUserByUsername, clearAuthCache } from "../../src/clients/auth.client.js";

function makeResponse(status: number, body: unknown): Response {
  return {
    status,
    ok: status >= 200 && status < 300,
    json: vi.fn().mockResolvedValue(body),
  } as unknown as Response;
}

describe("auth.client / getUserByUsername", () => {
  const mockFetch = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("fetch", mockFetch);
    clearAuthCache(); // start each test with empty cache
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("fetches user from auth service when not cached", async () => {
    const user = { id: 7, username: "alice" };
    mockFetch.mockResolvedValue(makeResponse(200, user));

    const result = await getUserByUsername("alice");

    expect(result).toEqual(user);
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/auth/users/by-username/alice"),
      expect.objectContaining({ signal: expect.anything() }),
    );
  });

  it("returns cached user on second call without fetching again", async () => {
    const user = { id: 7, username: "alice" };
    mockFetch.mockResolvedValue(makeResponse(200, user));

    const first = await getUserByUsername("alice");
    const second = await getUserByUsername("alice");

    expect(first).toEqual(user);
    expect(second).toEqual(user);
    // fetch should only have been called once — second call uses cache
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("returns null and caches null when auth service returns 404", async () => {
    mockFetch.mockResolvedValue(makeResponse(404, { detail: "not found" }));

    const result = await getUserByUsername("nobody");

    expect(result).toBeNull();
    expect(mockFetch).toHaveBeenCalledTimes(1);

    // Second call should return cached null without another fetch
    const result2 = await getUserByUsername("nobody");
    expect(result2).toBeNull();
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("throws when auth service returns a non-OK, non-404 status", async () => {
    mockFetch.mockResolvedValue(makeResponse(500, { detail: "internal error" }));

    await expect(getUserByUsername("alice")).rejects.toThrow(
      "Auth service returned 500",
    );
  });

  it("throws when fetch itself rejects (network error)", async () => {
    mockFetch.mockRejectedValue(new Error("ECONNREFUSED"));

    await expect(getUserByUsername("alice")).rejects.toThrow("ECONNREFUSED");
  });
});

describe("auth.client / clearAuthCache", () => {
  const mockFetch = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("fetch", mockFetch);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    clearAuthCache();
  });

  it("clears cached entries so the next call re-fetches", async () => {
    const user = { id: 3, username: "bob" };
    mockFetch.mockResolvedValue(makeResponse(200, user));

    // Prime the cache
    await getUserByUsername("bob");
    expect(mockFetch).toHaveBeenCalledTimes(1);

    // Clear cache and fetch again — should call fetch a second time
    clearAuthCache();
    await getUserByUsername("bob");
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });
});
