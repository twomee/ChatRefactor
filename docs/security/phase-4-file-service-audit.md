# Phase 4: File Service Security Audit

**Service:** File Service (Node.js/TypeScript/Express, port 8005)
**Date:** 2026-03-28
**Auditor:** Claude Code
**Scope:** OWASP Top 10 code-level review

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 3 |
| MEDIUM   | 4 |
| LOW      | 3 |
| INFO     | 2 |

---

## Findings

### [HIGH] FILE-01: Loose MIME validation allows type confusion via prefix matching

- **OWASP Category:** A08 - Software and Data Integrity Failures
- **File:** `services/file-service/src/utils/format.util.ts:116-118`
- **Description:** The MIME validation logic used prefix matching instead of exact matching. For each expected MIME type (e.g., `image/png`), it extracted the category prefix (`image/`) and checked if the detected MIME started with that prefix. This meant any MIME type in the same category would pass validation — for example, a file detected as `image/svg+xml` (which can contain JavaScript) would pass validation when uploaded as a `.png` file.
- **Impact:** An attacker could bypass MIME validation by crafting a file whose magic bytes resolve to a different MIME type in the same category. Combined with SVG's scriptable nature, this could enable stored XSS if files are ever served inline.
- **Evidence:**
  ```typescript
  // BEFORE (vulnerable) — prefix matching
  const matches = expectedMimes.some(
    (mime) => detected.mime === mime || detected.mime.startsWith(mime.split("/")[0] + "/")
  );
  ```
- **Recommendation:** Use exact MIME matching only. **[FIXED]**
- **Fix applied:** Changed to `expectedMimes.some((mime) => detected.mime === mime)` — exact match only, no prefix fallback.

---

### [HIGH] FILE-02: SVG uploads allowed without content sanitization (XSS via embedded JavaScript)

- **OWASP Category:** A03 - Injection
- **File:** `services/file-service/src/config/env.config.ts:66` and `services/file-service/src/utils/format.util.ts:100-103`
- **Description:** SVG files (`.svg`) are in the allowed extensions list but were completely excluded from MIME validation because they are text-based and have no reliable magic bytes (`file-type` returns undefined). SVG files are XML-based and can contain embedded JavaScript via `<script>` tags, `onload` event handlers, `javascript:` protocol URIs, `<foreignObject>` elements, and other XSS vectors. While downloads are served as `application/octet-stream` with `Content-Disposition: attachment`, a configuration change or proxy misconfiguration could expose this to browsers.
- **Impact:** If SVG files are ever served inline (e.g., as image thumbnails, or via a CDN misconfiguration), embedded JavaScript would execute in the user's browser, enabling session hijacking, data exfiltration, and account takeover.
- **Evidence:**
  ```typescript
  // BEFORE — SVG validation was completely skipped
  const expectedMimes = EXTENSION_MIME_MAP[extension];
  if (!expectedMimes) {
    // Text-based format with no magic bytes — skip validation
    return;  // .svg falls through here with zero checks
  }
  ```
- **Recommendation:** Add content-level scanning for SVG files that rejects known dangerous patterns. **[FIXED]**
- **Fix applied:** Added `validateSvgContent()` function that scans SVG content for `<script>`, event handlers (`on*=`), `javascript:` URIs, `<iframe>`, `<object>`, `<embed>`, `<foreignObject>`, and `data:text/html` URIs. SVGs containing these patterns are rejected with a 400 error.

---

### [HIGH] FILE-03: No authorization check on file listing and download endpoints (IDOR)

- **OWASP Category:** A01 - Broken Access Control
- **File:** `services/file-service/src/routes/file.route.ts:118-136` and `services/file-service/src/routes/file.route.ts:68-110`
- **Description:** The `GET /files/room/:roomId` endpoint returns all files for any room ID, and `GET /files/download/:fileId` serves any file by ID — both only require a valid JWT token. There is no check that the authenticated user is actually a member of the room. Any authenticated user can enumerate and download files from any room by iterating over room IDs or file IDs.
- **Impact:** Complete bypass of room-level access control. An authenticated attacker can access private conversations' file attachments, including sensitive documents shared in private rooms they don't belong to. This is an Insecure Direct Object Reference (IDOR) vulnerability.
- **Evidence:**
  ```typescript
  // GET /files/room/:roomId — no membership check
  fileRouter.get("/room/:roomId", authMiddleware as never, async (req, res) => {
    const roomId = parseInt(req.params.roomId as string, 10);
    // Immediately lists files — never checks if user belongs to roomId
    const files = await listRoomFiles(roomId);
    res.status(200).json(files);
  });

  // GET /files/download/:fileId — no ownership/membership check
  fileRouter.get("/download/:fileId", authMiddleware as never, async (req, res) => {
    const fileId = parseInt(req.params.fileId as string, 10);
    // Immediately returns file — never checks if user has access
    const record = await getFile(fileId);
    // ... streams file to response
  });
  ```
