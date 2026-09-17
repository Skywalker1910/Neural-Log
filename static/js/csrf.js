/**
 * Attach the CSRF token to every write the classic app makes.
 *
 * The server now rejects any POST/PUT/PATCH/DELETE that does not echo the
 * `csrf_token` cookie back in an `X-CSRF-Token` header. The classic dashboard
 * makes those writes through about twenty hand-rolled `fetch()` calls scattered
 * across 1,600 lines of app.js, and threading a header through all of them means
 * twenty chances to miss one - where "missed one" shows up as a feature that
 * silently stopped working.
 *
 * So it is done once, here, by wrapping `fetch` itself. The wrapper is
 * deliberately conservative: it only touches same-origin requests, only
 * state-changing methods, and never overwrites a header the caller set. Anything
 * it does not understand it passes straight through.
 *
 * The SPA does not load this. It has one `request()` function and sets the
 * header there, which is the better arrangement and the reason this file exists
 * only for the older half of the app.
 */
(function () {
    'use strict';

    var UNSAFE = /^(POST|PUT|PATCH|DELETE)$/i;

    function token() {
        var match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    function sameOrigin(input) {
        try {
            var url = new URL(
                typeof input === 'string' ? input : input.url,
                window.location.href
            );
            return url.origin === window.location.origin;
        } catch (error) {
            // A Request object from somewhere exotic, or a malformed URL. Not
            // ours to modify.
            return false;
        }
    }

    var original = window.fetch.bind(window);

    window.fetch = function (input, init) {
        var options = init || {};
        var method = options.method || (input && input.method) || 'GET';

        if (!UNSAFE.test(method) || !sameOrigin(input)) {
            return original(input, init);
        }

        var headers = new Headers(options.headers || (input && input.headers) || {});
        if (!headers.has('X-CSRF-Token')) {
            headers.set('X-CSRF-Token', token());
        }

        return original(input, Object.assign({}, options, { headers: headers }));
    };
})();
