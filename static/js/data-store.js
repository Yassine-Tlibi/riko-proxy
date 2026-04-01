/**
 * Kiro Gateway - Data Store
 */

document.addEventListener('alpine:init', () => {
    Alpine.store('data', {
        // Connection state
        connectionStatus: 'connecting',
        loading: false,
        initialLoad: true,

        // Data
        metrics: {
            total_requests: 0,
            active_requests: 0,
            rate_limited: 0,
            quota_used_percent: 0,
            request_volume: [],
            model_usage: {},
            status_codes: {}
        },

        health: {
            status: 'ok',
            uptime_seconds: 0,
            memory_usage_mb: 0,
            active_connections: 0,
            database_stats: {}
        },

        models: [],
        logs: [],

        // Filters
        filters: {
            timeRange: '24h',
            family: null,
            model: null
        },

        // Fetch all data
        async fetchData() {
            if (this.loading) return;

            this.loading = true;

            try {
                const apiKey = Alpine.store('global').webuiPassword;

                // Fetch metrics
                const { response: metricsRes } = await window.utils.request('/api/metrics?hours=24', {}, apiKey);
                if (metricsRes.ok) {
                    this.metrics = await metricsRes.json();
                    this.connectionStatus = 'connected';
                }

                // Fetch health
                const { response: healthRes } = await window.utils.request('/api/health', {}, apiKey);
                if (healthRes.ok) {
                    this.health = await healthRes.json();
                }

                this.initialLoad = false;
            } catch (error) {
                console.error('Failed to fetch data:', error);
                this.connectionStatus = 'disconnected';
                Alpine.store('global').showToast('Failed to fetch data: ' + error.message, 'error');
            } finally {
                this.loading = false;
            }
        },

        // Fetch models
        async fetchModels() {
            try {
                const apiKey = Alpine.store('global').webuiPassword;
                const { response } = await window.utils.request('/v1/models', {}, apiKey);

                if (response.ok) {
                    const data = await response.json();
                    this.models = data.data || [];
                }
            } catch (error) {
                console.error('Failed to fetch models:', error);
            }
        },

        // Fetch logs
        async fetchLogs(limit = 100) {
            try {
                const apiKey = Alpine.store('global').webuiPassword;
                const { response } = await window.utils.request(`/api/logs?limit=${limit}`, {}, apiKey);

                if (response.ok) {
                    this.logs = await response.json();
                }
            } catch (error) {
                console.error('Failed to fetch logs:', error);
            }
        }
    });
});
