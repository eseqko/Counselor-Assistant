"""SSE streaming helpers for Ollama AI generation."""
import json
from flask import Response, stream_with_context
from app.utils import ollama_client
from app.utils.context_budget import budget_prompt


def stream_sse(prompt, system=None, temperature=0.7, timeout=None):
    """Return a Flask Response that streams SSE tokens from Ollama.

    Automatically applies context budget management before streaming.
    """
    prompt, system = budget_prompt(prompt, system)

    def generate():
        full_text = []
        try:
            for token, done in ollama_client.generate_stream(
                    prompt, system=system, temperature=temperature, timeout=timeout):
                full_text.append(token)
                if token:
                    yield f"data: {json.dumps({'token': token})}\n\n"
                if done:
                    yield f"data: {json.dumps({'done': True, 'full_text': ''.join(full_text).strip()})}\n\n"
        except Exception:
            # Never surface the raw exception: a requests error stringifies with
            # the internal Ollama host/port/URL, and this stream serves the
            # unauthenticated student portal. Log server-side, emit a generic
            # message.
            try:
                from flask import current_app
                current_app.logger.exception('SSE AI generation failed')
            except Exception:
                pass
            yield f"data: {json.dumps({'error': 'AI generation failed. Please try again.'})}\n\n"

    return Response(
        stream_with_context(generate()),
        content_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )
