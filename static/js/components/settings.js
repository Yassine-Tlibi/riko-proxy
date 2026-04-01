/**
 * Kiro Gateway - Settings Component
 */

window.Components = window.Components || {};

window.Components.settings = () => ({
    settings: {
        refreshInterval: 15,
        showConfigWarning: true,
        theme: 'dark',
        accountStrategy: 'hybrid',
        autoRefreshAccounts: true,
        debugMode: false,
        showTimestamps: true
    },

    originalSettings: {},
    validationErrors: {},

    get hasUnsavedChanges() {
        return JSON.stringify(this.settings) !== JSON.stringify(this.originalSettings);
    },

    get isValid() {
        return Object.keys(this.validationErrors).length === 0;
    },

    init() {
        // Load settings from store
        this.settings = { ...this.$store.settings };
        this.originalSettings = { ...this.settings };

        // Initial validation
        this.validateAll();

        // Watch for changes
        this.$watch('settings', () => {
            this.validateAll();
        }, { deep: true });
    },

    validateRefreshInterval() {
        const interval = this.settings.refreshInterval;

        if (!interval || isNaN(interval)) {
            this.validationErrors.refreshInterval = 'Refresh interval is required';
            return false;
        }

        if (interval < 5) {
            this.validationErrors.refreshInterval = 'Minimum interval is 5 seconds';
            return false;
        }

        if (interval > 300) {
            this.validationErrors.refreshInterval = 'Maximum interval is 300 seconds';
            return false;
        }

        delete this.validationErrors.refreshInterval;
        return true;
    },

    validateAll() {
        this.validationErrors = {};
        this.validateRefreshInterval();
    },

    saveSettings() {
        // Validate before saving
        this.validateAll();

        if (!this.isValid) {
            this.showToast('Please fix validation errors before saving', 'error');
            return;
        }

        try {
            // Update store
            Object.assign(this.$store.settings, this.settings);
            this.$store.settings.saveSettings();

            // Update original settings to track changes
            this.originalSettings = { ...this.settings };

            // Trigger refresh interval change if needed
            document.dispatchEvent(new CustomEvent('refresh-interval-changed'));

            // Show success message
            this.showToast('Settings saved successfully', 'success');

            // Log debug mode change
            if (this.settings.debugMode) {
                console.log('[Settings] Debug mode enabled');
            }
        } catch (error) {
            console.error('Failed to save settings:', error);
            this.showToast('Failed to save settings', 'error');
        }
    },

    resetSettings() {
        if (!confirm('Are you sure you want to reset all settings to defaults?')) {
            return;
        }

        this.settings = {
            refreshInterval: 15,
            showConfigWarning: true,
            theme: 'dark',
            accountStrategy: 'hybrid',
            autoRefreshAccounts: true,
            debugMode: false,
            showTimestamps: true
        };

        this.validateAll();
        this.showToast('Settings reset to defaults (not saved yet)', 'info');
    },

    showToast(message, type = 'info') {
        if (this.$store && this.$store.global) {
            this.$store.global.showToast(message, type);
        }
    }
});
