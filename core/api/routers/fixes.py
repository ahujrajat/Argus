from __future__ import annotations
import subprocess
import tempfile
import os
from datetime import datetime, timezone
from uuid import uuid4, UUID
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.api.deps import get_db
from core.db.tables import (
    FixRow,
    FindingRow,
    ScanRow,
    TargetAuthorizationRow,
    AuditLogEntryRow,
)
from core.vcs.factory import get_vcs_provider
from core.vcs.protocol import VCSError, VCSNotSupported

router = APIRouter(tags=["fixes"])


class RejectBody(BaseModel):
    reason: str


class ApplyFixRequest(BaseModel):
    create_pr: bool = False
    vcs_token: Optional[str] = None
    pr_base_branch: str = "main"
    pr_title: Optional[str] = None

    @model_validator(mode="after")
    def vcs_token_required_when_create_pr(self) -> "ApplyFixRequest":
        if self.create_pr and not self.vcs_token:
            raise ValueError("vcs_token is required when create_pr=True")
        return self


def _write_audit(
    db: AsyncSession,
    actor: str,
    action: str,
    target: str,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
) -> AuditLogEntryRow:
    entry = AuditLogEntryRow(
        id=str(uuid4()),
        actor=actor,
        action=action,
        target=target,
        before=before,
        after=after,
    )
    db.add(entry)
    return entry


@router.get("/scans/{scan_id}/fixes")
async def list_scan_fixes(
    scan_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(FixRow)
        .join(FindingRow, FixRow.finding_id == FindingRow.id)
        .where(FindingRow.scan_id == str(scan_id))
    )
    result = await db.execute(q)
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "finding_id": r.finding_id,
            "diff": r.diff,
            "test": r.test,
            "explanation": r.explanation,
            "validation_result": r.validation_result,
            "status": r.status,
            "reviewer": r.reviewer,
            "audit_ref": r.audit_ref,
        }
        for r in rows
    ]


@router.get("/fixes/{fix_id}")
async def get_fix(fix_id: UUID, db: AsyncSession = Depends(get_db)):
    q = select(FixRow).where(FixRow.id == str(fix_id))
    result = await db.execute(q)
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Fix not found")
    return {
        "id": row.id,
        "finding_id": row.finding_id,
        "diff": row.diff,
        "test": row.test,
        "explanation": row.explanation,
        "validation_result": row.validation_result,
        "status": row.status,
        "reviewer": row.reviewer,
        "audit_ref": row.audit_ref,
    }


