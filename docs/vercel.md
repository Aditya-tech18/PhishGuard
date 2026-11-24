# Vercel deployment — 2.2.0

This dedicated project serves the real trained URL detector and its web interface. It is a stateless Python FastAPI app, with lean NumPy-based portable inference. Spark/Kafka workers, Streamlit and Torch screenshot inference stay in the local/full project; they are not silently deployed as Vercel background workers. The cloud app reports image inference disabled.

## Deploy the prepared folder

1. Extract `PhishGuard-2.2.0-vercel.zip` to a new folder. Use that folder as the Vercel project root. Do not upload the full training repository or Desktop dataset.
2. In Vercel create/import the project with the FastAPI framework preset, Python 3.12, no custom build command and no static output-directory override.
3. Generate a random key locally, for example `python -c 'import secrets; print(secrets.token_urlsafe(32))'`. Add it as the sensitive `PHISHGUARD_API_KEY` environment variable in your Vercel project for each intended environment. Never commit it or paste it into this chat.
4. Vercel's `VERCEL_URL` and `VERCEL_PROJECT_PRODUCTION_URL` provide exact trusted deployment hosts. If you attach a custom domain, also set `PHISHGUARD_ALLOWED_HOSTS` to its hostname only, without scheme/path. No wildcard host trust is used.
5. Deploy. With CLI: from this prepared folder run `vercel login`, `vercel link`, add the key using `vercel env add PHISHGUARD_API_KEY production`, then `vercel deploy --prod`. No account credentials are bundled.
6. Visit the deployment. `/health` must return 200 and `vision_enabled:false`. Paste your private key into the page's access section, enter a public URL, give consent and scan. The key lives in page memory only. A refresh forgets it.
7. Confirm missing/wrong key produces 401, invalid URL 422, and `/api/v1/predictions` reports storage disabled. Model card should match `3a4516d9641014ee`. Run a preview acceptance check before exposing a production URL.

Actual remote deployment is not performed in this delivery; the user chose a ZIP/deploy-ready build. Local ASGI, HTTP/browser and bundle checks are recorded in the release report. Vercel build/runtime verification remains a real post-login acceptance step, not a claimed pass.

## Generate this build from the full repository

```sh
python scripts/prepare_vercel.py --model models/trained/url-model.json --evaluation reports/evaluation.json --output ../PhishGuard-vercel
```

The exporter uses an explicit module/file allowlist and includes only the selected numeric URL model and minimized public model card. No raw data, CNN weights, training dependencies, runtime keys, database or history is copied.

## Connect the Chrome extension

The default extension continues to target the tested loopback backend. For your final cloud URL, create a separate extension with a narrow HTTPS host permission:

```sh
python scripts/configure_extension.py --origin https://YOUR-PROJECT.vercel.app --output ../PhishGuard-cloud-extension
```

Load that new folder using Chrome Developer mode → Load unpacked. Set the same private server key in its popup. Manual ON/OFF/consent rules remain. Screenshot attempts are blocked before capture because this cloud profile has no screenshot model. Do not embed the server key in extension source or public frontend assets.

## Operational and privacy boundaries

A serverless instance has ephemeral process state. The built-in rate limiter is per warm instance, not a distributed quota. Configure Vercel Firewall/rate limiting in your account for internet-facing use; do not claim this code enforces a global limit. Request/instance metrics are local and reset. This application has no persistent SQLite, retained URL history, training jobs or worker loop in this profile. Hosting providers may retain request metadata under their own settings. The app never fetches submitted URLs and never places URL inputs in route/query strings or access-log fields.

The private API key is an owner-operated access control, not a multi-user identity system. Do not publish a shared owner key or promise public abuse protection from it. Public multi-user access requires an identity and quota service designed for that deployment. URL test metrics describe a historical dataset, not guaranteed accuracy today. The supplied corpus underrepresents benign login/article paths; the UI/API display review warnings for those inconclusive shapes instead of presenting high model scores as verified phishing.

Official runtime references: [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi), [Python runtime](https://vercel.com/docs/functions/runtimes/python), [project configuration](https://vercel.com/docs/project-configuration/vercel-json). Platform limits and account features can change; check your project's build output and plan.

## Selected model input policy

The 2.2 release uses origin-only Gradient Boosting. It ignores the path/query after validating the full URL. This removes the severe root-versus-path shortcut found in the original corpus (zero legitimate training paths). Held-out precision is 91.24%, recall 82.20%, F1 86.49%, FPR 3.37% on 8,125 origin examples. These are different inputs/splits from the old full-URL 98% result and must not be compared as the same benchmark. Login-like hosts and ordinary domains can still be overflagged. Review notices are intentionally conservative and are not domain allowlists or guarantees.