- **Recommendation:** Add a room membership check before listing or downloading files. This requires either: (a) an inter-service call to the Chat Service to verify room membership, (b) a shared database query if room membership data is accessible, or (c) embedding room membership claims in the JWT. Option (a) is the cleanest microservice pattern. **[NOT FIXED — requires cross-service coordination]**

---

### [MEDIUM] FILE-04: JWT token accepted via query parameter exposes credentials in logs and browser history

- **OWASP Category:** A07 - Identification and Authentication Failures
- **File:** `services/file-service/src/middleware/auth.middleware.ts:38-41`
- **Description:** The auth middleware falls back to accepting JWT tokens from the `?token=` query parameter when no Authorization header is present. While this is necessary for `<a href>` download links where headers cannot be set, query parameters appear in server access logs, browser history, proxy logs, Referer headers, and can be cached by intermediaries. The comment in the code acknowledges this is for browser-initiated downloads.
- **Impact:** JWT tokens in URLs can be leaked through browser history, shared URLs, proxy/CDN access logs, and Referer headers when navigating away. An attacker with access to any of these sources can hijack the user's session.
- **Evidence:**
  ```typescript
  // Fall back to ?token= query param (used by download endpoint)
  if (!token && typeof req.query.token === "string") {
    token = req.query.token;
  }
  ```
- **Recommendation:** Replace the query parameter approach with one of: (a) short-lived, single-use download tokens (generate a token that expires in 30 seconds and can only be used once), (b) a POST-based download endpoint that accepts the token in the request body, or (c) a cookie-based approach using `httpOnly` + `secure` cookies. Option (a) is the most common pattern for secure file downloads. **[NOT FIXED — requires architectural change]**

---

### [MEDIUM] FILE-05: 150MB Multer memory storage creates OOM denial-of-service risk

- **OWASP Category:** A04 - Insecure Design
- **File:** `services/file-service/src/index.ts:55-60`
- **Description:** Multer is configured with `memoryStorage()`, which buffers the entire uploaded file (up to 150MB) in Node.js process memory before the service code runs. With concurrent uploads, a modest number of simultaneous requests (e.g., 10 x 150MB = 1.5GB) can exhaust the container's memory limit, causing OOM kills and service unavailability. The single-threaded Node.js event loop also stalls while processing large buffers.
- **Impact:** Denial of service. An attacker (or even normal usage during peak hours) can crash the service by sending multiple large file uploads simultaneously. Kubernetes will restart the pod, but repeated crashes degrade availability.
- **Evidence:**
  ```typescript
  const upload = multer({
    storage: multer.memoryStorage(),  // Entire file buffered in RAM
    limits: {
      fileSize: config.maxFileSizeBytes,  // 150MB per file
    },
  });
  ```
- **Recommendation:** Switch to `multer.diskStorage()` which streams files to a temporary directory instead of RAM. Validate the file from the temp path, then move it to the final location. This limits memory usage to the streaming buffer size (~64KB) regardless of file size. **[NOT FIXED — noted as recommendation to avoid breaking core functionality]**

---

### [MEDIUM] FILE-06: Missing global Express error handler allows stack trace leaks

- **OWASP Category:** A05 - Security Misconfiguration
- **File:** `services/file-service/src/index.ts` (end of middleware chain)
- **Description:** Express's default error handler includes stack traces in responses when `NODE_ENV` is not set to `"production"`. If an unhandled error reaches the Express error handler (e.g., a middleware throws before reaching the route's `handleServiceError`), the stack trace, file paths, and internal module names would be exposed to the client. While the route-level `handleServiceError` function correctly suppresses stack traces, it only covers errors within route handlers — middleware errors (e.g., multer parsing failures, JSON parsing errors) could bypass it.
- **Impact:** Information disclosure of internal file paths, module names, Node.js version, and error details that aid attackers in crafting targeted exploits.
- **Evidence:** No global error handler was registered after routes — Express's built-in handler would be the fallback.
- **Recommendation:** Add a global Express error handler at the end of the middleware chain. **[FIXED]**
- **Fix applied:** Added a catch-all Express error handler `(err, req, res, next)` after routes that logs the error server-side but returns only `{ error: "Internal server error" }` to the client.

