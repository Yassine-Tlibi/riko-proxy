/**
 * Kiro Gateway - Global Alpine Store
 */

document.addEventListener('alpine:init', () => {
    Alpine.store('global', {
        // App state
        activeTab: 'dashboard',
        version: '2.3',

        // Toast notification
        toast: null,

        // API key
        webuiPassword: localStorage.getItem('kiro_api_key') || '',

        // OAuth progress
        oauthProgress: {
            active: false,
            current: 0,
            max: 60,
            cancel: null
        },

        // Translation function (English only for now)
        t(key) {
            const translations = {
                // System
                'systemName': 'KIRO GATEWAY',
                'systemDesc': 'CLAUDE PROXY SYSTEM',
                'online': 'ONLINE',
                'offline': 'OFFLINE',
                'connecting': 'CONNECTING',
                'live': 'LIVE',
                'refreshData': 'Refresh Data',

                // Navigation
                'main': 'Main',
                'system': 'System',
                'dashboard': 'Dashboard',
                'models': 'Models',
                'logs': 'Logs',
                'settings': 'Settings',

                // Dashboard
                'totalRequests': 'TOTAL REQUESTS',
                'active': 'ACTIVE',
                'rateLimited': 'RATE LIMITED',
                'successRate': 'SUCCESS RATE',
                'requestVolume': 'Request Volume',
                'modelUsage': 'Model Usage',
                'allTime': 'All time',
                'operational': 'Operational',
                'cooldown': 'Cooldown',

                // Time ranges
                'last1Hour': 'Last 1 Hour',
                'last6Hours': 'Last 6 Hours',
                'last24Hours': 'Last 24 Hours',
                'last7Days': 'Last 7 Days',

                // Stats
                'totalColon': 'Total:',
                'todayColon': 'Today:',
                'hour1Colon': '1H:',

                // Common
                'close': 'Close',
                'cancel': 'Cancel',
                'save': 'Save',
                'apply': 'Apply',
                'reset': 'Reset',
                'filter': 'Filter',
                'all': 'All',
                'none': 'None',
                'syncing': 'SYNCING...',
                'noDataTracked': 'No data tracked yet'
            };

            return translations[key] || key;
        },

        // Show toast notification
        showToast(message, type = 'info') {
            this.toast = { message, type };
            setTimeout(() => {
                this.toast = null;
            }, 3000);
        }
    });
});
