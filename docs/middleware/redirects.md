# HostnameRedirectMiddleware

Hostname redirect configuration for HostnameRedirectMiddleware
Performs HTTP 301 redirects based on incoming request hostname patterns.

The middleware is configured with an ENV variable of the following format:

Environment variable format (comma-separated list):
  REDIRECT_HOSTNAMES=from_pattern:to_hostname,from_pattern:to_hostname,...

Examples:
  # Single rule - redirect any subdomain
  REDIRECT_HOSTNAMES=*.app.example.com:app.example.com

  # Multiple rules
  REDIRECT_HOSTNAMES=*.app.example.com:app.example.com,*.old.example.com:new.example.com

  # With port number in target
  REDIRECT_HOSTNAMES=*.dev.local:localhost:8000

  # Exact hostname match (no wildcard)
  REDIRECT_HOSTNAMES=staging.myapp.com:myapp.com

Wildcard rules:
  - '*' matches exactly ONE subdomain level (letters, numbers, hyphens)
  - '*.example.com' matches 'test.example.com' but NOT 'foo.bar.example.com'
  - Matched part cannot contain periods or start/end with hyphens

Behavior:
  - HTTP 301 (permanent redirect) is returned when pattern matches
  - Original path, query string, and scheme (http/https) are preserved
  - First matching pattern wins (order matters)
  - Redirects are logged to application logs and sent to Sentry