@router.post("/fixes/{fix_id}/apply")
async def apply_fix(
    fix_id: UUID,
    body: ApplyFixRequest = ApplyFixRequest(),
    db: AsyncSession = Depends(get_db),
):
    # Load fix
    result = await db.execute(select(FixRow).where(FixRow.id == str(fix_id)))
    fix_row = result.scalar_one_or_none()
    if not fix_row:
        raise HTTPException(status_code=404, detail="Fix not found")

    # Load finding (needed for PR path; null-checked here for both paths)
    result = await db.execute(
        select(FindingRow).where(FindingRow.id == fix_row.finding_id)
    )
    finding_row = result.scalar_one_or_none()
    if not finding_row:
        raise HTTPException(status_code=404, detail="Finding not found for fix")

    # ── Local apply ───────────────────────────────────────────────────────────
    if not body.create_pr:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".patch", delete=False
        ) as f:
            f.write(fix_row.diff)
            patch_path = f.name
        try:
            proc = subprocess.run(
                ["patch", "-p1", "--input", patch_path],
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                raise HTTPException(
                    status_code=422,
                    detail=f"patch failed: {proc.stderr}",
                )
        finally:
            os.unlink(patch_path)

        fix_row.status = "applied"
        _write_audit(
            db,
            actor="api",
            action="fix_applied_local",
            target=str(fix_id),
            before={"status": "proposed"},
            after={"status": "applied"},
        )
        await db.flush()
        return {"fix_id": str(fix_id), "status": "applied"}

    # ── PR creation path ──────────────────────────────────────────────────────
    result = await db.execute(
        select(ScanRow).where(ScanRow.id == finding_row.scan_id)
    )
    scan_row = result.scalar_one_or_none()
    if not scan_row:
        raise HTTPException(status_code=404, detail="Scan not found for finding")

    target_ref: str = scan_row.target_ref

    # Require a valid TargetAuthorization
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(TargetAuthorizationRow).where(
            TargetAuthorizationRow.target == target_ref,
            TargetAuthorizationRow.owner_confirmed == True,  # noqa: E712
            (TargetAuthorizationRow.expires_at == None)  # noqa: E711
            | (TargetAuthorizationRow.expires_at > now),
        )
    )
    auth_row = result.scalar_one_or_none()
    if not auth_row:
        raise HTTPException(
            status_code=403,
            detail=(
                f"No active TargetAuthorization found for '{target_ref}'. "
                "Create one via POST /api/v1/authorizations before applying VCS fixes."
            ),
        )

    # Derive repo identifier from target_ref: github.com/org/repo@main → "org/repo"
    after_host = target_ref.split("/", 1)[1]
    repo = after_host.split("@")[0]

    branch_name = f"argus/fix-{str(fix_id)[:8]}"
    base_branch = body.pr_base_branch
    file_path: str = finding_row.location["file"]
    rule_id: str = finding_row.rule_id

    pr_title = body.pr_title or f"fix: {rule_id} in {file_path}"
    pr_body = (
        f"Automated fix generated by Argus.\n\n"
        f"**Rule:** {rule_id}  \n"
        f"**File:** {file_path}  \n\n"
        f"```diff\n{fix_row.diff}\n```"
    )

    provider = get_vcs_provider(target_ref, token=body.vcs_token)

    # 1. Create branch + audit
    await provider.create_branch(repo, branch_name, base_branch)
    _write_audit(
        db,
        actor="api",
        action="vcs_branch_created",
        target=f"{repo}:{branch_name}",
    )

    # 2. Commit patched file + audit
    current_content = await provider.get_file_content(repo, file_path, ref=base_branch)
    patched_content = _apply_diff_in_memory(current_content, fix_row.diff)
    await provider.commit_file(repo, branch_name, file_path, patched_content, pr_title)
    _write_audit(
        db,
        actor="api",
        action="vcs_file_committed",
        target=f"{repo}:{branch_name}:{file_path}",
    )

    # 3. Open PR + audit
    pr_url = await provider.create_pr(repo, branch_name, base_branch, pr_title, pr_body)
    fix_row.status = "pr_opened"
    fix_row.validation_result = {
        **(fix_row.validation_result or {}),
        "pr_url": pr_url,
    }
    _write_audit(
        db,
        actor="api",
        action="fix_pr_created",
        target=pr_url,
        after={"pr_url": pr_url, "branch": branch_name},
    )
    await db.flush()

    return {"fix_id": str(fix_id), "status": "pr_opened", "pr_url": pr_url}


def _apply_diff_in_memory(original: str, diff: str) -> str:
    """Apply a unified diff to in-memory content via subprocess patch.

    Writes to a temp dir, rewrites the diff headers to use the temp path,
    runs patch, returns patched content. Raises HTTPException(422) if patch fails.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_path = os.path.join(tmpdir, "original")
        patch_path = os.path.join(tmpdir, "changes.patch")

        with open(orig_path, "w") as f:
            f.write(original)

        lines = []
        for line in diff.splitlines(keepends=True):
            if line.startswith("--- a/"):
                lines.append(f"--- {orig_path}\n")
            elif line.startswith("+++ b/"):
                lines.append(f"+++ {orig_path}\n")
            else:
                lines.append(line)
        with open(patch_path, "w") as f:
            f.writelines(lines)

        proc = subprocess.run(
            ["patch", "--no-backup-if-mismatch", orig_path, patch_path],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise HTTPException(
                status_code=422,
                detail=f"Failed to apply diff in memory: {proc.stderr}",
            )

        with open(orig_path) as f:
            return f.read()


@router.post("/fixes/{fix_id}/reject")
async def reject_fix(
    fix_id: UUID,
    body: RejectBody,
    db: AsyncSession = Depends(get_db),
):
    q = select(FixRow).where(FixRow.id == str(fix_id))
    result = await db.execute(q)
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Fix not found")

    # Write audit log BEFORE mutating status
    audit = AuditLogEntryRow(
        id=str(uuid4()),
        actor="api",
        action="fix_reject",
        target=str(fix_id),
        before={"status": row.status},
        after={"status": "rejected", "reason": body.reason},
    )
    db.add(audit)

    row.status = "rejected"
    await db.commit()
    await db.refresh(row)
    return {"status": row.status, "fix_id": str(fix_id)}
