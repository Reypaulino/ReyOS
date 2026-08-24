(function () {
    if (window.__reyosFingerprintProtected) {
        return;
    }
    window.__reyosFingerprintProtected = true;

    var SESSION_KEY = "%%SESSION_KEY%%";

    function fnv1a(str) {
        var h = 0x811c9dc5;
        for (var i = 0; i < str.length; i++) {
            h ^= str.charCodeAt(i);
            h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
        }
        return h >>> 0;
    }

    function mulberry32(seed) {
        var a = seed >>> 0;
        return function () {
            a = (a + 0x6D2B79F5) | 0;
            var t = Math.imul(a ^ (a >>> 15), 1 | a);
            t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
            return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
        };
    }

    // Same session + same site => same noise all session long (stable UI, no flicker).
    // Different site, or a fresh browser launch => different noise (breaks cross-site/long-term tracking).
    var siteSeed = fnv1a(SESSION_KEY + "|" + location.hostname);

    // Canvas fingerprinting: perturb a small, bounded sample of pixels rather than
    // the whole buffer, so this stays cheap even inside a hot render loop.
    if (window.CanvasRenderingContext2D) {
        var origGetImageData = CanvasRenderingContext2D.prototype.getImageData;
        CanvasRenderingContext2D.prototype.getImageData = function () {
            var imageData = origGetImageData.apply(this, arguments);
            var data = imageData.data;
            var pixelCount = data.length / 4;
            if (pixelCount > 0) {
                var rand = mulberry32(siteSeed);
                var samples = Math.min(2000, Math.max(8, Math.floor(pixelCount * 0.02)));
                for (var s = 0; s < samples; s++) {
                    var idx = Math.floor(rand() * pixelCount) * 4;
                    data[idx] = data[idx] ^ 1;
                }
            }
            return imageData;
        };
    }

    if (window.HTMLCanvasElement) {
        var origToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function () {
            try {
                var ctx = this.getContext && this.getContext("2d");
                if (ctx && this.width > 0 && this.height > 0) {
                    var imageData = ctx.getImageData(0, 0, this.width, this.height);
                    ctx.putImageData(imageData, 0, 0);
                }
            } catch (e) {
                // Non-2D context (e.g. WebGL) or tainted canvas: leave untouched.
            }
            return origToDataURL.apply(this, arguments);
        };
    }

    // WebGL fingerprinting: the GPU vendor/renderer strings are the single
    // highest-value identifier exposed via WEBGL_debug_renderer_info.
    function spoofRendererInfo(proto) {
        var origGetParameter = proto.getParameter;
        proto.getParameter = function (param) {
            if (param === 37445) return "Generic Vendor"; // UNMASKED_VENDOR_WEBGL
            if (param === 37446) return "Generic Renderer"; // UNMASKED_RENDERER_WEBGL
            return origGetParameter.apply(this, arguments);
        };
    }
    if (window.WebGLRenderingContext) {
        spoofRendererInfo(WebGLRenderingContext.prototype);
    }
    if (window.WebGL2RenderingContext) {
        spoofRendererInfo(WebGL2RenderingContext.prototype);
    }

    // AudioContext fingerprinting: nudge a sparse sample of samples by an
    // inaudible amount, deterministic per site+session.
    if (window.AudioBuffer) {
        var origGetChannelData = AudioBuffer.prototype.getChannelData;
        AudioBuffer.prototype.getChannelData = function () {
            var data = origGetChannelData.apply(this, arguments);
            var rand = mulberry32(siteSeed ^ 0x9e3779b9);
            for (var i = 0; i < data.length; i += 100) {
                data[i] += (rand() - 0.5) * 0.0001;
            }
            return data;
        };
    }
})();
