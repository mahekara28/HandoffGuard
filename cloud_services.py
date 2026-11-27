"""Optional cloud integrations. Local reviews require no cloud credentials."""
import json
import os

from google.api_core.exceptions import GoogleAPIError, PreconditionFailed
from google.auth.exceptions import GoogleAuthError


def archive_evidence(bucket_name, packet_id, source, handoff):
    from google.cloud import storage
    blob = storage.Client().bucket(bucket_name).blob(f"handoffs/{packet_id}/evidence.json")
    try:
        blob.upload_from_string(json.dumps({"source": source, "handoff": handoff}),
                                content_type="application/json", if_generation_match=0, timeout=20)
    except PreconditionFailed:
        # The same packet was already archived by an earlier attempt.
        pass


def firebase_user(token, project):
    from google.auth.transport.requests import Request
    from google.oauth2.id_token import verify_firebase_token
    try:
        claims = verify_firebase_token(token, Request(), audience=project)
    except (ValueError, GoogleAuthError):
        return None
    if claims.get("iss") != "https://securetoken.google.com/" + project or not claims.get("sub"):
        return None
    return claims

