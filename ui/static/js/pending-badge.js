/**
 * Site-wide "needs confirmation" badge in the sidebar.
 *
 * Shows a count of recipes awaiting confirmation and links to History
 * pre-filtered to that status, so the user doesn't need browser
 * notification permission to notice new recipes waiting on them.
 */
document.addEventListener('DOMContentLoaded', function() {
    const badgeLink = document.getElementById('pending-badge-link');
    const badgeCount = document.getElementById('pending-badge-count');
    if (!badgeLink || !badgeCount) return;

    function setCount(count) {
        if (count > 0) {
            badgeCount.textContent = count > 99 ? '99+' : String(count);
            badgeLink.style.display = '';
        } else {
            badgeLink.style.display = 'none';
        }
    }

    async function refresh() {
        try {
            const response = await fetch('/api/pending-uploads/count');
            if (!response.ok) return;
            const data = await response.json();
            setCount(data.count || 0);
        } catch (e) {
            // Silent - badge just keeps its last known value.
        }
    }

    refresh();
    setInterval(refresh, 20000);

    if (window.io) {
        const badgeSocket = io();
        badgeSocket.on('connect', refresh);
        badgeSocket.on('recipe_preview', refresh);
        badgeSocket.on('recipe_cancelled', refresh);
    }
});
