// Enhanced Dashboard Alpine.js component with improved visualizations
function dashboard() {
    return {
        // Loading state
        loading: false,

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

        // Charts
        requestVolumeChart: null,
        statusCodesChart: null,

        // API key
        apiKey: '',

        // Update interval
        updateInterval: null,

        // Initialize
        init() {
            console.log('Enhanced Dashboard initializing...');

            // Get API key
            this.apiKey = localStorage.getItem('kiro_api_key');
            if (!this.apiKey) {
                this.apiKey = prompt('Enter your PROXY_API_KEY:');
                if (this.apiKey) {
                    localStorage.setItem('kiro_api_key', this.apiKey);
                }
            }

            // Load initial data
            this.loadMetrics();

            // Set up auto-refresh (15 seconds)
            this.updateInterval = setInterval(() => {
                if (!document.hidden) {
                    this.loadMetrics();
                }
            }, 15000);

            // Initialize charts after a short delay
            setTimeout(() => {
                this.initCharts();
            }, 100);
        },

        // Load metrics from API
        async loadMetrics() {
            if (this.loading) return;

            this.loading = true;

            try {
                const response = await fetch('/api/metrics?hours=24', {
                    headers: {
                        'Authorization': `Bearer ${this.apiKey}`
                    }
                });

                if (!response.ok) {
                    if (response.status === 401 || response.status === 403) {
                        localStorage.removeItem('kiro_api_key');
                        this.showToast('Invalid API key. Please refresh and enter the correct key.', 'error');
                        return;
                    }
                    throw new Error(`HTTP ${response.status}`);
                }

                const data = await response.json();

                // Update stats
                this.updateStats(data);

                // Update charts
                this.updateCharts(data);

                // Store in global data store
                if (this.$store && this.$store.data) {
                    this.$store.data.metrics = data;
                }

                console.log('Metrics loaded:', data);
            } catch (error) {
                console.error('Failed to load metrics:', error);
                this.showToast(`Failed to load metrics: ${error.message}`, 'error');
            } finally {
                this.loading = false;
            }
        },

        // Update stats from metrics data
        updateStats(data) {
            this.stats.total = data.total_requests || 0;
            this.stats.active = data.active_requests || 0;
            this.stats.limited = data.rate_limited || 0;

            // Calculate success rate
            const statusCodes = data.status_codes || {};
            const successCount = Object.entries(statusCodes)
                .filter(([code]) => code.startsWith('2'))
                .reduce((sum, [, count]) => sum + count, 0);

            this.stats.successRate = this.stats.total > 0
                ? Math.round((successCount / this.stats.total) * 100)
                : 100;

            // Calculate usage stats
            const requestVolume = data.request_volume || [];
            this.usageStats.total = this.stats.total;

            // Today's requests (last 24 hours)
            this.usageStats.today = requestVolume
                .slice(-24)
                .reduce((sum, item) => sum + (item.count || 0), 0);

            // This hour's requests
            this.usageStats.thisHour = requestVolume.length > 0
                ? requestVolume[requestVolume.length - 1].count || 0
                : 0;

            // Cache sorted model usage to prevent reactivity infinite loops
            const usage = data.model_usage || {};
            this.sortedModelUsage = Object.entries(usage)
                .sort((a, b) => b[1] - a[1]);
        },

        // Initialize charts
        initCharts() {
            this.initRequestVolumeChart();
            this.initStatusCodesChart();
        },

        // Cached values to prevent infinite reactivity loops in templates
        sortedModelUsage: [],

        // Initialize request volume chart
        initRequestVolumeChart() {
            const canvas = document.getElementById('requestVolumeChart');
            if (!canvas) {
                console.error('Request volume chart canvas not found');
                return;
            }

            // Only initialize if the element has physical dimensions to prevent Chart.js fullSize error
            if (canvas.clientHeight === 0 && canvas.clientWidth === 0) {
                setTimeout(() => this.initRequestVolumeChart(), 500);
                return;
            }

            const ctx = canvas.getContext('2d');

            try {
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
                            pointRadius: 0,
                            pointHoverRadius: 6,
                            pointHoverBackgroundColor: '#22C55E',
                            pointHoverBorderColor: '#0F172A',
                            pointHoverBorderWidth: 2
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        interaction: {
                            intersect: false,
                            mode: 'index'
                        },
                        plugins: {
                            legend: {
                                display: false
                            },
                            tooltip: {
                                backgroundColor: '#1E293B',
                                titleColor: '#F8FAFC',
                                bodyColor: '#22C55E',
                                borderColor: '#334155',
                                borderWidth: 1,
                                padding: 12,
                                displayColors: false,
                                callbacks: {
                                    title: (items) => {
                                        return items[0].label;
                                    },
                                    label: (item) => {
                                        return `${item.parsed.y} requests`;
                                    }
                                }
                            }
                        },
                        scales: {
                            x: {
                                grid: {
                                    color: '#334155',
                                    drawBorder: false
                                },
                                ticks: {
                                    color: '#94A3B8',
                                    font: {
                                        family: 'JetBrains Mono',
                                        size: 10
                                    },
                                    maxRotation: 0
                                }
                            },
                            y: {
                                beginAtZero: true,
                                grid: {
                                    color: '#334155',
                                    drawBorder: false
                                },
                                ticks: {
                                    color: '#94A3B8',
                                    font: {
                                        family: 'JetBrains Mono',
                                        size: 10
                                    },
                                    precision: 0
                                }
                            }
                        }
                    }
                });
            } catch (e) {
                console.warn('Failed to initialize request volume chart. The container might be hidden.', e);
            }
        },

        // Initialize status codes chart
        initStatusCodesChart() {
            const canvas = document.getElementById('statusCodesChart');
            if (!canvas) return;

            // Only initialize if the element has physical dimensions
            if (canvas.clientHeight === 0 && canvas.clientWidth === 0) {
                setTimeout(() => this.initStatusCodesChart(), 500);
                return;
            }

            const ctx = canvas.getContext('2d');

            try {
                this.statusCodesChart = new Chart(ctx, {
                    type: 'doughnut',
                    data: {
                        labels: [],
                        datasets: [{
                            data: [],
                            backgroundColor: [
                                '#22C55E', // 2xx - green
                                '#3B82F6', // 3xx - blue
                                '#F59E0B', // 4xx - yellow
                                '#EF4444'  // 5xx - red
                            ],
                            borderColor: '#0F172A',
                            borderWidth: 2
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                position: 'right',
                                labels: {
                                    color: '#F8FAFC',
                                    font: {
                                        family: 'JetBrains Mono',
                                        size: 11
                                    },
                                    padding: 15,
                                    usePointStyle: true,
                                    pointStyle: 'circle'
                                }
                            },
                            tooltip: {
                                backgroundColor: '#1E293B',
                                titleColor: '#F8FAFC',
                                bodyColor: '#22C55E',
                                borderColor: '#334155',
                                borderWidth: 1,
                                padding: 12,
                                callbacks: {
                                    label: (item) => {
                                        const total = item.dataset.data.reduce((a, b) => a + b, 0);
                                        const percentage = ((item.parsed / total) * 100).toFixed(1);
                                        return `${item.label}: ${item.parsed} (${percentage}%)`;
                                    }
                                }
                            }
                        }
                    }
                });
            } catch (e) {
                console.warn('Failed to initialize status codes chart. The container might be hidden.', e);
            }
        },

        // Update charts with new data
        updateCharts(data) {
            this.updateRequestVolumeChart(data);
            this.updateStatusCodesChart(data);
        },

        // Update request volume chart
        updateRequestVolumeChart(data) {
            if (!this.requestVolumeChart) return;

            const requestVolume = data.request_volume || [];

            // Prepare labels and data (last 24 hours)
            const labels = requestVolume.slice(-24).map(item => {
                const date = new Date(item.timestamp);
                return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            });

            const counts = requestVolume.slice(-24).map(item => item.count || 0);

            // Update chart
            this.requestVolumeChart.data.labels = labels;
            this.requestVolumeChart.data.datasets[0].data = counts;
            this.requestVolumeChart.update('none'); // No animation for updates
        },

        // Update status codes chart
        updateStatusCodesChart(data) {
            if (!this.statusCodesChart) return;

            const statusCodes = data.status_codes || {};

            // Group by status code category
            const categories = {
                '2xx Success': 0,
                '3xx Redirect': 0,
                '4xx Client Error': 0,
                '5xx Server Error': 0
            };

            Object.entries(statusCodes).forEach(([code, count]) => {
                const category = Math.floor(parseInt(code) / 100);
                if (category === 2) categories['2xx Success'] += count;
                else if (category === 3) categories['3xx Redirect'] += count;
                else if (category === 4) categories['4xx Client Error'] += count;
                else if (category === 5) categories['5xx Server Error'] += count;
            });

            // Filter out zero values
            const labels = [];
            const values = [];
            Object.entries(categories).forEach(([label, value]) => {
                if (value > 0) {
                    labels.push(label);
                    values.push(value);
                }
            });

            // Update chart
            this.statusCodesChart.data.labels = labels;
            this.statusCodesChart.data.datasets[0].data = values;
            this.statusCodesChart.update('none');
        },

        // Show toast notification
        showToast(message, type = 'info') {
            if (this.$store && this.$store.global) {
                this.$store.global.showToast(message, type);
            }
        },

        // Cleanup on destroy
        destroy() {
            if (this.updateInterval) {
                clearInterval(this.updateInterval);
            }
            if (this.requestVolumeChart) {
                this.requestVolumeChart.destroy();
            }
            if (this.statusCodesChart) {
                this.statusCodesChart.destroy();
            }
        }
    };
}
