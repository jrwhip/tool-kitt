"""KITT golden-REQ fixture app.

A deterministic, minimal FastAPI application. It exists to give the KITT
crew skill (scout, coder, tester, auditor) a small, fast, repeatable target
to run a single requirement against. Keep it minimal on purpose.
"""

from fastapi import FastAPI

app = FastAPI(
    title="KITT Golden Fixture",
    description="Deterministic fixture app for KITT crew-skill evaluation.",
    version="0.1.0",
)


@app.get("/health")
def get_health() -> dict[str, str]:
    """Liveness check. Always returns 200 with a fixed body."""
    return {"status": "ok"}
