# Security model and reporting

PhishGuard is a local research/development platform, not a certified phishing prevention
product. It gives model estimates and does not block navigation. Do not rely on it as the
sole control for account security.

## Implemented controls

URL checks are lexical only: no target HTTP, DNS, WHOIS, browser automation or page retrieval.
HTTP(S), length, credentials, host syntax and obvious private literals are validated. This
validator is not a reusable network-fetch allowlist. The API requires an environment-provided
key, fails startup on invalid/missing models, bounds input, minimizes validation errors and
rate-limits locally. Model export is numeric JSON with a fixed feature schema, not pickle.
The optional CNN loads only trusted local weights with PyTorch `weights_only=True`.

The Chrome extension is OFF by default. Automatic domain checks require explicit ON,
a saved session key and optional HTTP(S) website host access. Required permissions are
activeTab, storage, scripting (warning insertion), and alarms (active-tab rechecks).
Browser notifications are separately optional. There is no cookies, history or webRequest
permission. The API origin remains a fixed required host permission.

Automatic URL requests contain only the website origin; path/query/fragment, titles and page
contents are excluded. Minimal per-tab scheduling/results remain in service-worker memory,
not persistent browsing storage. OFF/key revocation aborts requests and invalidates late
results. Chrome session/local storage is restricted to trusted extension contexts; the page
warning receives sanitized text, not the API key or extension storage access. No model
strings are interpreted as HTML. Warnings do not block navigation or prove a website is a scam.

Optional visible-tab capture still uses activeTab, separate screenshot opt-in and fresh
per-capture consent. The server must advertise an enabled image model before capture.
The visible tab and consent settings are revalidated before capture and upload.
Screenshot bytes can contain personal content and are never persisted by the extension/API.
It loads no remote script and uses textContent to display responses. A malicious local process
may still bind the expected API port; use a trusted device and service startup process.

## Threat model

Protected against: accidental raw-URL logging through application events, model schema drift,
credentialed/private literal input, oversized payload memory growth, default event retention,
common archive/merge path escapes, committing a consumed message before output is acknowledged.

Not protected against: compromised OS/browser/extension, malicious concurrent filesystem writer,
poisoned training data, adversarial URLs designed around lexical features, stolen API keys,
local port impersonation, browser API implementation bugs, insecure reverse-proxy deployment,
resource exhaustion by an authorized local user, near-duplicate dataset leakage or dependency
supply-chain compromise. No formal penetration test has been performed.

## Deployment rules

Bind API and dashboard to loopback by default. Before remote use add TLS termination, connection
and idle timeouts, distributed rate limiting, per-user authentication, secret rotation, firewall
controls and log minimization. A shared static key does not offer revocation by individual user.
Dashboard does not implement a login system; do not expose its port publicly.

Kafka plaintext is for an isolated local demo. Use SASL_SSL or SSL with ACLs in production;
Python Kafka clients accept security environment variables. Spark's example helper needs
additional secure connector configuration for remote brokers. Raw topic retention and access
must be reviewed separately because raw URLs are present in explicit events.

## Reporting

No security contact address has been configured for this new repository. Before publishing,
configure a private reporting channel such as GitHub private vulnerability reporting. Do not
post real victim URLs, API keys, screenshots, passwords or personal dataset rows in public
issues. Include a minimized synthetic reproduction, dependency versions and expected behavior.

## Dependency updates

CI includes lint, tests, Bandit and pip-audit. Passing tools does not establish absence of
vulnerabilities. The tested dependency snapshot records what ran locally; broad installation
ranges can resolve differently later. Review lock refreshes and rerun tests after changes.
Spark includes bundled JVM jars that Python vulnerability scanning does not comprehensively
cover. Container images and Java/Kafka runtimes require their own scanning and patch process.


## Additional hardening in the completed revision

HTTP body reception has a deadline, declared-length checks, chunk-count and byte limits.
Only the bounded metadata-list `limit` query is accepted; URL/key query submission is rejected.
Trusted Host validation rejects unexpected hostnames. Runtime metrics keep bounded numeric
latencies/status classes only. Request IDs are server-generated, not caller tracking IDs.

SQLite files are private (0600), reject symlink paths, retain at most the configured event cap
and purge by age. Secure-delete/WAL truncation reduce residual local pages but are not a
physical secure-erasure guarantee. Failed optional-model startup closes the already-open store.

Portable tree artifacts reject malformed topology, cycles, invalid child/feature indices,
unreachable nodes, depth/size overflow and non-finite numeric parameters. V2 artifacts verify
a content fingerprint. Registry activation additionally checks immutable-file hashes and
explicit labeled-evaluation gates. A registry owner's malicious edits remain outside this trust boundary.

`.dockerignore` excludes secrets, datasets, trained artifacts and caches from build context.
Git ignores all data/model/report runtime trees, including curated derivatives and registries.
The delivered image was locally built and exercised as UID 10001 with read-only root and no
capabilities. Remote hosting, TLS ownership and an independent penetration test remain external acceptance work.


## Reviewed launcher subprocess findings

The full Bandit scan reports B404 and B603 at low severity in the managed launcher. The
launcher uses the current absolute Python interpreter and an argument list, never shell=True
or an interpolated shell command. Ports are validated integers and application paths are
local project code. These findings remain visible and are accepted for process orchestration;
no nosec suppression hides them. Medium/high severity findings are zero in the release scan.
