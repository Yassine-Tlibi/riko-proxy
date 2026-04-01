/**
 * Kiro Gateway - Utility Functions
 */

window.utils = {
    /**
     * Make authenticated API request
     */
    async request(url, options = {}, apiKey = null) {
        const key = apiKey || localStorage.getItem('kiro_api_key');

        const headers = {
            'Content-Type': 'application/json',
            ...options.headers
        };

        if (key) {
            headers['Authorization'] = `Bearer ${key}`;
        }

        const response = await fetch(url, {
            ...options,
            headers
        });

        return { response };
    },

    /**
     * Format uptime seconds to human readable
     */
    formatUptime(seconds) {
        if (!seconds) return '0s';

        const days = Math.floor(seconds / 86400);
        const hours = Math.floor((seconds % 86400) / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);

        const parts = [];
        if (days > 0) parts.push(`${days}d`);
        if (hours > 0) parts.push(`${hours}h`);
        if (minutes > 0) parts.push(`${minutes}m`);
        if (secs > 0 || parts.length === 0) parts.push(`${secs}s`);

        return parts.join(' ');
    },

    /**
     * Format bytes to human readable
     */
    formatBytes(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
    },

    /**
     * Get theme color from CSS variable
     */
    getThemeColor(varName) {
        return getComputedStyle(document.documentElement)
            .getPropertyValue(varName).trim();
    },

    /**
     * Debounce function
     */
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
};
