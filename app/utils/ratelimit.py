"""Per-IP rolling-window rate limiting for unauthenticated endpoints.

Generalizes the brute-force throttle already used by auth.login
(app/routes/auth.py `_recent_failures`). In-process state, which is correct
for this app: it runs as a single local process, and a counter that resets on
restart is the right trade for zero dependencies.

Used on the public surfaces that accept writes or invoke the LLM without a
login — a token-holder should not be able to script hundreds of bookings, or
drive the counselor's Ollama server for free.
"""
import time
from functools import wraps

from flask import request, jsonify

_hits = {}          # bucket key -> [timestamps]


def _recent(key, window):
    now = time.time()
    hits = [t for t in _hits.get(key, []) if now - t < window]
    if hits:
        _hits[key] = hits
    else:
        _hits.pop(key, None)
    return hits


def check_rate(bucket, limit, window=60, key=None):
    """Record a hit and report whether the caller is over the limit.

    Returns (allowed, retry_after_seconds). Callers that need a non-JSON
    response shape use this directly; most should use @rate_limit.
    """
    ident = key or (request.remote_addr or 'unknown')
    full = f'{bucket}:{ident}'
    hits = _recent(full, window)
    if len(hits) >= limit:
        return False, int(window - (time.time() - hits[0])) + 1
    _hits.setdefault(full, []).append(time.time())
    return True, 0


def rate_limit(bucket, limit, window=60):
    """Decorator: 429 with a Retry-After header once the caller exceeds limit."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            allowed, retry_after = check_rate(bucket, limit, window)
            if not allowed:
                resp = jsonify({
                    'error': 'Too many requests. Please wait a moment and try again.'
                })
                resp.status_code = 429
                resp.headers['Retry-After'] = str(retry_after)
                return resp
            return f(*args, **kwargs)
        return wrapper
    return decorator


def clamp(value, max_len):
    """Truncate free text from an unauthenticated caller.

    These fields are persisted and then rendered back to the counselor (and
    into the iCal feed), so an uncapped POST body is both a storage and a
    display problem.
    """
    if value is None:
        return ''
    return str(value).strip()[:max_len]
