# HandoffGuard

A release gate for agent handoffs. A producer submits the original requirement and a proposed instruction. The desk checks both, quotes the evidence, and records the release decision for that exact task and pair of excerpts. A cooperating consumer reads the approved instruction from the release endpoint.

## Demo in 90 seconds

Open the desk, select **Deprecated API alias**, and submit the two agent messages. Alternatively, upload the two UTF-8 conversations from static/samples. Each field accepts plain text, Markdown or raw JSON up to 14,000 characters. Both texts stay editable before submission. Use a new task reference for each independent demo, especially when switching from local checks to Gemini.

In the source, the researcher asks to keep a deprecated API alias. The receiving agent is told to remove it. Inspect the quoted instructions, select **Reject**, and open review history. An agent calling the release endpoint now receives HTTP 409. For a live Gemini demo, include the reason the alias exists in the source transcript and ask the reviewer to explain the compatibility impact.

The local keep/remove rule handles two opposite direct instructions when Gemini is unconfigured. The engine label identifies this case. With Gemini configured, the model extracts material decisions from the conversations and returns paired evidence for each comparison. A single invalid citation stops release. The headline finding is the most severe one; expand the other decisions to inspect them.

| Highest finding | Policy score | Recommended action |
| --- | --- | --- |
| Aligned | 0/4 | Approve |
| Ambiguous | 1/4 | Request clarification |
| Missing requirement or off-task decision | 2/4 | Request clarification |
| Contradiction | 3/4 | Reject |
| Suspicious instruction or recognized credential | 4/4 | Reject; release is blocked |
| Review unavailable | Unscored | Retry |

The score is an ordinal triage rule. Gemini supplies the semantic findings and quotations, and server policy assigns the score.

## Start the desk

Use Python 3.11 or newer. In PowerShell, from this folder:

~~~powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
~~~

Open http://localhost:8502. An exact match, a recognized credential or a recognized instruction override can be tested with no account. For Gemini comparisons, set these variables in the same terminal before starting the server:

~~~powershell
$env:GEMINI_MODEL = Read-Host "Exact model ID enabled in AI Studio"
$env:GEMINI_API_KEY = [System.Net.NetworkCredential]::new('',(Read-Host 'Gemini API key' -AsSecureString)).Password
~~~

The server reads PORT if set. The earlier Streamlit desk used port 8501. The final dashboard and JSON API share a single server. SQLite records live in reviews.sqlite next to app.py. HANDOFF_DB can override that location. Existing V1 decision events are preserved in their original table or collection. They do not grant release for new packets.

## Test in the browser

1. Select **Exact match**, then **Review handoff**. Confirm the original and outgoing evidence. Approve it, run the mock retries and look for one simulated charge.
2. Choose **New handoff**, then **Credential check**. The policy should block it before any Gemini call. The review stores a fingerprint and a generic finding. It discards the matched packet's text.
3. With Gemini configured, select **Changed instruction**. Expect a conflict about issuing a new payment key. Reject it and inspect Review history. The mock runner is available only for approved payment examples.
4. Select **Missing detail** and expect a missing retry-key requirement. Request clarification. Then submit **Corrected wording**, inspect its citations and approve. A new instruction creates a separate packet.
5. Open a second browser tab. Submit from either tab or the API and watch the queue update within a few seconds.

Use a different task reference for a separate run. Repeating an identical reference and excerpts returns the existing decision. The queue shows the latest 100 packets. Older IDs remain addressable. Failed checks can be retried by resubmitting. A producer can reclaim a checking packet after two minutes if a worker stopped mid-review.

## Automation and the release gate

The default policy requires a reviewer. Set HANDOFF_AUTO_RELEASE=1 before starting the server to release newly checked aligned packets automatically. This includes Gemini judgments and exact text matches. Conflicts, omissions and unclear findings still wait for a human. A reviewer may approve a semantic finding after inspecting it. Local credential and override blocks cannot be approved. An unavailable model or invalid quotation leaves release closed. Pattern checks recognize selected formats and fixed instruction phrases. They cannot establish that arbitrary input is safe.

| Request | Purpose |
| --- | --- |
| POST /api/reviews | Send a JSON object containing source, handoff and an optional reference. Checks run during the request. |
| GET /api/reviews | List the latest queue entries. |
| GET /api/reviews/{id} | Read the finding, workflow state and recent review events. |
| POST /api/reviews/{id}/decision | Send a decision of approved, rejected or clarification. The first terminal decision wins. |
| GET /api/reviews/{id}/release | Return the approved handoff. HTTP 409 means the consumer must wait or stop. |

Use a unique stable reference per task instance. Retry with the same reference and original excerpts if the request times out. Check the state even after HTTP 200. HTTP 503 with state failed means the packet can be resubmitted. Revisions and clarifications require a fresh submission with changed content. The API supports cooperating agents; calling the release endpoint before executing is the consumer's responsibility.

### Send one packet manually

~~~powershell
$desk = 'http://localhost:8502'
$packet = @{reference='API smoke test'; source='Keep the alias.'; handoff='Keep the alias.'} | ConvertTo-Json
$r = Invoke-RestMethod "$desk/api/reviews" -Method Post -ContentType 'application/json' -Body $packet
$r.state
# Approve the item in the browser before reading its release.
Invoke-RestMethod "$desk/api/reviews/$($r.id)/release"
~~~

### Connect Context Relay

