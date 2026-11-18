import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Public Profile Audit")

mcp = FastMCP("Public Profile Audit")

mcp = MCPServer("Public Profile Audit")


# Plataformas com URLs públicas de perfil.
# A verificação de HTTP não garante que um perfil realmente exista.
PLATFORMS = {
    "github": "https://github.com/{username}",
    "reddit": "https://www.reddit.com/user/{username}/",
    "instagram": "https://www.instagram.com/{username}/",
    "x": "https://x.com/{username}",
    "tiktok": "https://www.tiktok.com/@{username}",
    "youtube": "https://www.youtube.com/@{username}",
    "medium": "https://medium.com/@{username}",
    "pinterest": "https://www.pinterest.com/{username}/",
}

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]{1,50}$")

HEADERS = {
    "User-Agent": (
        "PublicProfileAudit/1.0 "
        "(authorized public-profile verification)"
    )
}


def validate_username(username: str) -> str:
    username = username.strip()

    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError(
            "Username inválido. Use somente letras, números, "
            "ponto, hífen ou underscore."
        )

    return username


async def check_profile(
    username: str,
    platform: str,
) -> dict[str, Any]:

    username = validate_username(username)
    platform = platform.lower().strip()

    if platform not in PLATFORMS:
        raise ValueError(
            f"Plataforma não suportada: {platform}"
        )

    url = PLATFORMS[platform].format(username=username)

    result = {
        "username": username,
        "platform": platform,
        "url": url,
        "status": "unknown",
        "http_status": None,
        "checked_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "error": None,
    }

    timeout = httpx.Timeout(10.0)

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            headers=HEADERS,
            follow_redirects=True,
        ) as client:

            response = await client.get(url)

            result["http_status"] = response.status_code

            if response.status_code == 200:
                result["status"] = "accessible"

            elif response.status_code == 404:
                result["status"] = "not_found"

            elif response.status_code in (401, 403):
                result["status"] = "restricted"

            elif response.status_code == 429:
                result["status"] = "rate_limited"

            else:
                result["status"] = "unknown"

    except httpx.TimeoutException:
        result["status"] = "error"
        result["error"] = "Timeout"

    except httpx.RequestError as exc:
        result["status"] = "error"
        result["error"] = str(exc)

    return result


@mcp.tool()
async def check_public_profile(
    username: str,
    platform: str,
) -> dict[str, Any]:
    """
    Verifica se uma URL de perfil público está acessível.

    Use somente para usernames próprios ou pesquisas autorizadas.
    """
    return await check_profile(username, platform)


@mcp.tool()
async def search_public_profiles(
    username: str,
    platforms: list[str] | None = None,
) -> dict[str, Any]:
    """
    Verifica URLs de perfis públicos em plataformas selecionadas.

    Não coleta dados privados nem tenta contornar controles
    de acesso das plataformas.
    """

    username = validate_username(username)

    if platforms is None:
        platforms = [
            "github",
            "reddit",
            "instagram",
            "x",
            "tiktok",
        ]

    platforms = [
        platform.lower().strip()
        for platform in platforms
    ]

    invalid = [
        platform
        for platform in platforms
        if platform not in PLATFORMS
    ]

    if invalid:
        return {
            "error": "Plataformas inválidas",
            "invalid_platforms": invalid,
            "supported_platforms": list(PLATFORMS.keys()),
        }

    # Limita a quantidade de verificações por solicitação.
    platforms = platforms[:8]

    results = await asyncio.gather(
        *[
            check_profile(username, platform)
            for platform in platforms
        ]
    )

    return {
        "username": username,
        "total_checked": len(results),
        "results": results,
    }


@mcp.tool()
async def generate_audit_report(
    username: str,
    platforms: list[str] | None = None,
) -> str:
    """
    Cria relatório JSON de presença digital pública.
    """

    data = await search_public_profiles(
        username=username,
        platforms=platforms,
    )

    report = {
        "report_type": "public_profile_audit",
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "notice": (
            "Resultados indicam acessibilidade HTTP. "
            "Não representam confirmação de identidade."
        ),
        "data": data,
    }

    return json.dumps(
        report,
        indent=2,
        ensure_ascii=False,
    )


app = mcp.app()
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
