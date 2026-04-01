/**
 * Kiro Gateway - Models Component
 */

window.Components = window.Components || {};

window.Components.models = () => ({
    models: [],
    loading: false,
    searchQuery: '',

    init() {
        this.loadModels();
    },

    async loadModels() {
        this.loading = true;
        await this.$store.data.fetchModels();
        this.models = this.$store.data.models;
        this.loading = false;
    },

    get filteredModels() {
        if (!this.searchQuery) return this.models;

        const query = this.searchQuery.toLowerCase();
        return this.models.filter(model =>
            model.id.toLowerCase().includes(query)
        );
    }
});
