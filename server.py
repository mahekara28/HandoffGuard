import hmac
import json
import os

from pathlib import Path
from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles

from release_check import run_check, run_gemini_demo
from review import needs_fresh_review, released, ALIAS_SOURCE, ALIAS_HANDOFF, RISK, gemini_configured, BAD, GOOD, DEFAULT, MISSING, Problem, decide, submit
from storage import Store
from cloud_services import firebase_user

STATIC = Path(__file__).with_name("static")


def public(record):
    visible = {k: v for k, v in record.items() if k != "owner"}
    if needs_fresh_review(record):
        visible["state"] = "archived"
    status = (record.get("finding") or {}).get("status")
    score, action = RISK.get(status, (None, "Retry review" if status == "unavailable" else "Wait"))
    return dict(visible, risk_score=score, recommended_action=action)


async def payload(request):
    if request.headers.get("content-type", "").split(";")[0] != "application/json":
        raise Problem(415, "Send an application/json body.")
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).netloc != request.headers.get("host") and origin != os.getenv("HANDOFF_PUBLIC_ORIGIN"):
        raise Problem(403, "Open the dashboard on this server.")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 200000:
            raise Problem(413, "This packet exceeds the intake limit.")
        body.extend(chunk)
    try:
        data = json.loads(body)
    except (ValueError, RecursionError):
        raise Problem(400, "Invalid JSON.")
    if not isinstance(data, dict):
        raise Problem(422, "Send one packet as a JSON object.")
    return data


async def home(request):
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})


async def config(request):
    return JSONResponse({"model": os.getenv("GEMINI_MODEL") or "Unconfigured",
                         "live": gemini_configured(),
                         "provider": "Vertex AI" if os.getenv("VERTEX_PROJECT") and not os.getenv("GEMINI_API_KEY") else "Gemini API",
                         "firebase": bool(os.getenv("HANDOFF_FIREBASE_PROJECT")),
                         "firebase_web_key": os.getenv("HANDOFF_FIREBASE_WEB_KEY", ""),
                         "auto": os.getenv("HANDOFF_AUTO_RELEASE") == "1",
                         "protected": not os.getenv("HANDOFF_FIREBASE_PROJECT") and bool(os.getenv("HANDOFF_REVIEW_TOKEN") or os.getenv("K_SERVICE")),
                         "source": DEFAULT, "alias_source": ALIAS_SOURCE,
                         "examples": {"Deprecated API alias": ALIAS_HANDOFF, "Changed instruction": BAD, "Corrected wording": GOOD,
                                      "Missing detail": MISSING, "Exact match": DEFAULT,
                                      "Credential check": "api_key=DEMO_ONLY_VALUE"}})


async def reviews(request):
    if request.method == "POST":
        data = await payload(request)
        record = await run_in_threadpool(submit, data)
        return JSONResponse(public(record), status_code=503 if record["state"] == "failed" else 200)
    records = await run_in_threadpool(lambda: Store().recent())
    return JSONResponse([{k: public(r).get(k) for k in ("id", "reference", "revision", "state", "updated")} for r in records])


async def packet(request):
    key = request.path_params["key"]
    if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
        raise Problem(404, "Unknown packet.")
    if request.method == "POST":
        data = await payload(request)
        token = os.getenv("HANDOFF_REVIEW_TOKEN")
        if not os.getenv("HANDOFF_FIREBASE_PROJECT") and (token or os.getenv("K_SERVICE")) and not (token and hmac.compare_digest(
                request.headers.get("x-review-token", "").encode(), token.encode())):
            raise Problem(403, "Enter the reviewer token to record a decision.")
        record = await run_in_threadpool(decide, key, data.get("decision"), getattr(request.state, "reviewer", "Reviewer"))
    else:
        record = await run_in_threadpool(lambda: Store().get(key))
    if record is None:
        raise Problem(404, "Unknown packet.")
    if request.url.path.endswith("/simulate"):
        released(record)
        instruction = record["handoff"]
        if instruction not in (BAD, GOOD, DEFAULT):
            raise Problem(422, "Select a payment demo to run the mock ledger.")
        keys = [str(i) if instruction == BAD else "payment-1" for i in range(2)]
        return JSONResponse({"attempts": 2, "charges": len(set(keys))})
    if request.url.path.endswith("/release"):
        return JSONResponse(released(record))
    return JSONResponse(public(record))


async def receive(request):
    uid = getattr(request.state, "uid", None)
    if not uid:
        raise Problem(403, "This endpoint requires a Firebase receiver identity.")
    key = request.path_params["key"]
    if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
        raise Problem(404, "Unknown assignment.")
    record = await run_in_threadpool(lambda: Store().get(key))
    if not record or record.get("receiver_uid") != uid:
        raise Problem(404, "Unknown assignment.")
    return JSONResponse(released(record))


async def self_test(request):
    await payload(request)
    return JSONResponse(await run_in_threadpool(run_check))

async def gemini_demo(request):
    await payload(request)
    return JSONResponse(await run_in_threadpool(run_gemini_demo))


async def problem(request, exc):
    return JSONResponse({"error": str(exc)}, status_code=exc.code)


app = Starlette(routes=[Route("/", home), Route("/api/config", config),
                        Route("/api/self-test", self_test, methods=["POST"]),
                        Route("/api/gemini-demo", gemini_demo, methods=["POST"]),
                        Route("/api/receiver/{key}/release", receive),
                        Route("/api/reviews", reviews, methods=["GET", "POST"]),
                        Route("/api/reviews/{key}/release", packet),
                        Route("/api/reviews/{key}/simulate", packet),
                        Route("/api/reviews/{key}/decision", packet, methods=["POST"]),
                        Route("/api/reviews/{key}", packet),
                        Mount("/static", app=StaticFiles(directory=STATIC))],
                exception_handlers={Problem: problem})
if not os.getenv("K_SERVICE"):
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]"])



async def privacy(request, call_next):
    project = os.getenv("HANDOFF_FIREBASE_PROJECT")
    if project and request.url.path.startswith("/api/") and request.url.path != "/api/config":
        auth = request.headers.get("authorization", "")
        claims = await run_in_threadpool(firebase_user, auth[7:], project) if auth.startswith("Bearer ") else None
        if not claims:
            return JSONResponse({"error":"Sign in to the review desk."}, status_code=401, headers={"Cache-Control":"no-store"})
        uid = claims["sub"]
        reviewers = os.getenv("HANDOFF_FIREBASE_REVIEWERS", "").split(",")
        members = os.getenv("HANDOFF_FIREBASE_MEMBERS", "").split(",")
        request.state.uid = uid
        receiver_read = request.method == "GET" and request.url.path.startswith("/api/receiver/")
        if not receiver_read and uid not in reviewers and (uid not in members or request.url.path.endswith("/decision")):
            return JSONResponse({"error":"Your account lacks permission for this action."}, status_code=403, headers={"Cache-Control":"no-store"})
        request.state.reviewer = "Reviewer " + uid
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = "default-src 'self'; connect-src 'self' https://identitytoolkit.googleapis.com; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    return response


app.add_middleware(BaseHTTPMiddleware, dispatch=privacy)
