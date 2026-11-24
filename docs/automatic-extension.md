# Automatic browser checks — 2.5.0

The extension checks website domains automatically after explicit ON, a local session API
key and Chrome website permission. Existing supported tabs, new tabs and URL navigation
changes are scheduled with a short debounce. A one-minute Chrome alarm rechecks active
normal-window tabs and recovers after temporary server unavailability. Alarms are browser
scheduled, not an exact one-second timer; sleeping/background browsers can delay them.

## Start

Run the complete project from a fresh extracted folder with setup_mac.sh, activate the
managed environment, then make launch. Open the session key file path printed by the
launcher locally; do not publish it. Load this release's extension folder through
chrome://extensions → Developer mode → Load unpacked. Disable/remove older unpacked
versions. Save the session key in Connect your local server, then turn automatic checks
ON and approve the requested website access. The key stays in Chrome session storage,
not synced/persistent key storage. A new browser session requires saving a new key.

The extension-only ZIP needs a compatible running PhishGuard API and URL model; it does
not contain or launch the backend. The complete ZIP includes the backend and trained weights.

## What users see

A phishing verdict produces a dismissible on-page card:
**Yeh website scam ho sakti hai**
Password, OTP ya payment details dene se pehle website verify karein.

The reasons button shows only returned model features translated into plain-language
signals. If no explanation is returned, the UI says that detailed reasons are unavailable.
This is an estimate, not confirmed fraud. Low-risk results are quiet; no success popup
interrupts browsing. A toolbar ! marks suspicion, … means checking, and ? means unavailable.
Optional browser notifications are separately enabled; native OS notification settings can
suppress them. Repeated warnings for a tab/domain are suppressed for five minutes.

OFF cancels queued work and aborts active requests, clears badges, and removes injected
warnings. Late responses are checked against tab URL and mode generation. Navigating away
invalidates an old result. If a worker restarts, cleanup also queries current tabs rather
than relying only on the old in-memory list. Pages are not blocked or closed.

## Privacy and scope

Automatic and manual URL checks send origin only: scheme, hostname and port. No path,
query, fragment, screenshot, page text, cookies, form values or browsing history is uploaded.
This is domain risk, not full page-content analysis. Phishing hosted under a legitimate
origin may be missed. The existing model's false positives/negatives still apply.

Automatic warnings use the unchanged origin-only URL model. The CNN's historical 88.16%
precision/88.36% recall numbers are an adaptive screenshot benchmark audit, not accuracy
of this live automatic mode. No model was retrained in 2.5.

Screenshot checks are an explicit, separate per-capture action. They do not run automatically.
The selected visible tab and consent are checked again before capture/upload. DOM warnings
use isolated-world execution and textContent; inserted warning text is not executable HTML.
Broad website host access is requested only at ON, not required at install. No automatic
access to incognito, internal Chrome or other unsupported non-HTTP(S) pages is attempted.
Chrome Web Store and similarly restricted pages may allow a toolbar alert but reject
warning injection. Desktop notifications are optional, not a guaranteed delivery channel.

Three requests may run concurrently. Very large bursts can hit API rate limits; affected
checks show unavailable rather than a false low-risk result. Active-tab alarms retry.
The API must remain running; this is not an independent offline/browser-only detector.
No dashboard master switch, dashboard event stream or new three-page frontend is included
in this feature release. The control is the real extension toolbar popup.

## Reproduce checks

```sh
node --test tests/test_extension_auto.cjs
npm ci --prefix tests/browser
node tests/browser/node_modules/playwright/cli.js install chromium
node tests/browser_auto.cjs
# Or PHISHGUARD_TEST_BROWSER=true pytest -m browser -v
```

The real Chromium suite uses an isolated temporary profile, synthetic .test pages, a
local deterministic API and pregranted website host permissions in a test-only copy.
It verifies actual popup ON, existing/new tabs, warning DOM, dismissal, navigation,
OFF cancellation, late-response rejection and data minimization. Native optional-site
permission dialogs and visual OS notification delivery were not automated. The shipping
manifest retains optional website and notification permissions. Live phishing websites
and the user's personal Chrome profile are not used.

Chrome API references: https://developer.chrome.com/docs/extensions/reference/api/permissions
https://developer.chrome.com/docs/extensions/reference/api/scripting
https://developer.chrome.com/docs/extensions/reference/api/tabs
