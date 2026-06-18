# core/api/routers/webhooks.py
from __future__ import annotations
import hashlib
import hmac
import os
import structlog
from uuid import uuid4
from fastapi import APIRouter, Request, HTTPException, Header, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.api.deps import get_db
from core.db.tables import PipelineConfigRow, ScanRow

log = structlog.get_logger()

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_GITHUB_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
_GITLAB_SECRET = os.environ.get("GITLAB_WEBHOOK_SECRET", "")

# Default pipeline to trigger on push events
_PUSH_PIPELINE = os.environ.get("WEBHOOK_PIPELINE", "pr-check")


def _verify_github_signature(body: bytes, sig_header: str) -> bool:
    if not _GITHUB_SECRET:
        return True  # secret not configured — accept but log
    expected = "sha256=" + hmac.new(
        _GITHUB_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, sig_header)


def _verify_gitlab_token(token: str) -> bool:
    if not _GITLAB_SECRET:
        return True
    return hmac.compare_digest(_GITLAB_SECRET, token)


async def _resolve_pipeline(db: AsyncSession) -> str | None:
    result = await db.execute(
        select(PipelineConfigRow).where(PipelineConfigRow.name == _PUSH_PIPELINE)
    )
    row = result.scalar_one_or_none()
    return str(row.id) if row else None


async def _enqueue_scan(db: AsyncSession, target_ref: str, pipeline_id: str, mode: str = "batch") -> str:
    scan_id = str(uuid4())
    db.add(ScanRow(
        id=scan_id,
        target_ref=target_ref,
        pipeline_config_id=pipeline_id,
        mode=mode,
        approach="penetration_testing",
        status="pending",
    ))
    await db.flush()
    return scan_id


@router.post("/github")
async def github_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_hub_signature_256: str = Header(default=""),
    x_github_event: str = Header(default=""),
):
    body = await request.body()

    if _GITHUB_SECRET and not _verify_github_signature(body, x_hub_signature_256):
        log.warning("github_webhook_invalid_signature")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    if x_github_event not in ("push", "pull_request"):
        return {"status": "ignored", "event": x_github_event}

    payload = await request.json()

    if x_github_event == "push":
        repo_url = payload.get("repository", {}).get("clone_url", "")
        ref = payload.get("ref", "")
        target_ref = f"{repo_url}#{ref}"
    else:
        pr = payload.get("pull_request", {})
        repo_url = pr.get("head", {}).get("repo", {}).get("clone_url", "")
        branch = pr.get("head", {}).get("ref", "")
        target_ref = f"{repo_url}#{branch}"

    if not repo_url:
        return {"status": "skipped", "reason": "no_repo_url"}

    pipeline_id = await _resolve_pipeline(db)
    if not pipeline_id:
        log.warning("github_webhook_no_pipeline", pipeline=_PUSH_PIPELINE)
        raise HTTPException(status_code=503, detail=f"Pipeline '{_PUSH_PIPELINE}' not found")

    scan_id = await _enqueue_scan(db, target_ref, pipeline_id)

    log.info("github_webhook_scan_enqueued", scan_id=scan_id, target=target_ref, webhook_event=x_github_event)
    return {"status": "accepted", "scan_id": scan_id}


@router.post("/gitlab")
async def gitlab_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_gitlab_token: str = Header(default=""),
    x_gitlab_event: str = Header(default=""),
):
    if _GITLAB_SECRET and not _verify_gitlab_token(x_gitlab_token):
        log.warning("gitlab_webhook_invalid_token")
        raise HTTPException(status_code=401, detail="Invalid webhook token")

    if x_gitlab_event not in ("Push Hook", "Merge Request Hook"):
        return {"status": "ignored", "event": x_gitlab_event}

    payload = await request.json()

    if x_gitlab_event == "Push Hook":
        repo_url = payload.get("repository", {}).get("git_http_url", "")
        ref = payload.get("ref", "")
        target_ref = f"{repo_url}#{ref}"
    else:
        attrs = payload.get("object_attributes", {})
        repo_url = payload.get("repository", {}).get("git_http_url", "")
        branch = attrs.get("source_branch", "")
        target_ref = f"{repo_url}#{branch}"

    if not repo_url:
        return {"status": "skipped", "reason": "no_repo_url"}

    pipeline_id = await _resolve_pipeline(db)
    if not pipeline_id:
        log.warning("gitlab_webhook_no_pipeline", pipeline=_PUSH_PIPELINE)
        raise HTTPException(status_code=503, detail=f"Pipeline '{_PUSH_PIPELINE}' not found")

    scan_id = await _enqueue_scan(db, target_ref, pipeline_id)

    log.info("gitlab_webhook_scan_enqueued", scan_id=scan_id, target=target_ref, webhook_event=x_gitlab_event)
    return {"status": "accepted", "scan_id": scan_id}
