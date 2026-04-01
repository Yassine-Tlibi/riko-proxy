/**
 * Kiro Gateway - Settings Store
 */

document.addEventListener('alpine:init', () => {
    Alpine.store('settings', {
        // Settings
        refreshInterval: 15,
        showConfigWarning: true,
        theme: 'dark',

        // Load settings from localStorage
        init() {
            const saved = localStorage.getItem('kiro_settings');
            if (saved) {
                try {
                    const settings = JSON.parse(saved);
                    Object.assign(this, settings);
                } catch (e) {
                    console.error('Failed to load settings:', e);
                }
            }
        },

        // Save settings to localStorage
        saveSettings(silent = false) {
            const settings = {
                refreshInterval: this.refreshInterval,
                showConfigWarning: this.showConfigWarning,
                theme: this.theme
            };

            localStorage.setItem('kiro_settings', JSON.stringify(settings));

            if (!silent) {
                Alpine.store('global').showToast('Settings saved', 'success');
            }
        }
    });
});