---

### [MEDIUM] FILE-07: Missing security response headers (X-Content-Type-Options, CSP, X-Frame-Options)

- **OWASP Category:** A05 - Security Misconfiguration
- **File:** `services/file-service/src/index.ts` and `services/file-service/src/routes/file.route.ts`
- **Description:** The service did not set `X-Content-Type-Options: nosniff`, `Content-Security-Policy`, or `X-Frame-Options` headers on responses. Without `nosniff`, browsers may MIME-sniff response content and render uploaded files as HTML/JavaScript even when served as `application/octet-stream`. Without CSP, any injected content would have unrestricted access. Without `X-Frame-Options`, responses could be embedded in iframes for clickjacking.
- **Impact:** Increases the exploitability of other vulnerabilities. If MIME sniffing occurs, uploaded files could be interpreted as HTML, enabling XSS. Missing CSP means no defense-in-depth against script execution.
- **Evidence:** No security headers were set on any response.
- **Recommendation:** Add security headers globally and on download responses specifically. **[FIXED]**
- **Fix applied:** Added global middleware setting `X-Content-Type-Options: nosniff` and `X-Frame-Options: DENY` on all responses. Added `Content-Security-Policy: default-src 'none'`, `X-Content-Type-Options: nosniff`, and `X-Frame-Options: DENY` specifically on download responses.

---

### [LOW] FILE-08: Content-Disposition header injection via filename backslash

- **OWASP Category:** A03 - Injection
- **File:** `services/file-service/src/routes/file.route.ts:85`
- **Description:** The Content-Disposition header's ASCII fallback filename stripped double quotes but not backslashes. In some parsers, a backslash can be used to escape the closing quote, potentially allowing injection of additional header parameters. While the `sanitizeFilename` function strips null bytes and CRLF (preventing full header injection), backslash-based parameter injection remains a theoretical risk depending on the downstream HTTP parser.
- **Impact:** Low — the primary defense (CRLF removal in sanitizeFilename) prevents full header injection. Backslash injection would only affect parsing of the Content-Disposition value itself, potentially causing filename confusion.
- **Evidence:**
  ```typescript
  // BEFORE — only stripped double quotes
  const safeName = record.originalName.replace(/"/g, "");
  ```
- **Recommendation:** Strip backslashes, CRLF, and quotes from the ASCII fallback filename. **[FIXED]**
- **Fix applied:** Changed to `record.originalName.replace(/["\\\r\n]/g, "")`.

---

### [LOW] FILE-09: Extension reflected in error messages without sanitization

- **OWASP Category:** A03 - Injection
- **File:** `services/file-service/src/utils/format.util.ts:52-55`
- **Description:** When a file extension is rejected, the raw extension string was included in the error message without sanitization. While JSON responses prevent classic XSS, unusual characters in the extension could cause log injection or formatting issues in downstream log aggregation tools that parse structured log output.
- **Impact:** Low — the error is returned as JSON (safe from browser XSS) but could cause log injection in tools like ELK or Splunk that parse log output.
- **Evidence:**
  ```typescript
  // BEFORE — raw extension in error message
  throw new FileValidationError(
    `File type '${extension}' is not allowed`,
    400
  );
  ```
- **Recommendation:** Sanitize the extension before embedding in error messages. **[FIXED]**
- **Fix applied:** Added `extension.replace(/[^a-z0-9.]/g, "").slice(0, 20)` to strip non-alphanumeric characters and limit length.

---

### [LOW] FILE-10: Metrics endpoint exposed without authentication

