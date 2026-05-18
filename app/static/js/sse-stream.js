/* Shared helper for consuming Server-Sent Event streams from local AI endpoints.
 *
 * Backend protocol (see app/utils/stream_helpers.py):
 *   "data: {token: '...'}\n"        — incremental output chunk
 *   "data: {transcript: '...'}\n"   — emitted once after audio transcription
 *   "data: {done: true, full_text}" — final marker; full_text is a fallback
 *   "data: {error: '...'}"          — server-side failure
 *
 * Usage:
 *   streamSSE({
 *     url: '/ai/foo-stream',
 *     body: {student_id: 42},          // object → JSON; FormData → multipart
 *     csrf: '{{ csrf_token() }}',      // omit for FormData uploads
 *     onToken:  function(t) { ... },   // called per token chunk
 *     onEvent:  function(d) { ... },   // optional catch-all for custom events
 *     onDone:   function(d) { ... },   // called once when data.done arrives
 *     onError:  function(msg) { ... }, // network failure or data.error
 *   });
 */
(function () {
    function streamSSE(opts) {
        var headers = {};
        var body;
        if (opts.body instanceof FormData) {
            body = opts.body;
        } else if (opts.body !== undefined) {
            headers['Content-Type'] = 'application/json';
            body = JSON.stringify(opts.body);
        }
        if (opts.csrf) headers['X-CSRFToken'] = opts.csrf;

        fetch(opts.url, {
            method: opts.method || 'POST',
            headers: headers,
            body: body,
        }).then(function (response) {
            if (!response.ok) {
                return response.json()
                    .catch(function () { return {error: 'Request failed (' + response.status + ')'}; })
                    .then(function (d) { throw new Error(d.error || 'Request failed'); });
            }
            var reader = response.body.getReader();
            var decoder = new TextDecoder();
            var buffer = '';

            function pump() {
                reader.read().then(function (r) {
                    if (r.done) return;
                    buffer += decoder.decode(r.value, {stream: true});
                    var lines = buffer.split('\n');
                    buffer = lines.pop();
                    lines.forEach(function (line) {
                        if (!line.startsWith('data: ')) return;
                        var data;
                        try { data = JSON.parse(line.slice(6)); } catch (e) { return; }
                        if (opts.onEvent) opts.onEvent(data);
                        if (data.token && opts.onToken) opts.onToken(data.token);
                        if (data.error && opts.onError) opts.onError(data.error);
                        if (data.done && opts.onDone) opts.onDone(data);
                    });
                    pump();
                }).catch(function (err) {
                    if (opts.onError) opts.onError(err.message || String(err));
                });
            }
            pump();
        }).catch(function (err) {
            if (opts.onError) opts.onError(err.message || String(err));
        });
    }

    window.streamSSE = streamSSE;
})();
