"""统一的访问控制。

设计取舍：

* 配置了 `APP_AUTH_TOKEN` 时，所有接口都要求携带令牌；令牌可以是
  `X-API-Token` 请求头，也可以是 `Authorization: Bearer <token>`。
* 未配置 `APP_AUTH_TOKEN` 时不做拦截，但**只允许本机回环地址访问**，
  避免开发时零配置、一部署就变成"内网任何人都能听门店录音"。
* `<audio src>` 无法自定义请求头，因此录音流接口额外接受 `?token=`，
  这是唯一允许令牌出现在 URL 的位置。

之所以不用 HTTP Basic / Session，是因为当前没有用户体系，先补一层共享令牌
把"零鉴权"这个最大的窟窿堵住；接入正式登录时只需替换 `require_auth`。
"""

from __future__ import annotations

import hmac
import logging
import os
from typing import Annotated

from fastapi import HTTPException, Query, Request, status

from app.security import is_loopback_host

logger = logging.getLogger(__name__)

AUTH_TOKEN_ENV = "APP_AUTH_TOKEN"
TOKEN_HEADER = "X-API-Token"
_UNAUTHORIZED_HEADERS = {"WWW-Authenticate": "Token"}


def configured_token() -> str | None:
    value = os.getenv(AUTH_TOKEN_ENV, "").strip()
    return value or None


def _token_matches(candidate: str | None) -> bool:
    expected = configured_token()
    if expected is None or not candidate:
        return False
    return hmac.compare_digest(candidate, expected)


def _extract_token(request: Request) -> str | None:
    header = request.headers.get(TOKEN_HEADER)
    if header and header.strip():
        return header.strip()
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


def _client_host(request: Request) -> str | None:
    client = request.client
    return client.host if client else None


def require_auth(request: Request) -> None:
    """路由级依赖：所有业务接口都必须通过这里。"""
    if configured_token() is None:
        if is_loopback_host(_client_host(request)):
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"服务未配置 {AUTH_TOKEN_ENV}，当前仅允许本机访问。"
                f"如需对外提供服务，请在 backend/.env 中设置 {AUTH_TOKEN_ENV}。"
            ),
        )
    if _token_matches(_extract_token(request)):
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="缺少或无效的访问令牌",
        headers=_UNAUTHORIZED_HEADERS,
    )


def require_media_auth(
    request: Request,
    token: Annotated[str | None, Query(description="录音流专用令牌")] = None,
) -> None:
    """录音流依赖：允许把令牌放在查询串里，因为 audio 标签无法设置请求头。"""
    if _token_matches(token):
        return
    require_auth(request)


def warn_if_unprotected() -> None:
    """启动时把当前的防护级别说清楚，避免"以为有鉴权"。"""
    if configured_token() is None:
        logger.warning(
            "%s 未配置：接口仅允许本机回环地址访问，对外部署前必须设置该变量。",
            AUTH_TOKEN_ENV,
        )
    else:
        logger.info("%s 已启用，所有接口要求携带令牌。", AUTH_TOKEN_ENV)