relay_demo.py uses Context Relay's ContextGuard, allow_tool and execute_with_recovery APIs. The host supplies the original requirement. The guarded tool callback submits the instruction, then the consumer waits for a decision and reads /release before printing the approved text. The demo uses an exact match so it can run offline against localhost. In a Python environment with your Context Relay checkout installed, run:

~~~powershell
python relay_demo.py
~~~

To install Relay into the desk's virtual environment, run pip with the path to the checkout containing its pyproject.toml. Set HANDOFF_URL to point the demo at a different desk or an authenticated local Cloud Run proxy. This example adds a callback to a Relay host; other running Relay projects must register the callback explicitly.

## Automated checks

~~~powershell
.\.venv\Scripts\python.exe -m unittest -v test_workflow
~~~

Tests start an isolated HTTP server and temporary SQLite store. They cover conflicting reviewer decisions, repeat submissions, the release gate, automatic approval, policy blocks, input validation, citation rejection, retries, and changed versions. Gemini responses are fixtures in the test suite.

## Private deployment on Google Cloud

Use a billing-enabled project, the default Firestore Native database, and a dedicated runtime service account. Grant it Firestore access (roles/datastore.user) and Secret Manager access on two secrets: gemini-api-key and handoff-review-token. Set the latter to a random secret shared only with reviewers. Configure the deployer's Cloud Run source deployment and service account permissions.

~~~powershell
$project = Read-Host "Google Cloud project ID"
$region = Read-Host "Cloud Run region"
$account = Read-Host "Runtime service account email"
$model = Read-Host "Enabled Gemini model ID"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com firestore.googleapis.com secretmanager.googleapis.com --project $project
gcloud run deploy handoffguard --source . --project $project --region $region --service-account $account --no-allow-unauthenticated --set-env-vars "GOOGLE_CLOUD_PROJECT=$project,GEMINI_MODEL=$model" --set-secrets "GEMINI_API_KEY=gemini-api-key:latest,HANDOFF_REVIEW_TOKEN=handoff-review-token:latest"
gcloud run services proxy handoffguard --project $project --region $region --port 8080
~~~

Visit http://localhost:8080. Only grant Cloud Run Invoker access to trusted members and agents of this shared workspace. All invokers can read review excerpts. Cloud decisions additionally require the reviewer token. Localhost uses the same token check if HANDOFF_REVIEW_TOKEN is set. The history identifies a reviewer or policy, without individual reviewer authentication. Approved output is a data handoff, and the mock runner never makes a payment.

## Google Cloud integrations

The AI Studio configuration above uses the Gemini Developer API. To use Vertex instead, enable the Vertex AI API, set VERTEX_PROJECT to the inference project, set GEMINI_MODEL to a model available on its global endpoint, and give the runtime identity the Vertex AI User role. On a local machine use application default credentials (gcloud auth application-default login). VERTEX_PROJECT takes precedence over the API key; GOOGLE_CLOUD_PROJECT separately selects Firestore storage.

* **Cloud Storage evidence.** Set HANDOFF_EVIDENCE_BUCKET to an existing private bucket and grant the runtime identity Storage Object Creator on it. The service archives the submitted text pair at handoffs/{packet-id}/evidence.json after analysis. Policy blocks skip archival. Writes use a create-only generation condition so retries can reuse the object. Archive failures hold release. The database also keeps the approved review evidence.
* **Google ADK agents.** In a separate Python environment install requirements-adk.txt, set GEMINI_API_KEY and GEMINI_MODEL, and run python adk_demo.py --change with the desk running. The researcher drafts a handoff, the demo substitutes the remove-alias instruction, and the implementer waits for release. Reject the packet to stop it. Run without --change for a faithful handoff. Both ADK agents use Gemini and require live service access. Set HANDOFF_URL if the desk uses a different port.
* **BigQuery risk patterns.** Install requirements-analytics.txt in the desk environment and run python risk_export.py PROJECT.DATASET. Supply an existing dataset and an identity with permission to run load jobs and create tables there. Each run produces a new dated snapshot grouped by UTC day, verdict and decision state. Rows contain counts only. The app exports on command.
* **Firebase sign-in and Hosting.** The default Cloud Run setup above uses private IAM. For Firebase authentication, enable Email/Password sign-in in the Firebase project, provision users, and set HANDOFF_FIREBASE_PROJECT and HANDOFF_FIREBASE_WEB_KEY on the backend. Set HANDOFF_FIREBASE_MEMBERS and HANDOFF_FIREBASE_REVIEWERS to comma-separated Firebase user IDs (no spaces). Reviewers can read and decide; members can submit and read. The API verifies the bearer token and project issuer, checks the UID allowlist, and records reviewer UIDs. The UI signs in directly with Firebase and keeps the ID token in page memory. Reload to end the local session. Agents supply a current Firebase ID token via HANDOFF_ID_TOKEN in this mode.
* **Hosting route.** firebase.json routes the dashboard, assets and API to the handoffguard Cloud Run service in us-central1. Adjust the region to match deployment and set HANDOFF_PUBLIC_ORIGIN to the exact HTTPS Hosting origin. Configure Firebase authentication on the backend and verify an unauthenticated request to /api/reviews returns HTTP 401 before enabling public invocation for Hosting. Then use firebase deploy --only hosting --project PROJECT. The Firebase web key identifies the Firebase app and is distinct from the server-side Gemini key.

The Cloud Run image installs server dependencies. ADK and BigQuery are separate clients. Any external services require a configured project, enabled APIs and suitable account permissions.
