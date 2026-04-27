"""SSE streaming helpers for Ollama AI generation."""
import json
from flask import Response, stream_with_context
from app.utils import ollama_client


def stream_sse(prompt, system=None, temperature=0.7, timeout=None):
    """Return a Flask Response that streams SSE tokens from Ollama.

    Each SSE event is either:
      data: {"token": "word "}
      data: {"done": true, "full_text": "accumulated output"}
      data: {"error": "message"}
    """
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
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        content_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )
