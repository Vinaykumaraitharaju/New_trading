from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from data.source_router import SourceRouter

log = logging.getLogger(__name__)


@dataclass
class AuthResult:
    ok: bool
    message: str
    router: SourceRouter


def build_router(totp_code: str = "") -> SourceRouter:
    return SourceRouter(
        kotak_consumer_key=os.getenv("KOTAK_CONSUMER_KEY")
        or os.getenv("KOTAK_NEO_CONSUMER_KEY"),
        kotak_access_token=os.getenv("KOTAK_ACCESS_TOKEN")
        or os.getenv("KOTAK_NEO_ACCESS_TOKEN"),
        kotak_totp_code=totp_code.strip(),
    )


def validate_session(totp_code: str = "") -> AuthResult:
    router = build_router(totp_code=totp_code)
    auth = router.validate_auth()
    if auth["ok"]:
        log.info("AUTH_SUCCESS %s", auth["message"])
    else:
        log.error("AUTH_FAILED %s", auth["message"])
    return AuthResult(ok=bool(auth["ok"]), message=str(auth["message"]), router=router)
