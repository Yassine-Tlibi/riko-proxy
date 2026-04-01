/**
 * Kiro Gateway - Dashboard Component
 */

window.Components = window.Components || {};

window.Components.dashboard = () => ({
    // Stats
    stats: {
        total: 0,
        active: 0,
        limited: 0,
        successRate: 0
    },

    // Usage stats
    usageStats: {
        total: 0,
        today: 0,
        thisHour: 0
    },

    // Chart instances
    requestVolumeChart: null,

    // Dropdowns
    showTimeRangeDropdown: false,
    showDisplayModeDropdown: false,
    showModelFilter: false,

    // Filters
    timeRange: '24h',
    displayMode: 'family',

    init() {
        this.computeStats();
        this.initCharts();

        // Watch for data changes
        this.$watch('$store.data.metrics', () => {
            this.computeStats();
            this.updateCharts();
        });
    },

    computeStats() {
        const metrics = this.$store.data.metrics;

        this.stats.total = metrics.total_requests || 0;
        this.stats.active = metrics.active_requests || 0;
        this.stats.limited = metrics.rate_limited || 0;

        // Calculate success rate
        const statusCodes = metrics.status_codes || {};
        const total = Object.values(statusCodes).reduce((a, b) => a + b, 0);
        const success = statusCodes['200'] || 0;
        this.stats.successRate = total > 0 ? Math.round((success / total) * 100) : 0;

        // Calculate usage stats
        const volume = metrics.request_volume || [];
        this.usageStats.total = volume.reduce((sum, p) => sum + p.count, 0);

        // Today's requests
        const today = new Date().toISOString().split('T')[0];
        this.usageStats.today = volume
            .filter(p => new Date(p.timestamp * 1000).toISOString().split('T')[0] === today)
            .reduce((sum, p) => sum + p.count, 0);

        // This hour's requests
        const currentHour = new Date().getHours();
        this.usageStats.thisHour = volume
            .filter(p => new Date(p.timestamp * 1000).getHours() === currentHour)
            .reduce((sum, p) => sum + p.count, 0);
    },

    initCharts() {
        this.$nextTick(() => {
            const canvas = document.getElementById('requestVolumeChart');
            if (!canvas) return;

            const ctx = canvas.getContext('2d');

            this.requestVolumeChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Requests',
                        data: [],
                        borderColor: '#22C55E',
                        backgroundColor: 'rgba(34, 197, 94, 0.1)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.4,
                        pointRadius: 3,
                        pointHoverRadius: 5,
                        pointBackgroundColor: '#22C55E',
                        pointBorderColor: '#22C55E'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            mode: 'index',
                            intersect: false,
                            backgroundColor: '#1E293B',
                            titleColor: '#F8FAFC',
                            bodyColor: '#F8FAFC',
                            borderColor: '#22C55E',
                            borderWidth: 2,
                            padding: 12
                        }
                    },
                    scales: {
                        x: {
                            grid: {
                                color: 'rgba(51, 65, 85, 0.3)',
                                drawBorder: false
                            },
                            ticks: {
                                color: 'rgba(248, 250, 252, 0.6)',
                                font: { family: 'JetBrains Mono', size: 11 }
                            }
                        },
                        y: {
                            beginAtZero: true,
                            grid: {
                                color: 'rgba(51, 65, 85, 0.3)',
                                drawBorder: false
                            },
                            ticks: {
                                color: 'rgba(248, 250, 252, 0.6)',
                                precision: 0,
                                font: { family: 'JetBrains Mono', size: 11 }
                            }
                        }
                    }
                }
            });

            this.updateCharts();
        });
    },

    updateCharts() {
        if (!this.requestVolumeChart) return;

        const volume = this.$store.data.metrics.request_volume || [];

        const labels = volume.map(point => {
            const date = new Date(point.timestamp * 1000);
            return date.toLocaleTimeString('en-US', {
                hour: '2-digit',
                minute: '2-digit',
                hour12: false
            });
        });

        const data = volume.map(point => point.count);

        this.requestVolumeChart.data.labels = labels;
        this.requestVolumeChart.data.datasets[0].data = data;
        this.requestVolumeChart.update('none');
    },

    setTimeRange(range) {
        this.timeRange = range;
        this.showTimeRangeDropdown = false;
    },

    getTimeRangeLabel() {
        const labels = {
            '1h': this.$store.global.t('last1Hour'),
            '6h': this.$store.global.t('last6Hours'),
            '24h': this.$store.global.t('last24Hours'),
            '7d': this.$store.global.t('last7Days'),
            'all': this.$store.global.t('allTime')
        };
        return labels[this.timeRange] || '24h';
    }
});
