"""HTTP-level tests for SecurityHeadersMiddleware's CSP exemption on the docs UI."""
import pytest


@pytest.mark.asyncio
async def test_csp_is_strict_on_a_real_api_route(client):
    """A normal JSON API route keeps the strict, no-resource-loading CSP."""
    resp = await client.get("/health")
    assert resp.headers["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'"


@pytest.mark.asyncio
async def test_csp_is_exempted_on_the_docs_ui(client):
    """/docs's own CDN-loaded JS would silently break under the strict CSP.

    Exempted from this one header only — every other security header still
    applies, a narrow exemption, not a blanket one.
    """
    resp = await client.get("/docs")
    assert "Content-Security-Policy" not in resp.headers
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
