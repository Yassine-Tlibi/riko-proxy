/**
 * Kiro Gateway - Accounts Component
 */

window.Components = window.Components || {};

window.Components.accounts = () => ({
        // Loading state
        loading: false,

        // Account status data
        status: {
            total: 0,
            enabled: 0,
            invalid: 0,
            available: 0,
            strategy: 'hybrid',
            accounts: []
        },

        // Accounts list
        accounts: [],

        // API key
        apiKey: '',

        // Update interval
        updateInterval: null,

        // Add Account Modal
        showAddAccountModal: false,
        addMode: 'manual',
        showManualForm: false,
        showCliForm: false,
        addingAccount: false,
        addAccountError: '',

        manualForm: {
            refreshToken: '',
            email: '',
            profileArn: '',
            region: 'us-east-1'
        },

        cliForm: {
            dbPath: '~/.local/share/kiro-cli/data.sqlite3'
        },

        // Auto-scan state
        scanningAccounts: false,
        scannedAccounts: [],
        selectedScannedIndexes: [],
        importingAccounts: false,

        // Initialize
        init() {
            console.log('Multi-Account Manager initializing...');

            // Get API key
            this.apiKey = localStorage.getItem('kiro_api_key');
            if (!this.apiKey) {
                this.apiKey = prompt('Enter your PROXY_API_KEY:');
                if (this.apiKey) {
                    localStorage.setItem('kiro_api_key', this.apiKey);
                }
            }

            // Load initial data with delay to prevent blocking
            setTimeout(() => {
                this.loadAccountStatus();
            }, 100);

            // Set up auto-refresh (30 seconds)
            this.updateInterval = setInterval(() => {
                if (!document.hidden && !this.showAddAccountModal) {
                    this.loadAccountStatus();
                }
            }, 30000);
        },

        // Load account status from API
        async loadAccountStatus() {
            if (this.loading) return;

            this.loading = true;

            try {
                const response = await fetch('/api/v1/accounts/status', {
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

                    // Multi-account might not be enabled
                    if (response.status === 404) {
                        this.showToast('Multi-account mode is not enabled', 'info');
                        this.status = {
                            total: 0,
                            enabled: 0,
                            invalid: 0,
                            available: 0,
                            strategy: 'N/A',
                            accounts: []
                        };
                        this.accounts = [];
                        return;
                    }

                    throw new Error(`HTTP ${response.status}`);
                }

                const data = await response.json();
                this.status = data;
                this.accounts = data.accounts || [];

                console.log('Account status loaded:', data);
            } catch (error) {
                console.error('Failed to load account status:', error);
                this.showToast(`Failed to load accounts: ${error.message}`, 'error');
            } finally {
                this.loading = false;
            }
        },

        // Scan for Kiro IDE accounts on this machine
        async scanForAccounts() {
            this.scanningAccounts = true;
            this.addAccountError = '';
            this.scannedAccounts = [];
            this.selectedScannedIndexes = [];

            try {
                const response = await fetch('/api/v1/accounts/scan', {
                    headers: {
                        'Authorization': `Bearer ${this.apiKey}`
                    }
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.detail || 'Failed to scan for accounts');
                }

                this.scannedAccounts = data.accounts || [];

                if (this.scannedAccounts.length === 0) {
                    this.showToast('No Kiro IDE accounts found in ~/.aws/sso/cache/', 'info');
                } else {
                    // Auto-select all non-expired accounts
                    this.selectedScannedIndexes = this.scannedAccounts
                        .map((account, index) => (!account.is_expired ? index : -1))
                        .filter(index => index !== -1);

                    this.showToast(`Found ${this.scannedAccounts.length} account(s)`, 'success');
                }

            } catch (error) {
                console.error('Failed to scan for accounts:', error);
                this.addAccountError = error.message;
                this.showToast(error.message, 'error');
            } finally {
                this.scanningAccounts = false;
            }
        },

        // Import selected scanned accounts via bulk endpoint
        async importScannedAccounts() {
            if (this.selectedScannedIndexes.length === 0) {
                this.addAccountError = 'No accounts selected';
                return;
            }

            this.importingAccounts = true;
            this.addAccountError = '';

            const selectedAccounts = this.selectedScannedIndexes.map(
                index => this.scannedAccounts[index]
            );

            try {
                const response = await fetch('/api/v1/accounts/add/scan', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${this.apiKey}`
                    },
                    body: JSON.stringify({ accounts: selectedAccounts })
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.detail || 'Failed to import accounts');
                }

                const importedCount = data.imported || 0;
                const failedCount = data.failed || 0;

                if (failedCount > 0) {
                    this.showToast(`Imported ${importedCount} account(s), ${failedCount} failed`, 'info');
                } else {
                    this.showToast(`Successfully imported ${importedCount} account(s)`, 'success');
                }

                // Reset scan state and close modal
                this.scannedAccounts = [];
                this.selectedScannedIndexes = [];
                this.showAddAccountModal = false;
                await this.loadAccountStatus();

            } catch (error) {
                console.error('Failed to import scanned accounts:', error);
                this.addAccountError = error.message;
                this.showToast(error.message, 'error');
            } finally {
                this.importingAccounts = false;
            }
        },

        // Toggle selection of a scanned account by index
        toggleScanSelection(index) {
            const pos = this.selectedScannedIndexes.indexOf(index);
            if (pos === -1) {
                this.selectedScannedIndexes.push(index);
            } else {
                this.selectedScannedIndexes.splice(pos, 1);
            }
        },

        // Select all scanned accounts
        selectAllScanned() {
            this.selectedScannedIndexes = this.scannedAccounts.map((_, i) => i);
        },

        // Deselect all scanned accounts
        deselectAllScanned() {
            this.selectedScannedIndexes = [];
        },

        // Add account manually
        async addAccountManual() {
            if (!this.manualForm.refreshToken) {
                this.addAccountError = 'Refresh token is required';
                return;
            }

            this.addingAccount = true;
            this.addAccountError = '';

            try {
                const response = await fetch('/api/v1/accounts/add/manual', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${this.apiKey}`
                    },
                    body: JSON.stringify({
                        refresh_token: this.manualForm.refreshToken,
                        email: this.manualForm.email || null,
                        profile_arn: this.manualForm.profileArn || null,
                        region: this.manualForm.region
                    })
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.detail || 'Failed to add account');
                }

                // Success!
                this.showToast('Account added successfully!', 'success');

                // Reset form
                this.manualForm = {
                    refreshToken: '',
                    email: '',
                    profileArn: '',
                    region: 'us-east-1'
                };

                // Close modal and refresh
                this.showAddAccountModal = false;
                this.showManualForm = false;
                await this.loadAccountStatus();

            } catch (error) {
                console.error('Failed to add account:', error);
                this.addAccountError = error.message;
            } finally {
                this.addingAccount = false;
            }
        },

        // Add account from kiro-cli
        async addAccountCli() {
            if (!this.cliForm.dbPath) {
                this.addAccountError = 'Database path is required';
                return;
            }

            this.addingAccount = true;
            this.addAccountError = '';

            try {
                const response = await fetch('/api/v1/accounts/add/cli', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${this.apiKey}`
                    },
                    body: JSON.stringify({
                        db_path: this.cliForm.dbPath
                    })
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.detail || 'Failed to import account');
                }

                // Success!
                this.showToast('Account imported successfully!', 'success');

                // Reset form
                this.cliForm = {
                    dbPath: '~/.local/share/kiro-cli/data.sqlite3'
                };

                // Close modal and refresh
                this.showAddAccountModal = false;
                this.showCliForm = false;
                await this.loadAccountStatus();

            } catch (error) {
                console.error('Failed to import account:', error);
                this.addAccountError = error.message;
            } finally {
                this.addingAccount = false;
            }
        },

        // Remove account
        async removeAccount(email) {
            if (!confirm(`Are you sure you want to remove account ${email}?`)) {
                return;
            }

            try {
                const response = await fetch('/api/v1/accounts/remove', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${this.apiKey}`
                    },
                    body: JSON.stringify({ email })
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.detail || 'Failed to remove account');
                }

                this.showToast('Account removed successfully', 'success');
                await this.loadAccountStatus();

            } catch (error) {
                console.error('Failed to remove account:', error);
                this.showToast(`Failed to remove account: ${error.message}`, 'error');
            }
        },

        // Toggle account enabled/disabled
        async toggleAccount(email, enabled) {
            try {
                const response = await fetch('/api/v1/accounts/toggle', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${this.apiKey}`
                    },
                    body: JSON.stringify({ email, enabled })
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.detail || 'Failed to toggle account');
                }

                this.showToast(`Account ${enabled ? 'enabled' : 'disabled'} successfully`, 'success');
                await this.loadAccountStatus();

            } catch (error) {
                console.error('Failed to toggle account:', error);
                this.showToast(`Failed to toggle account: ${error.message}`, 'error');
            }
        },

        // Format timestamp
        formatTimestamp(timestamp) {
            if (!timestamp) return 'Never';

            const date = new Date(timestamp);
            const now = new Date();
            const diffMs = now - date;
            const diffMins = Math.floor(diffMs / 60000);
            const diffHours = Math.floor(diffMs / 3600000);
            const diffDays = Math.floor(diffMs / 86400000);

            if (diffMins < 1) return 'Just now';
            if (diffMins < 60) return `${diffMins}m ago`;
            if (diffHours < 24) return `${diffHours}h ago`;
            if (diffDays < 7) return `${diffDays}d ago`;

            return date.toLocaleDateString();
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
        }
    });

