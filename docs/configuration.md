# Configuration reference

Environment settings are read by the API factory at startup. Changes require restart. Training
and Spark batch configuration are explicit CLI arguments. Reference YAML files are versioned
and validated by `read_yaml`, but they are not silently merged into runtime settings. This
avoids preserving old settings that suggest features are enabled when they are not implemented.

| Environment variable | Default / requirement | Effect |
| --- | --- | --- |
| PHISHGUARD_API_KEY | Required, 32+ random characters | Shared API authentication |
| PHISHGUARD_MODEL | models/trained/url-model.json | Trusted numeric JSON URL artifact |
| PHISHGUARD_DB | data/predictions.db | Opened only when storage is enabled |
| PHISHGUARD_STORE_EVENTS | false | Opt in to minimized metadata retention |
| PHISHGUARD_HMAC_KEY | Required if storing events | Separate 32+ character keyed digest secret |
| PHISHGUARD_RETENTION_DAYS | 7, range 1–30 | Logical SQLite retention |
| PHISHGUARD_RATE_LIMIT | 60, range 1–10000 | Global requests/minute/process |
| PHISHGUARD_MAX_REQUEST_BYTES | 65536, max 8000000 | Bounded HTTP body buffering |
| PHISHGUARD_VISION_MODEL | unset | Trusted local CNN weights; enables image route |
| PHISHGUARD_API_URL | http://127.0.0.1:8000 | Server-side Streamlit API address |
| PHISHGUARD_KAFKA_BOOTSTRAP | localhost:9092 | Python Kafka broker bootstrap |
| PHISHGUARD_KAFKA_PROTOCOL | PLAINTEXT | Local demo; SSL/SASL_SSL also supported |
| PHISHGUARD_KAFKA_USER | Required for SASL_SSL | Broker principal |
| PHISHGUARD_KAFKA_PASSWORD | Required for SASL_SSL | Broker secret |
| PHISHGUARD_KAFKA_MECHANISM | SCRAM-SHA-512 | SASL mechanism |
| PHISHGUARD_KAFKA_CA | unset | Optional broker CA certificate path |
| PHISHGUARD_TEST_KAFKA | false | Explicit real-broker integration test opt-in |
| PHISHGUARD_SPARK_LOCAL_IP | unset | Optional Spark driver host override |
| PHISHGUARD_PYTHON | python3.11 | Python interpreter used by setup_mac.sh |

Boolean settings accept only `true` or `false`, case-insensitively. Invalid values fail rather
than enabling a feature accidentally. API keys starting with the example's `replace-` prefix
are rejected. This prevents accidentally running with the distributed example secret.

The extension endpoint is intentionally fixed to `127.0.0.1:8000`; changing the Streamlit API
address does not change extension routing. To support a different browser endpoint, review
and update both `manifest.json` host permissions and `background.js` API constant, then reload
the unpacked extension. Never add `<all_urls>` to solve a local API connection issue.

For Spark, `JAVA_HOME`, `SPARK_LOCAL_IP`, `PYSPARK_PYTHON` and `PYSPARK_SUBMIT_ARGS` use Apache
Spark's native configuration. Pin matching Spark/Scala/Kafka connector versions. Keep Maven/Ivy
cache and checkpoint permissions appropriate for the worker account.


Additional supported settings:

| Variable | Default / behavior |
| --- | --- |
| PHISHGUARD_REGISTRY | Optional registry root; active verified model resolved at startup |
| PHISHGUARD_BODY_TIMEOUT_SECONDS | 10; allowed 0.05–120 seconds |
| PHISHGUARD_ALLOWED_HOSTS | 127.0.0.1,localhost,::1; comma-separated explicit hostnames |
| PHISHGUARD_MAX_RETAINED_EVENTS | 10000; bounded to 1–1000000 |
| PHISHGUARD_EVALUATION_REPORT | Optional explicit minimized model report for dashboard |
| PHISHGUARD_DATA_QUALITY_REPORT | Optional explicit aggregate quality report for dashboard |
| PHISHGUARD_PIPELINE_REPORT | Optional recorded batch report, not a live monitor |
| PHISHGUARD_SPARK_DRIVER_MEMORY | 2g; local/cluster driver memory override |
| PHISHGUARD_SPARK_IVY | Optional explicit Maven/Ivy cache directory |

Setting PHISHGUARD_VISION_MODEL raises the default request body cap to 8 MB unless
PHISHGUARD_MAX_REQUEST_BYTES is explicitly set. The decoded image remains capped at 5 MB.
A configured image model is not permission to capture automatically; the browser still requires
its separate opt-in and fresh consent for every visible-tab submission.
