/**
 * Kiro Gateway - Main Application Entry
 */

document.addEventListener('alpine:init', () => {
    // Register Components
    Alpine.data('dashboard', window.Components.dashboard);
    Alpine.data('models', window.Components.models);
    Alpine.data('accounts', window.Components.accounts);
    Alpine.data('logsViewer', window.Components.logsViewer);
    Alpine.data('settings', window.Components.settings);

    // View Loader Directive
    Alpine.directive('load-view', (el, { expression }, { evaluate }) => {
        if (!window.viewCache) window.viewCache = new Map();
        if (!window.viewsInitialized) window.viewsInitialized = new Set();

        const viewName = evaluate(expression);
        const viewKey = `${viewName}-${el.id || el.className}`;

        // Prevent re-initialization of already loaded views
        if (window.viewsInitialized.has(viewKey)) {
            return;
        }

        if (window.viewCache.has(viewName)) {
            el.innerHTML = window.viewCache.get(viewName);
            window.viewsInitialized.add(viewKey);
            // Use nextTick to avoid initialization race conditions
            queueMicrotask(() => Alpine.initTree(el));
            return;
        }

        fetch(`views/${viewName}.html?t=${Date.now()}`)
            .then(response => {
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                return response.text();
            })
            .then(html => {
                window.viewCache.set(viewName, html);
                el.innerHTML = html;
                window.viewsInitialized.add(viewKey);
                // Use nextTick to avoid initialization race conditions
                queueMicrotask(() => Alpine.initTree(el));
            })
            .catch(err => {
                console.error('Failed to load view:', viewName, err);
                el.innerHTML = `<div class="p-4 border border-red-500/50 bg-red-500/10 rounded-lg text-red-400 font-mono text-sm">
                    Error loading view: ${viewName}<br>
                    <span class="text-xs opacity-75">${err.message}</span>
                </div>`;
            });
    });

    // Main App Controller
    Alpine.data('app', () => ({
        get connectionStatus() {
            return Alpine.store('data')?.connectionStatus || 'connecting';
        },
        get loading() {
            return Alpine.store('data')?.loading || false;
        },

        sidebarOpen: window.innerWidth >= 1024,

        toggleSidebar() {
            this.sidebarOpen = !this.sidebarOpen;
        },

        init() {
            // Handle responsive sidebar
            let lastWidth = window.innerWidth;
            let resizeTimeout = null;

            window.addEventListener('resize', () => {
                if (resizeTimeout) clearTimeout(resizeTimeout);

                resizeTimeout = setTimeout(() => {
                    const currentWidth = window.innerWidth;
                    const lgBreakpoint = 1024;

                    if (lastWidth >= lgBreakpoint && currentWidth < lgBreakpoint) {
                        this.sidebarOpen = false;
                    }

                    if (lastWidth < lgBreakpoint && currentWidth >= lgBreakpoint) {
                        this.sidebarOpen = true;
                    }

                    lastWidth = currentWidth;
                }, 150);
            });

            // Theme setup
            document.documentElement.setAttribute('data-theme', 'dark');
            document.documentElement.classList.add('dark');

            // Chart Defaults
            if (typeof Chart !== 'undefined') {
                Chart.defaults.color = 'rgba(248, 250, 252, 0.6)';
                Chart.defaults.borderColor = '#334155';
                Chart.defaults.font.family = '"JetBrains Mono", monospace';
            }

            // Initialize stores
            Alpine.store('settings').init();

            // Start auto-refresh
            this.startAutoRefresh();
            document.addEventListener('refresh-interval-changed', () => this.startAutoRefresh());

            // Initial data fetch
            Alpine.store('data').fetchData();
        },

        refreshTimer: null,

        fetchData() {
            Alpine.store('data').fetchData();
        },

        startAutoRefresh() {
            if (this.refreshTimer) clearInterval(this.refreshTimer);
            const interval = parseInt(Alpine.store('settings')?.refreshInterval || 15);
            if (interval > 0) {
                this.refreshTimer = setInterval(() => Alpine.store('data').fetchData(), interval * 1000);
            }
        }
    }));
});
