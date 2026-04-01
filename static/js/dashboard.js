// Dashboard Alpine.js component
function dashboard() {
    return {
        // Current view
        currentView: 'dashboard',

        // Current time
        currentTime: '',

        // Metrics data
        metrics: {
            total_requests: 0,
            active_requests: 0,
            rate_limited: 0,
            quota_used_percent: 0,
            request_volume: [],
            model_usage: {},
            status_codes: {}
        },

        // Health data
        health: {
            status: 'ok',
            uptime_seconds: 0,
            memory_usage_mb: 0,
            active_connections: 0,
            database_stats: {}
        },

        // Chart instance
        requestVolumeChart: null,

        // Update interval
        updateInterval: null,

        // API key (from localStorage or prompt)
        apiKey: '',

        // Initialize
        init() {
            console.log('Dashboard initializing...');

            // Get API key
            this.apiKey = localStorage.getItem('kiro_api_key');
            if (!this.apiKey) {
                this.apiKey = prompt('Enter your PROXY_API_KEY:');
                if (this.apiKey) {
                    localStorage.setItem('kiro_api_key', this.apiKey);
                }
            }

            // Update current time
            this.updateTime();
            setInterval(() => this.updateTime(), 1000);

            // Load initial data
            this.loadMetrics();
            this.loadHealth();

            // Set up auto-refresh (15 seconds)
            this.updateInterval = setInterval(() => {
                if (!document.hidden) {
                    this.loadMetrics();
                    this.loadHealth();
                }
            }, 15000);

            // Initialize chart after a short delay to ensure canvas is ready
            setTimeout(() => this.initChart(), 100);
        },

        // Update current time
        updateTime() {
            const now = new Date();
            this.currentTime = now.toLocaleTimeString('en-US', {
                hour12: true,
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            });
        },

        // Load metrics from API
        async loadMetrics() {
            try {
                const response = await fetch('/api/metrics?hours=24', {
                    headers: {
                        'Authorization': `Bearer ${this.apiKey}`
                    }
                });

                if (!response.ok) {
                    if (response.status === 401 || response.status === 403) {
                        localStorage.removeItem('kiro_api_key');
                        alert('Invalid API key. Please refresh and enter the correct key.');
                        return;
                    }
                    throw new Error(`HTTP ${response.status}`);
                }

                const data = await response.json();
                this.metrics = data;

                // Update chart
                this.updateChart();

                console.log('Metrics loaded:', data);
            } catch (error) {
                console.error('Failed to load metrics:', error);
            }
        },

        // Load health from API
        async loadHealth() {
            try {
                const response = await fetch('/api/health', {
                    headers: {
                        'Authorization': `Bearer ${this.apiKey}`
                    }
                });

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }

                const data = await response.json();
                this.health = data;

                console.log('Health loaded:', data);
            } catch (error) {
                console.error('Failed to load health:', error);
            }
        },

        // Initialize request volume chart
        initChart() {
            const canvas = document.getElementById('requestVolumeChart');
            if (!canvas) {
                console.error('Chart canvas not found');
                return;
            }

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
                        pointBorderColor: '#22C55E',
                        pointHoverBackgroundColor: '#22C55E',
                        pointHoverBorderColor: '#F8FAFC'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    plugins: {
                        legend: {
                            display: false
                        },
                        tooltip: {
                            mode: 'index',
                            intersect: false,
                            backgroundColor: '#1E293B',
                            titleColor: '#F8FAFC',
                            bodyColor: '#F8FAFC',
                            borderColor: '#22C55E',
                            borderWidth: 2,
                            padding: 12,
                            displayColors: false,
                            callbacks: {
                                label: function(context) {
                                    return `Requests: ${context.parsed.y}`;
                                }
                            }
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
                                maxRotation: 45,
                                minRotation: 45,
                                font: {
                                    family: 'JetBrains Mono',
                                    size: 11
                                }
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
                                font: {
                                    family: 'JetBrains Mono',
                                    size: 11
                                }
                            }
                        }
                    },
                    interaction: {
                        mode: 'nearest',
                        axis: 'x',
                        intersect: false
                    }
                }
            });

            console.log('Chart initialized');
        },

        // Update chart with new data
        updateChart() {
            if (!this.requestVolumeChart) {
                return;
            }

            // Prepare labels and data
            const labels = this.metrics.request_volume.map(point => {
                const date = new Date(point.timestamp * 1000);
                return date.toLocaleTimeString('en-US', {
                    hour: '2-digit',
                    minute: '2-digit',
                    hour12: false
                });
            });

            const data = this.metrics.request_volume.map(point => point.count);

            // Update chart
            this.requestVolumeChart.data.labels = labels;
            this.requestVolumeChart.data.datasets[0].data = data;
            this.requestVolumeChart.update('none'); // Update without animation for smoother updates

            console.log('Chart updated with', data.length, 'data points');
        },

        // Format uptime
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

        // Cleanup on destroy
        destroy() {
            if (this.updateInterval) {
                clearInterval(this.updateInterval);
            }
            if (this.requestVolumeChart) {
                this.requestVolumeChart.destroy();
            }
        }
    };
}
