from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.core.security import decode_access_token

limiter = Limiter(key_func=get_remote_address)


def user_or_ip_key(request: Request) -> str:
    """Rate-limit bucket for authenticated endpoints: the (signature-verified) user id when a
    valid bearer token is present, otherwise the client IP.

    Keying scans by IP would put an entire classroom behind one campus-NAT address into a single
    bucket, so honest students would start getting 429s. Keying by user keeps the limit
    meaningful per person. No DB access here — only the JWT signature is checked; the real
    authentication still happens in the endpoint's dependencies.
    """
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        try:
            payload = decode_access_token(header[7:].strip())
            sub = payload.get("sub")
            if sub:
                return f"user:{sub}"
        except ValueError:
            pass
    return get_remote_address(request)
