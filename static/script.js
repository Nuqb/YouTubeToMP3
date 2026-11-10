let isConverting = false;

function showLoading() {
    isConverting = true;
    document.getElementById('btn-text').textContent = 'Converting';
    document.getElementById('loading-spinner').hidden = false;
    document.getElementById('convert-btn').disabled = true;
    document.getElementById('youtube-url').disabled = true;
    document.getElementById('artist-name').disabled = true;
    document.getElementById('convert-form').setAttribute('aria-busy', 'true');
}

function hideLoading() {
    document.getElementById('btn-text').textContent = 'Convert';
    document.getElementById('loading-spinner').hidden = true;
    document.getElementById('convert-btn').disabled = false;
    document.getElementById('youtube-url').disabled = false;
    document.getElementById('artist-name').disabled = false;
    document.getElementById('convert-form').setAttribute('aria-busy', 'false');
    isConverting = false;
}

function showResult(data) {
    document.getElementById('video-title').textContent = data.title;
    document.getElementById('download-link').href = data.download_url;
    document.getElementById('download-link').download = data.title + '.mp3';
    document.getElementById('result-section').hidden = false;
    document.getElementById('error-section').hidden = true;
}

function showError(message) {
    document.getElementById('error-message').textContent = message;
    document.getElementById('error-section').hidden = false;
    document.getElementById('result-section').hidden = true;
}

function hideResults() {
    document.getElementById('result-section').hidden = true;
    document.getElementById('error-section').hidden = true;
    document.getElementById('youtube-url').removeAttribute('aria-invalid');
}

async function convertVideo() {
    if (isConverting) return;

    const input = document.getElementById('youtube-url');
    const url = input.value.trim();
    const artist = document.getElementById('artist-name').value.trim();
    input.value = url;

    if (!url || !input.validity.valid) {
        input.setAttribute('aria-invalid', 'true');
        showError(url ? 'Enter a valid track or video URL, starting with https://.' : 'Paste a track or video URL to get started.');
        input.focus();
        return;
    }

    hideResults();
    showLoading();

    try {
        const response = await fetch('/convert', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, artist: artist || undefined })
        });
        const data = await response.json();

        if (response.ok && data.success) {
            showResult(data);
        } else {
            showError(data.error || 'Conversion failed. Check the URL and try again.');
        }
    } catch (error) {
        showError('Connection interrupted. Please try again.');
    } finally {
        hideLoading();
    }
}

document.addEventListener('DOMContentLoaded', function () {
    const artistToggle = document.getElementById('artist-toggle');
    const artistOptions = document.getElementById('artist-options');
    artistToggle.addEventListener('click', function () {
        const expanded = artistToggle.getAttribute('aria-expanded') !== 'true';
        artistToggle.setAttribute('aria-expanded', String(expanded));
        artistOptions.inert = !expanded;
    });

    document.getElementById('convert-form').addEventListener('submit', function (event) {
        event.preventDefault();
        convertVideo();
    });

    for (const id of ['youtube-url', 'artist-name']) {
        document.getElementById(id).addEventListener('input', hideResults);
    }
});
