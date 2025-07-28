// YouTube to MP3 Converter - Main JavaScript File

let isConverting = false;

// UI State Management Functions
function showLoading() {
    document.getElementById('btn-text').style.display = 'none';
    document.getElementById('loading-spinner').style.display = 'inline-block';
    document.getElementById('convert-btn').disabled = true;
    document.getElementById('youtube-url').disabled = true;
    isConverting = true;
}

function hideLoading() {
    document.getElementById('btn-text').style.display = 'inline';
    document.getElementById('loading-spinner').style.display = 'none';
    document.getElementById('convert-btn').disabled = false;
    document.getElementById('youtube-url').disabled = false;
    isConverting = false;
}

function showResult(data) {
    document.getElementById('video-title').textContent = data.title;
    document.getElementById('download-link').href = data.download_url;
    document.getElementById('download-link').download = data.title + '.mp3';
    document.getElementById('result-section').style.display = 'block';
    document.getElementById('error-section').style.display = 'none';
}

function showError(message) {
    document.getElementById('error-message').textContent = message;
    document.getElementById('error-section').style.display = 'block';
    document.getElementById('result-section').style.display = 'none';
}

function hideResults() {
    document.getElementById('result-section').style.display = 'none';
    document.getElementById('error-section').style.display = 'none';
}

// Main Conversion Function
async function convertVideo() {
    if (isConverting) return;

    const url = document.getElementById('youtube-url').value.trim();
    
    if (!url) {
        showError('Please enter a YouTube URL');
        return;
    }

    hideResults();
    showLoading();

    try {
        const response = await fetch('/convert', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ url: url })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            showResult(data);
        } else {
            showError(data.error || 'An error occurred during conversion');
        }
    } catch (error) {
        showError('Network error. Please check your connection and try again.');
    } finally {
        hideLoading();
    }
}

// GitHub Modal Functions
function openGitHubModal() {
    document.getElementById('githubModal').style.display = 'flex';
    document.body.style.overflow = 'hidden'; // Prevent background scrolling
}

function closeGitHubModal(event) {
    if (!event || event.target === document.getElementById('githubModal')) {
        document.getElementById('githubModal').style.display = 'none';
        document.body.style.overflow = 'auto'; // Restore scrolling
    }
}

// Event Listeners
document.addEventListener('DOMContentLoaded', function() {
    // Allow Enter key to trigger conversion
    document.getElementById('youtube-url').addEventListener('keypress', function(e) {
        if (e.key === 'Enter' && !isConverting) {
            convertVideo();
        }
    });

    // Clear results when URL changes
    document.getElementById('youtube-url').addEventListener('input', function() {
        hideResults();
    });

    // Close modal with Escape key
    document.addEventListener('keydown', function(event) {
        if (event.key === 'Escape') {
            closeGitHubModal();
        }
    });
});

// Make functions globally accessible for onclick handlers
window.convertVideo = convertVideo;
window.openGitHubModal = openGitHubModal;
window.closeGitHubModal = closeGitHubModal; 