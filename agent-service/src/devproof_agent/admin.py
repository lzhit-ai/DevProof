"""Explicit ownership activation using separate deployment management credentials."""

import asyncio
import os
import sys

import httpx

async def activate(aggregate: str) -> None:
    names = ["BUSINESS_API_URL", "BUSINESS_OWNERSHIP_TOKEN"]
    if any(not os.environ.get(name, "").strip() for name in names):
        raise SystemExit("Business URL and deployment ownership credentials are required.")
    async with httpx.AsyncClient() as client:
        response = await client.post(os.environ["BUSINESS_API_URL"].rstrip("/")+f"/internal/v1/business-ownership/{aggregate}/activate",
            headers={"Authorization": "Bearer "+os.environ["BUSINESS_OWNERSHIP_TOKEN"]}, json={}, timeout=30)
        if not response.is_success:
            raise SystemExit(f"Ownership activation failed (HTTP {response.status_code}).")
        result = response.json()
    groups = {"verification": ["verification-inputs", "verification"], "management": ["projects", "task-management"]}
    expected = {"aggregates": groups[aggregate], "owner": "JAVA"} if aggregate in groups else {"aggregate": aggregate, "owner": "JAVA"}
    if result != expected:
        raise SystemExit("The business service did not confirm requested ownership.")
    print(f"Business aggregate ownership is JAVA: {aggregate}.")


if __name__ == "__main__":
    commands = {"activate-reports": "reports", "activate-verification": "verification", "activate-identity": "identity", "activate-management": "management", "activate-github-sources": "github-sources", "activate-knowledge-bases": "knowledge-bases", "activate-knowledge-sources": "knowledge-sources", "activate-orchestration": "orchestration", "activate-evidence-materials": "evidence-materials", "activate-git-inputs": "git-inputs", "activate-delivery-associations": "delivery-associations", "activate-delivery-claims": "delivery-claims", "activate-evidence-questions": "evidence-questions", "activate-project-status": "project-status", "activate-security-baselines": "security-baselines", "activate-peripheral-profiles": "peripheral-profiles"}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        raise SystemExit("Usage: python -m devproof_agent.admin " + "|".join(commands))
    asyncio.run(activate(commands[sys.argv[1]]))
