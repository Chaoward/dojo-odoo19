/** @odoo-module **/
import { Component, proxy, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class KioskAdminApp extends Component {
    static template = "dojo_kiosk.KioskAdminApp";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({
            kiosks: [],
            search: "",
            page: 0,
            pageSize: 15,
            loading: true,
            showLaunchModal: false,
        });
        onMounted(() => this.loadKiosks());
    }

    async loadKiosks() {
        this.state.page = 0;
        this.state.loading = true;
        try {
            this.state.kiosks = await this.orm.searchRead(
                "dojo.kiosk.config",
                [],
                ["id", "name", "kiosk_url", "theme_mode", "active"],
                { order: "name" }
            );
        } finally {
            this.state.loading = false;
        }
    }

    get filteredKiosks() {
        const q = this.state.search.toLowerCase().trim();
        if (!q) return this.state.kiosks;
        return this.state.kiosks.filter(k => k.name.toLowerCase().includes(q));
    }

    get pagedKiosks() {
        const { page, pageSize } = this.state;
        return this.filteredKiosks.slice(page * pageSize, (page + 1) * pageSize);
    }

    get totalPages() {
        return Math.max(1, Math.ceil(this.filteredKiosks.length / this.state.pageSize));
    }

    get paginationLabel() {
        const total = this.filteredKiosks.length;
        if (!total) return "0";
        const { page, pageSize } = this.state;
        const start = page * pageSize + 1;
        const end = Math.min((page + 1) * pageSize, total);
        return `${start}-${end} / ${total}`;
    }

    onSearchInput(ev) {
        this.state.search = ev.target.value;
        this.state.page = 0;
    }

    prevPage() {
        if (this.state.page > 0) this.state.page--;
    }

    nextPage() {
        if (this.state.page < this.totalPages - 1) this.state.page++;
    }

    openNew() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "dojo.kiosk.config",
            views: [[false, "form"]],
            target: "current",
        });
    }

    openRecord(kiosk) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "dojo.kiosk.config",
            res_id: kiosk.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    launchKiosk(kiosk) {
        if (!kiosk.kiosk_url) return;
        this.action.doAction({
            type: "ir.actions.act_url",
            url: kiosk.kiosk_url,
            target: "new",
        });
    }

    openLaunchModal() {
        this.state.showLaunchModal = true;
    }

    closeLaunchModal() {
        this.state.showLaunchModal = false;
    }

    logout() {
        window.location.href = "/web/session/logout";
    }
}

registry.category("actions").add("dojo_kiosk.KioskAdminApp", KioskAdminApp);
