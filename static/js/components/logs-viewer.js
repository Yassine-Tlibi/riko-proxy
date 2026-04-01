/**
 * Kiro Gateway - Logs Viewer Component
 */

window.Components = window.Components || {};

window.Components.logsViewer = () => ({
    logs: [],
    loading: false,
    autoRefresh: true,
    searchQuery: '',
    levelFilter: 'all',

    init() {
        this.loadLogs();

        if (this.autoRefresh) {
            this.startAutoRefresh();
        }
    },

    async loadLogs() {
        this.loading = true;
        await this.$store.data.fetchLogs(100);
        this.logs = this.$store.data.logs;
        this.loading = false;
    },

    startAutoRefresh() {
        setInterval(() => {
            if (this.autoRefresh) {
                this.loadLogs();
            }
        }, 5000);
    },

    get filteredLogs() {
        let filtered = this.logs;

        // Filter by level
        if (this.levelFilter !== 'all') {
            filtered = filtered.filter(log => log.level === this.levelFilter);
        }

        // Filter by search query
        if (this.searchQuery) {
            const query = this.searchQuery.toLowerCase();
            filtered = filtered.filter(log =>
                log.message.toLowerCase().includes(query)
            );
        }

        return filtered;
    },

    getLevelColor(level) {
        const colors = {
            'DEBUG': 'text-gray-500',
            'INFO': 'text-blue-400',
            'WARNING': 'text-yellow-400',
            'ERROR': 'text-red-400',
            'CRITICAL': 'text-red-600'
        };
        return colors[level] || 'text-gray-400';
    }
});
