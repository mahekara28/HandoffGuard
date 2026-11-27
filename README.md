# HandoffGuard

HandoffGuard checks whether instructions changed between two agents. A reviewer can compare the quoted evidence, approve the handoff, reject it, or ask for clarification. The receiving agent can fetch only an approved, current revision through its release endpoint.

## Run locally

Use Python 3.11 or newer. In PowerShell, open this folder and run:

~~~powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py --gemini
~~~

The launcher prompts for your API key (hidden) and the model ID enabled in AI Studio. It keeps them in the server process. Open [the review desk](http://localhost:8502). Paste the source and outgoing instruction, or open **Examples and file uploads** for a sample or a UTF-8 text file. Each input accepts up to 14,000 characters.

## Try the release check

Click **Test release flow offline**. It approves a handoff, introduces a conflicting revision, and checks that the old approval stops working. It then corrects the instruction and verifies the release. The check uses a temporary database and runs without a Gemini key.

For your own reviews, use one **task reference** per task. Select **Edit as new version** when the instruction changes. The previous version becomes superseded, even while the new one is being checked. Reviews saved before version tracking remain available as history and need a fresh review for release.

## Connect Gemini

For unattended startup, set the model ID and key in the server environment:

~~~powershell
$env:GEMINI_MODEL = Read-Host "Model ID"
$env:GEMINI_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'API key' -AsSecureString)).Password
~~~

Every new semantic review uses Gemini, including identical excerpts. Completed reviews are reused on retries. When both an API key and Vertex project are configured, the key selects the Gemini Developer API. The report names the provider and model. HandoffGuard verifies those quotes and scores the most serious finding from 0 (aligned) to 4 (blocked). Recognized credential patterns are blocked locally. Human approval is the default. Set HANDOFF_AUTO_RELEASE=1 to release aligned findings automatically.

## Test

~~~powershell
.\.venv\Scripts\python.exe -m unittest -v test_workflow
~~~

GitHub Actions runs the offline suite on pushes and pull requests. To evaluate the configured Gemini model on six synthetic cases, set HANDOFF_LIVE_TEST=1 and run the same command with test_gemini_live. That suite makes live API calls.

## Connect an agent

| Action | Endpoint |
| --- | --- |
| Submit reference, source and handoff | POST /api/reviews |
| Record a reviewer decision | POST /api/reviews/{id}/decision |
| Fetch an assigned release with a Firebase receiver token | GET /api/receiver/{id}/release |

When editing through the API, send the current packet ID in **revises**. A stale edit returns HTTP 409. Duplicate submissions reuse their result.

Use **relay_demo.py** with Context Relay installed, or **adk_demo.py --change** with requirements-adk.txt installed in a separate environment. Both demos use the trusted local desk by default. For a scoped receiver, assign its Firebase UID on submission with **receiver_uid**. Give that identity no workspace member or reviewer role. The demo clients read HANDOFF_ID_TOKEN for submission and HANDOFF_RECEIVER_UID and HANDOFF_RECEIVER_TOKEN for receipt.

<details>
<summary>Cloud configuration</summary>

The Dockerfile runs the same server on Cloud Run. For private IAM deployment, supply GEMINI_MODEL, GEMINI_API_KEY and HANDOFF_REVIEW_TOKEN. Set GOOGLE_CLOUD_PROJECT for Firestore. Local reviews use SQLite.

- **Vertex AI:** Set VERTEX_PROJECT and use application default credentials with model access.
- **Evidence storage:** Set HANDOFF_EVIDENCE_BUCKET to a private bucket writable by the service account.
- **Firebase:** Set HANDOFF_FIREBASE_PROJECT and HANDOFF_FIREBASE_WEB_KEY. Allowlist producer and reviewer UIDs with HANDOFF_FIREBASE_MEMBERS and HANDOFF_FIREBASE_REVIEWERS. For Hosting, match the Cloud Run region in firebase.json and set HANDOFF_PUBLIC_ORIGIN to the Hosting origin. Verify anonymous API requests receive HTTP 401 before allowing public invocation.
- **BigQuery:** Install requirements-analytics.txt and run python risk_export.py PROJECT.DATASET to export aggregate counts.

</details>