- **OWASP Category:** A01 - Broken Access Control
- **File:** `services/file-service/src/index.ts:47-50`
- **Description:** The `/metrics` Prometheus endpoint is publicly accessible without authentication. While this is common in Kubernetes deployments (where network policies restrict access), it exposes internal operational data including request rates, error rates, file upload sizes, and Kafka availability status.
- **Impact:** Information disclosure of operational metrics. An attacker can monitor traffic patterns, identify peak/off-peak hours, determine error rates, and infer system architecture.
- **Recommendation:** Restrict `/metrics` access via network policy (Kubernetes NetworkPolicy) or add basic auth. In most Kubernetes deployments, this is acceptable if the metrics port is not exposed externally — verify that Kong/ingress does not route to `/metrics`.

---

### [INFO] FILE-11: CORS configured to allow all origins

- **OWASP Category:** A05 - Security Misconfiguration
- **File:** `services/file-service/src/index.ts:32`
- **Description:** CORS is configured with `cors()` (default: all origins allowed). The code comment states Kong gateway handles CORS in production, so this is intentional for the internal service.
- **Impact:** Acceptable if Kong is the only external entry point and enforces CORS. If the file service is ever exposed directly, any origin could make authenticated requests.
- **Recommendation:** Add explicit origin allowlist as defense-in-depth, or verify Kong CORS configuration covers all cases.

---

### [INFO] FILE-12: Synchronous file I/O in upload path

- **OWASP Category:** A04 - Insecure Design
- **File:** `services/file-service/src/services/file.service.ts:78-81`
- **Description:** `fs.mkdirSync` and `fs.writeFileSync` are used in the upload path. While functionally correct, synchronous I/O blocks the Node.js event loop during disk writes, reducing throughput under load. For a 150MB file, this could block the event loop for several hundred milliseconds.
- **Impact:** Performance degradation under concurrent uploads. Not a security vulnerability per se, but contributes to the denial-of-service risk identified in FILE-05.
- **Recommendation:** Switch to `fs.promises.mkdir` and `fs.promises.writeFile` for non-blocking I/O. This is a minor change that improves concurrency.

---

## Positive Findings

The following security controls are correctly implemented and demonstrate good security practices:

1. **Path traversal prevention (defense in depth):** Both the upload path (`file.service.ts:66-75`) and download path (`file.service.ts:157-166`) verify that resolved file paths stay within the upload directory using `path.resolve()` + `startsWith()` check. This is applied even on the download path where the stored path comes from the database — exemplary defense-in-depth.

2. **Filename sanitization:** `sanitizeFilename()` correctly strips path components (including Windows-style backslashes), null bytes, CRLF characters, and leading dots. The fallback to "unnamed" prevents empty filenames. Comprehensive test coverage exists for all edge cases.

3. **Extension allowlist approach:** The service uses an allowlist (not blocklist) for file extensions, which is the correct approach. Dangerous executable extensions (`.py`, `.js`, `.html`, `.bin`) are explicitly excluded. The allowlist is defined in config, making it easy to audit.

4. **Parameterized database queries:** All Prisma queries use parameterized inputs — no raw SQL string concatenation. Prisma's query builder inherently prevents SQL injection.

5. **JWT validation:** Algorithm is pinned to HS256 (no algorithm confusion attacks). Token payload validation checks for required fields (`sub`, `username`). The `sub` field is parsed with `parseInt` and validated for NaN.

6. **Fail-fast in production:** Environment configuration uses `requireEnv()` with `process.exit(1)` in production for missing required variables like `SECRET_KEY`. This prevents running with insecure defaults.

7. **Kafka fire-and-forget with graceful degradation:** Kafka event production failures are caught and logged but don't block the upload response. The service degrades gracefully when Kafka is unavailable.

8. **Docker security:** Multi-stage build, non-root user (`appuser:appgroup`), `apk upgrade --no-cache` in production stage, health check configured.

9. **Correlation ID tracking:** Every request gets a correlation ID (from `X-Request-ID` header or generated UUID) that flows through logs and responses, enabling request tracing for incident response.

10. **Content-Disposition: attachment:** File downloads are always served as attachments with `Content-Type: application/octet-stream`, preventing browsers from rendering uploaded content inline. This is the primary defense against stored XSS via uploaded files.

11. **Error handling separation:** Route handlers use a centralized `handleServiceError()` that maps `FileValidationError` to appropriate HTTP status codes and returns generic "Internal server error" for unexpected errors — no stack traces leaked to clients.

12. **File size limit enforced at two layers:** Both Multer (middleware) and the service layer (`validateFileSize()`) enforce the 150MB limit, providing defense-in-depth against oversized uploads.
