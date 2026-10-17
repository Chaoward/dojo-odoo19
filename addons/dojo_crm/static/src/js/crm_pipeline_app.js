/** @odoo-module **/
/**
 * crm_pipeline_app.js — Custom CRM Pipeline Board
 *
 * A full-replacement OWL client action for the dojo CRM pipeline.
 * Registered as the ir.actions.client tag "dojo_crm.CrmPipelineApp".
 *
 * Components (all defined in this file):
 *   CrmPipelineApp      — root client action; owns all state
 *   KpiHeader           — 4-cell KPI bar
 *   FilterChipsBar      — 5 quick-filter chips
 *   SearchBar           — text search input
 *   BulkActionBar       — shown when ≥ 1 leads are selected
 *   StageColumn         — one kanban column per stage
 *   LeadCard            — compact lead tile inside a column
 *   QuickCreateForm     — inline "new lead" form inside the New column
 *   LeadDetailModal     — full-screen centered modal for lead details
 *   BookTrialModal      — custom Book Trial flow
 *   BulkMoveModal       — bulk: move to stage
 *   BulkAssignModal     — bulk: assign salesperson
 *   BulkNoteModal       — bulk: internal note
 *   BulkMessageModal    — bulk: send message/email
 *   BulkTagModal        — bulk: tag add/remove
 */

import { Component, proxy, onMounted, onWillUpdateProps, signal, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

// ─── helpers ────────────────────────────────────────────────────────────────

function scoreLabel(score) {
    if (score >= 60) return { text: "Hot", cls: "cpb-score--hot" };
    if (score >= 30) return { text: "Warm", cls: "cpb-score--warm" };
    return { text: "Cold", cls: "cpb-score--cold" };
}

function fmtDate(iso) {
    if (!iso) return "";
    const d = new Date(iso.replace(" ", "T"));
    if (isNaN(d)) return iso;
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function fmtDateTime(iso) {
    if (!iso) return "";
    const d = new Date(iso.replace(" ", "T"));
    if (isNaN(d)) return iso;
    return d.toLocaleString(undefined, {
        month: "short", day: "numeric",
        hour: "2-digit", minute: "2-digit",
    });
}

// ─── KpiHeader ──────────────────────────────────────────────────────────────

class KpiHeader extends Component {
    static template = "dojo_crm.KpiHeader";
    static props = ["kpis"];
}

// ─── FilterChipsBar ──────────────────────────────────────────────────────────

const CHIP_DEFS = [
    { name: "high_score",       label: "High Score",      icon: "fa-star" },
    { name: "trial_attended",   label: "Trial Attended",  icon: "fa-check-circle" },
    { name: "no_show",          label: "No-Show",         icon: "fa-times-circle" },
    { name: "converted",        label: "Converted",       icon: "fa-user-plus" },
    { name: "has_booking_link", label: "Has Booking",     icon: "fa-calendar" },
];

class FilterChipsBar extends Component {
    static template = "dojo_crm.FilterChipsBar";
    static props = ["activeChips", "onToggle"];

    get chips() {
        return CHIP_DEFS.map(c => ({
            ...c,
            active: this.props.activeChips.includes(c.name),
        }));
    }

    toggle(name) {
        this.props.onToggle(name);
    }
}

// ─── SearchBar ───────────────────────────────────────────────────────────────

class SearchBar extends Component {
    static template = "dojo_crm.SearchBar";
    static props = ["query", "onInput", "onClear"];
}

// ─── BulkActionBar ───────────────────────────────────────────────────────────

class BulkActionBar extends Component {
    static template = "dojo_crm.BulkActionBar";
    static props = [
        "selectedCount",
        "onMoveStage", "onAssign", "onNote",
        "onMessage", "onTagUpdate", "onArchive", "onUnarchive", "onClear",
    ];
}

// ─── LeadCard ────────────────────────────────────────────────────────────────

class LeadCard extends Component {
    static template = "dojo_crm.LeadCard";
    static props = [
        "lead",
        "selected",
        "onClick",
        "onSelect",
        "onDragStart",
    ];

    get scoreInfo() { return scoreLabel(this.props.lead.dojo_lead_score); }
    get sessionDate() { return fmtDateTime(this.props.lead.trial_session_dt); }

    handleDragStart(ev) {
        ev.dataTransfer.setData("text/plain", String(this.props.lead.id));
        this.props.onDragStart(this.props.lead.id);
    }
}

// ─── QuickCreateForm ─────────────────────────────────────────────────────────

class QuickCreateForm extends Component {
    static template = "dojo_crm.QuickCreateForm";
    static props = ["stageId", "onSave", "onCancel"];

    setup() {
        this.state = proxy({ name: "Manual Inquiry", contact_name: "", email_from: "", phone: "" });
    }

    async save() {
        if (!this.state.name.trim()) return;
        await this.props.onSave({
            name: this.state.name.trim(),
            contact_name: this.state.contact_name.trim(),
            email_from: this.state.email_from.trim(),
            phone: this.state.phone.trim(),
            stage_id: this.props.stageId,
        });
    }
}

// ─── BookTrialModal ──────────────────────────────────────────────────────────

class BookTrialModal extends Component {
    static template = "dojo_crm.BookTrialModal";
    static props = ["lead", "sessions", "onConfirm", "onCancel"];

    setup() {
        this.state = proxy({ sessionId: null, force: false, saving: false, error: "" });
    }

    onSessionSelectChange(ev) {
        this.state.sessionId = parseInt(ev.target.value, 10) || null;
        this.state.error = "";
    }
    onForceChange(ev) {
        this.state.force = ev.target.checked;
    }

    async confirm() {
        if (!this.state.sessionId) {
            this.state.error = "Please select a session.";
            return;
        }
        this.state.saving = true;
        this.state.error = "";
        try {
            await this.props.onConfirm(this.state.sessionId, this.state.force);
        } catch (e) {
            this.state.error = e.message || "Booking failed.";
            this.state.saving = false;
        }
    }

    get selectedSession() {
        return this.props.sessions.find(s => s.id === this.state.sessionId) || null;
    }
}

// ─── Bulk modal helpers ───────────────────────────────────────────────────────

class BulkMoveModal extends Component {
    static template = "dojo_crm.BulkMoveModal";
    static props = ["stages", "selectedCount", "onConfirm", "onCancel"];

    setup() {
        this.state = proxy({ stageId: null });
    }
    onStageSelectChange(ev) {
        this.state.stageId = parseInt(ev.target.value, 10) || null;
    }
    onConfirmStage() {
        this.props.onConfirm(this.state.stageId);
    }
}

class BulkAssignModal extends Component {
    static template = "dojo_crm.BulkAssignModal";
    static props = ["salespersons", "selectedCount", "onConfirm", "onCancel"];

    setup() {
        this.state = proxy({ userId: null });
    }
    onUserSelectChange(ev) {
        this.state.userId = parseInt(ev.target.value, 10) || null;
    }
    onConfirmAssign() {
        this.props.onConfirm(this.state.userId);
    }
}

class BulkNoteModal extends Component {
    static template = "dojo_crm.BulkNoteModal";
    static props = ["selectedCount", "onConfirm", "onCancel"];

    setup() {
        this.state = proxy({ body: "" });
    }

    onBodyInput(ev) { this.state.body = ev.target.value; }
    onPostNote()    { this.props.onConfirm(this.state.body); }
}

class BulkMessageModal extends Component {
    static template = "dojo_crm.BulkMessageModal";
    static props = ["selectedCount", "onConfirm", "onCancel"];

    setup() {
        this.state = proxy({ subject: "", body: "" });
    }

    onSubjectInput(ev) { this.state.subject = ev.target.value; }
    onBodyInput(ev)    { this.state.body = ev.target.value; }
    onSend()           { this.props.onConfirm(this.state.subject, this.state.body); }
}

class BulkTagModal extends Component {
    static template = "dojo_crm.BulkTagModal";
    static props = ["tagOptions", "selectedCount", "onConfirm", "onCancel"];

    setup() {
        this.state = proxy({ addIds: [], removeIds: [] });
    }

    toggleAdd(tagId) {
        const idx = this.state.addIds.indexOf(tagId);
        if (idx >= 0) this.state.addIds.splice(idx, 1);
        else this.state.addIds.push(tagId);
    }

    toggleRemove(tagId) {
        const idx = this.state.removeIds.indexOf(tagId);
        if (idx >= 0) this.state.removeIds.splice(idx, 1);
        else this.state.removeIds.push(tagId);
    }
}

// ─── StageColumn ─────────────────────────────────────────────────────────────

class StageColumn extends Component {
    static template = "dojo_crm.StageColumn";
    static components = { LeadCard, QuickCreateForm };
    static props = [
        "stage", "leads", "loading", "hasMore",
        "selectedIds",
        "showQuickCreate",
        "onLeadClick", "onLeadSelect", "onLoadMore", "onDrop",
        "onOpenQuickCreate", "onQuickCreateSave", "onQuickCreateCancel",
        "onDragStart",
    ];

    handleDragOver(ev) {
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "move";
    }

    handleDrop(ev) {
        ev.preventDefault();
        const leadId = parseInt(ev.dataTransfer.getData("text/plain"), 10);
        if (leadId) this.props.onDrop(leadId, this.props.stage.id);
    }
}

// ─── LeadDetailModal ─────────────────────────────────────────────────────────

class LeadDetailModal extends Component {
    static template = "dojo_crm.LeadDetailModal";
    static props = [
        "lead", "stages", "salespersons",
        "messagesReloadKey?",
        "onClose", "onStageChange", "onAssign",
        "onBookTrial", "onConvertToMember",
        "onViewMember", "onToggleField", "onDelete",
        "onUploadAvatar",
        "onCall", "onSendEmail", "onSendSms",
        "onSaveDescription",
        "onSendRecap",
        "onSaveContact",
    ];

    get scoreInfo() { return scoreLabel(this.props.lead.dojo_lead_score); }

    setup() {
        this.state = proxy({
            tab: "overview",
            confirmDelete: false,
            notesDraft: this.props.lead.description || "",
            notesStatus: "",  // "saving" | "saved" | ""
            editingContact: false,
            contactDraft: {
                contact_name: this.props.lead.contact_name || "",
                email_from:   this.props.lead.email_from   || "",
                phone:        this.props.lead.phone        || "",
            },
            contactSaving: false,
            messages: [],
            messagesLoaded: false,
            messagesLoading: false,
            expandedMessages: {},
        });
        this.fileInputRef = signal.ref();
        this._notesTimer = null;
        this._lastSavedNotes = this.props.lead.description || "";
        this.orm = useService("orm");
        onWillUpdateProps((nextProps) => {
            // Parent bumps messagesReloadKey after a bulk note/message that
            // touched this open lead. Force a fresh fetch of the chatter.
            if (
                nextProps.messagesReloadKey !== this.props.messagesReloadKey
                && this.state.tab === "messages"
            ) {
                this.state.messagesLoaded = false;
                this.loadMessages();
            } else if (nextProps.messagesReloadKey !== this.props.messagesReloadKey) {
                // Tab not active; just invalidate so it reloads on next open.
                this.state.messagesLoaded = false;
            }
        });
    }

    setTab(t) {
        this.state.tab = t;
        if (t === "messages" && !this.state.messagesLoaded && !this.state.messagesLoading) {
            this.loadMessages();
        }
    }

    async loadMessages() {
        this.state.messagesLoading = true;
        const msgs = await this.orm.call("crm.pipeline.service", "get_lead_messages", [this.props.lead.id]);
        this.state.messages = msgs;
        this.state.expandedMessages = {};  // collapse all on (re)load
        this.state.messagesLoaded = true;
        this.state.messagesLoading = false;
    }

    toggleMessage(msgId) {
        this.state.expandedMessages[msgId] = !this.state.expandedMessages[msgId];
    }

    messagePreview(html) {
        // Strip tags + collapse whitespace for the 1-line collapsed preview.
        if (!html) return "";
        const tmp = document.createElement("div");
        tmp.innerHTML = html;
        return (tmp.textContent || tmp.innerText || "").replace(/\s+/g, " ").trim();
    }

    get sessionDate() { return fmtDateTime(this.props.lead.trial_session_dt); }
    get offerDate()   { return fmtDate(this.props.lead.offer_sent_date); }
    get engageDate()  { return fmtDateTime(this.props.lead.last_engagement_date); }

    requestDelete() { this.state.confirmDelete = true; }
    cancelDelete()  { this.state.confirmDelete = false; }
    async confirmDelete() {
        this.state.confirmDelete = false;
        await this.props.onDelete(this.props.lead.id);
    }

    triggerAvatarUpload() {
        this.fileInputRef.el && this.fileInputRef.el.click();
    }

    async onAvatarFileChange(ev) {
        const file = ev.target.files && ev.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = async (e) => {
            // Strip data URL prefix: 'data:image/jpeg;base64,'
            const b64 = e.target.result.split(",")[1];
            await this.props.onUploadAvatar(this.props.lead.id, b64);
        };
        reader.readAsDataURL(file);
        // Reset so same file can be re-uploaded
        ev.target.value = "";
    }

    // ── Delegated prop-call handlers (OWL 2 can't call props.X in inline arrows) ──
    onStageChangeEv(ev) {
        this.props.onStageChange(this.props.lead.id, parseInt(ev.target.value, 10));
    }
    onAssignEv(ev) {
        this.props.onAssign(this.props.lead.id, parseInt(ev.target.value, 10) || false);
    }
    onToggleTrialAttended(ev) {
        this.props.onToggleField(this.props.lead.id, 'trial_attended', ev.target.checked);
    }

    // ── Communications ──
    callLead()  { this.props.onCall(this.props.lead.id); }
    emailLead() { this.props.onSendEmail(this.props.lead.id); }
    smsLead()   { this.props.onSendSms(this.props.lead.id); }
    sendRecap() { this.props.onSendRecap(this.props.lead.id); }

    // ── Inline contact edit ──
    startEditContact() {
        this.state.contactDraft = {
            contact_name: this.props.lead.contact_name || "",
            email_from:   this.props.lead.email_from   || "",
            phone:        this.props.lead.phone        || "",
        };
        this.state.editingContact = true;
    }
    cancelEditContact() {
        this.state.editingContact = false;
    }
    onContactInput(field, ev) {
        this.state.contactDraft[field] = ev.target.value;
    }
    async saveEditContact() {
        if (this.state.contactSaving) return;
        this.state.contactSaving = true;
        try {
            await this.props.onSaveContact(this.props.lead.id, {
                contact_name: this.state.contactDraft.contact_name,
                email_from:   this.state.contactDraft.email_from,
                phone:        this.state.contactDraft.phone,
            });
            this.state.editingContact = false;
        } finally {
            this.state.contactSaving = false;
        }
    }

    isRecapActivity(act) {
        return act && (act.summary || "").toLowerCase().includes("recap");
    }
    noteMarkup(html) {
        // Return a Markup-like object so t-out renders HTML without escaping
        return owl.markup(html || "");
    }

    // ── Notes (debounced autosave) ──
    onNotesInput(ev) {
        this.state.notesDraft = ev.target.value;
        this.state.notesStatus = "saving";
        if (this._notesTimer) clearTimeout(this._notesTimer);
        this._notesTimer = setTimeout(() => this._flushNotes(), 600);
    }

    async onNotesBlur() {
        if (this._notesTimer) {
            clearTimeout(this._notesTimer);
            this._notesTimer = null;
        }
        await this._flushNotes();
    }

    async _flushNotes() {
        const draft = this.state.notesDraft || "";
        if (draft === this._lastSavedNotes) {
            this.state.notesStatus = "saved";
            return;
        }
        try {
            await this.props.onSaveDescription(this.props.lead.id, draft);
            this._lastSavedNotes = draft;
            this.state.notesStatus = "saved";
        } catch (e) {
            this.state.notesStatus = "";
        }
    }
}

// ─── AutomationsDrawer ──────────────────────────────────────────────────────

class AutomationsDrawer extends Component {
    static template = "dojo_crm.AutomationsDrawer";
    static props = ["automations", "isAdmin", "onClose", "onToggle", "onOpenSettings"];

    onToggleAuto(key, ev) {
        this.props.onToggle(key, ev.target.checked);
    }
}

// ─── TemplatesDrawer ────────────────────────────────────────────────────────

class TemplatesDrawer extends Component {
    static template = "dojo_crm.TemplatesDrawer";
    static props = [
        "templates", "loading", "activeTab",
        "onClose", "onSetTab", "onOpenTemplate", "onOpenList", "onAddCard",
    ];
}

// ─── CrmPipelineApp (root) ────────────────────────────────────────────────────

class CrmPipelineApp extends Component {
    static template = "dojo_crm.CrmPipelineApp";
    static components = {
        KpiHeader, FilterChipsBar, SearchBar, BulkActionBar,
        StageColumn, LeadDetailModal,
        BookTrialModal,
        BulkMoveModal, BulkAssignModal, BulkNoteModal,
        BulkMessageModal, BulkTagModal,
        AutomationsDrawer,
        TemplatesDrawer,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");

        this.state = proxy({
            loading: true,
            stages: [],
            kpis: { total_leads: 0, conversion_rate: 0, trials_this_week: 0, expiring_offers: 0 },
            stageLeads: {},       // { stageId: { leads: [], total: 0, loading: false, offset: 0 } }
            selectedIds: new Set(),
            activeChips: [],
            searchQuery: "",
            detailLead: null,       // full detail payload
            messagesReloadKey: 0,   // bumped to force LeadDetailModal to reload chatter
            quickCreateStageId: null,
            dragLeadId: null,
            sessions: [],
            salespersons: [],
            tagOptions: [],
            currentUser: null,
            // modals
            modal: null,           // null | "bookTrial" | "bulkMove" | "bulkAssign" | "bulkNote" | "bulkMessage" | "bulkTag"
            // automations drawer
            automationsOpen: false,
            automations: [],
            automationsAdmin: false,
            automationsLoading: false,
            // templates drawer
            templatesOpen: false,
            templates: { email: [], sms: [] },
            templatesLoading: false,
            templatesTab: "email",
        });

        onMounted(() => this._bootstrap());
    }

    // ── Bootstrap ────────────────────────────────────────────────────────────

    async _bootstrap() {
        const data = await this.orm.call("crm.pipeline.service", "get_board_data", [
            this.state.activeChips, this.state.searchQuery,
        ]);
        this.state.stages        = data.stages;
        this.state.kpis          = data.kpis;
        this.state.salespersons  = data.salespersons;
        this.state.tagOptions    = data.tag_options;
        this.state.currentUser   = data.current_user;

        // Init per-stage slot
        for (const st of data.stages) {
            this.state.stageLeads[st.id] = { leads: [], total: st.count, loading: false, offset: 0 };
        }

        // Load all columns in parallel (batched first-page fetch)
        await Promise.all(data.stages.map(st => this._loadStageLeads(st.id)));
        this.state.loading = false;
    }

    async _reloadBoard() {
        // Re-fetch stage counts + KPIs without resetting lead payloads
        const data = await this.orm.call("crm.pipeline.service", "get_board_data", [
            this.state.activeChips, this.state.searchQuery,
        ]);
        this.state.kpis   = data.kpis;
        // reset all columns
        for (const st of data.stages) {
            this.state.stageLeads[st.id] = { leads: [], total: st.count, loading: false, offset: 0 };
        }
        await Promise.all(data.stages.map(st => this._loadStageLeads(st.id)));
    }

    // ── Column loading ────────────────────────────────────────────────────────

    async _loadStageLeads(stageId, append = false) {
        const slot = this.state.stageLeads[stageId];
        if (!slot) return;
        slot.loading = true;
        const offset = append ? slot.offset : 0;
        const result = await this.orm.call("crm.pipeline.service", "get_stage_leads", [
            stageId, this.state.activeChips, this.state.searchQuery, offset, 20,
        ]);
        if (append) {
            slot.leads = [...slot.leads, ...result.leads];
        } else {
            slot.leads = result.leads;
        }
        slot.total   = result.total;
        slot.offset  = slot.leads.length;
        slot.loading = false;
    }

    async loadMoreLeads(stageId) {
        await this._loadStageLeads(stageId, true);
    }

    // ── Search & filter ───────────────────────────────────────────────────────

    onSearchInput(query) {
        this.state.searchQuery = query;
        this._reloadBoard();
    }

    onSearchClear() {
        this.state.searchQuery = "";
        this._reloadBoard();
    }

    onToggleChip(name) {
        const idx = this.state.activeChips.indexOf(name);
        if (idx >= 0) this.state.activeChips.splice(idx, 1);
        else this.state.activeChips.push(name);
        this._reloadBoard();
    }

    // ── Lead selection ────────────────────────────────────────────────────────

    onLeadSelect(leadId) {
        const s = this.state.selectedIds;
        if (s.has(leadId)) s.delete(leadId);
        else s.add(leadId);
        // trigger reactivity
        this.state.selectedIds = new Set(s);
    }

    clearSelection() {
        this.state.selectedIds = new Set();
    }

    // ── Lead click → detail panel ──────────────────────────────────────────────

    async onLeadClick(leadId) {
        const detail = await this.orm.call("crm.pipeline.service", "get_lead_detail", [leadId]);
        this.state.detailLead = detail;
    }

    closeDetailPanel() {
        this.state.detailLead = null;
    }

    // ── Quick create ─────────────────────────────────────────────────────────

    openQuickCreate(stageId) {
        this.state.quickCreateStageId = stageId;
    }

    closeQuickCreate() {
        this.state.quickCreateStageId = null;
    }

    async saveQuickCreate(vals) {
        const lead = await this.orm.call("crm.pipeline.service", "create_lead", [vals]);
        const stageId = vals.stage_id;
        const slot = this.state.stageLeads[stageId];
        if (slot) {
            slot.leads = [lead, ...slot.leads];
            slot.total += 1;
        }
        this.state.quickCreateStageId = null;
        this.notification.add("Lead created", { type: "success" });
    }

    // ── Drag & drop ───────────────────────────────────────────────────────────

    onDragStart(leadId) {
        this.state.dragLeadId = leadId;
    }

    async onDrop(leadId, targetStageId) {
        // Find source stage
        let sourceStageId = null;
        for (const [sid, slot] of Object.entries(this.state.stageLeads)) {
            if (slot.leads.find(l => l.id === leadId)) {
                sourceStageId = parseInt(sid, 10);
                break;
            }
        }
        if (!sourceStageId || sourceStageId === targetStageId) return;

        const updated = await this.orm.call("crm.pipeline.service", "move_lead_stage", [leadId, targetStageId]);

        // Remove from source
        const src = this.state.stageLeads[sourceStageId];
        if (src) {
            src.leads = src.leads.filter(l => l.id !== leadId);
            src.total = Math.max(0, src.total - 1);
        }
        // Prepend to target
        const tgt = this.state.stageLeads[targetStageId];
        if (tgt) {
            tgt.leads = [updated, ...tgt.leads];
            tgt.total += 1;
        }
        // Update detail panel if open
        if (this.state.detailLead && this.state.detailLead.id === leadId) {
            this.state.detailLead = { ...this.state.detailLead, ...updated };
        }
    }

    // ── Detail panel mutations ────────────────────────────────────────────────

    async onStageChange(leadId, stageId) {
        const updated = await this.orm.call("crm.pipeline.service", "move_lead_stage", [leadId, stageId]);
        this._patchLead(updated);
        this.state.detailLead = { ...this.state.detailLead, ...updated };
        // full column reload to reposition cards
        await this._reloadBoard();
    }

    async onAssign(leadId, userId) {
        const updated = await this.orm.call("crm.pipeline.service", "assign_salesperson", [leadId, userId]);
        this._patchLead(updated);
        if (this.state.detailLead && this.state.detailLead.id === leadId) {
            this.state.detailLead = { ...this.state.detailLead, ...updated };
        }
    }

    async onToggleField(leadId, field, value) {
        const updated = await this.orm.call("crm.pipeline.service", "update_lead_field", [leadId, field, value]);
        this._patchLead(updated);
        if (this.state.detailLead && this.state.detailLead.id === leadId) {
            this.state.detailLead = { ...this.state.detailLead, ...updated };
        }
    }

    // ── Book Trial ────────────────────────────────────────────────────────────

    async onBookTrial(leadId) {
        if (!this.state.sessions.length) {
            this.state.sessions = await this.orm.call("crm.pipeline.service", "get_available_sessions", []);
        }
        this.state.modal = "bookTrial";
    }

    async confirmBookTrial(sessionId, force) {
        const updated = await this.orm.call("crm.pipeline.service", "book_trial", [
            this.state.detailLead.id, sessionId, force,
        ]);
        this._patchLead(updated);
        if (this.state.detailLead) {
            // refresh full detail
            this.state.detailLead = await this.orm.call("crm.pipeline.service", "get_lead_detail", [updated.id]);
        }
        this.state.modal = null;
        this.notification.add("Trial booked!", { type: "success" });
        // Refresh stage columns for Trial Booked stage
        await this._reloadBoard();
    }

    // ── Convert to Member ─────────────────────────────────────────────────────

    onConvertToMember(leadId) {
        this.action.doAction("dojo_crm.action_dojo_convert_lead_wizard", {
            additionalContext: { default_lead_id: leadId, active_id: leadId },
            onClose: async () => {
                // Refresh the lead detail after the wizard closes
                if (this.state.detailLead && this.state.detailLead.id === leadId) {
                    this.state.detailLead = await this.orm.call(
                        "crm.pipeline.service", "get_lead_detail", [leadId]
                    );
                }
                await this._reloadBoard();
            },
        });
    }

    onViewMember(memberId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Member",
            res_model: "dojo.member",
            res_id: memberId,
            views: [[false, "form"]],
        });
    }

    // ── Bulk actions ──────────────────────────────────────────────────────────

    openBulkModal(type) {
        this.state.modal = type;
    }

    openBulkMoveModal()    { this.state.modal = "bulkMove"; }
    openBulkAssignModal()  { this.state.modal = "bulkAssign"; }
    openBulkNoteModal()    { this.state.modal = "bulkNote"; }
    openBulkMessageModal() { this.state.modal = "bulkMessage"; }
    openBulkTagModal()     { this.state.modal = "bulkTag"; }
    archiveSelected()      { this.confirmBulkArchive(true); }
    unarchiveSelected()    { this.confirmBulkArchive(false); }

    closeModal() {
        this.state.modal = null;
    }

    get selectedIdArray() {
        return Array.from(this.state.selectedIds);
    }

    async confirmBulkMoveStage(stageId) {
        const ids = this.selectedIdArray;
        const cnt = ids.length;
        await this.orm.call("crm.pipeline.service", "bulk_move_stage", [ids, stageId]);
        this.state.modal = null;
        this.clearSelection();
        await this._reloadBoard();
        this.notification.add(`Moved ${cnt} lead(s)`, { type: "success" });
    }

    async confirmBulkAssign(userId) {
        const ids = this.selectedIdArray;
        const cnt = ids.length;
        await this.orm.call("crm.pipeline.service", "bulk_assign_salesperson", [ids, userId]);
        this.state.modal = null;
        this.clearSelection();
        await this._reloadBoard();
        this.notification.add(`Salesperson updated on ${cnt} lead(s)`, { type: "success" });
    }

    async confirmBulkNote(body) {
        const ids = this.selectedIdArray;
        const cnt = ids.length;
        await this.orm.call("crm.pipeline.service", "bulk_post_note", [ids, body]);
        this.state.modal = null;
        // If the open lead detail is one of the bulk targets, force its
        // Messages tab to reload so the new note appears immediately.
        if (this.state.detailLead && ids.includes(this.state.detailLead.id)) {
            this.state.messagesReloadKey += 1;
        }
        this.clearSelection();
        this.notification.add(`Note posted on ${cnt} lead(s)`, { type: "success" });
    }

    async confirmBulkMessage(subject, body) {
        const ids = this.selectedIdArray;
        const cnt = ids.length;
        await this.orm.call("crm.pipeline.service", "bulk_send_message", [ids, body, subject]);
        this.state.modal = null;
        if (this.state.detailLead && ids.includes(this.state.detailLead.id)) {
            this.state.messagesReloadKey += 1;
        }
        this.clearSelection();
        this.notification.add(`Message sent to ${cnt} lead(s)`, { type: "success" });
    }

    async confirmBulkArchive(archive) {
        const ids = this.selectedIdArray;
        const cnt = ids.length;
        await this.orm.call("crm.pipeline.service", "bulk_archive", [ids, archive]);
        this.clearSelection();
        await this._reloadBoard();
        this.notification.add(archive ? `${cnt} lead(s) archived` : `${cnt} lead(s) restored`, { type: "success" });
    }

    async confirmBulkTags(addIds, removeIds) {
        const ids = this.selectedIdArray;
        const cnt = ids.length;
        await this.orm.call("crm.pipeline.service", "bulk_update_tags", [ids, addIds, removeIds]);
        this.state.modal = null;
        this.clearSelection();
        await this._reloadBoard();
        this.notification.add(`Tags updated on ${cnt} lead(s)`, { type: "success" });
    }

    // ── Delete lead ───────────────────────────────────────────────────────────

    async onDeleteLead(leadId) {
        await this.orm.call("crm.pipeline.service", "delete_lead", [leadId]);
        // Remove from all stage slots
        for (const slot of Object.values(this.state.stageLeads)) {
            const idx = slot.leads.findIndex(l => l.id === leadId);
            if (idx >= 0) {
                slot.leads.splice(idx, 1);
                slot.total = Math.max(0, slot.total - 1);
            }
        }
        this.state.detailLead = null;
        this.notification.add("Lead deleted", { type: "info" });
    }

    // ── Avatar upload ─────────────────────────────────────────────────────────

    async onUploadAvatar(leadId, imageB64) {
        const updated = await this.orm.call(
            "crm.pipeline.service", "update_partner_avatar", [leadId, imageB64]
        );
        // Update the live detail + board card
        this._patchLead(updated);
        if (this.state.detailLead && this.state.detailLead.id === leadId) {
            this.state.detailLead = updated;
        }
        this.notification.add("Photo updated", { type: "success" });
    }

    // ── Communications: Call / Email / SMS ────────────────────────────────────

    async onCall(leadId) {
        try {
            const result = await this.orm.call(
                "crm.pipeline.service", "start_call", [leadId]
            );
            if (result && result.mode === "twilio") {
                this.notification.add("Calling " + (result.phone || "") + "…", { type: "info" });
            } else if (result && result.mode === "tel" && result.phone) {
                window.location.href = "tel:" + result.phone;
            }
        } catch (e) {
            this.notification.add(e.message || "Could not start call", { type: "danger" });
        }
    }

    async onSendEmail(leadId) {
        const action = await this.orm.call(
            "crm.pipeline.service", "open_email_composer", [leadId]
        );
        await this.action.doAction(action, {
            onClose: async () => {
                if (this.state.detailLead && this.state.detailLead.id === leadId) {
                    this.state.detailLead = await this.orm.call(
                        "crm.pipeline.service", "get_lead_detail", [leadId]
                    );
                }
            },
        });
    }

    async onSendSms(leadId) {
        const action = await this.orm.call(
            "crm.pipeline.service", "open_sms_composer", [leadId]
        );
        await this.action.doAction(action, {
            onClose: async () => {
                if (this.state.detailLead && this.state.detailLead.id === leadId) {
                    this.state.detailLead = await this.orm.call(
                        "crm.pipeline.service", "get_lead_detail", [leadId]
                    );
                }
            },
        });
    }

    async onSendRecap(leadId) {
        const action = await this.orm.call(
            "crm.pipeline.service", "send_recap_email", [leadId]
        );
        const recapActivityId = (action.context || {}).mark_recap_activity_id || null;
        await this.action.doAction(action, {
            onClose: async (info) => {
                // If the user actually sent the message (not just cancelled),
                // mark the recap activity as done.
                if (recapActivityId && info && info.special !== true) {
                    try {
                        await this.orm.call(
                            "crm.pipeline.service", "complete_recap_activity", [recapActivityId]
                        );
                        this.notification.add("Recap sent — To-Do marked done", { type: "success" });
                    } catch (e) {
                        // non-fatal
                    }
                }
                if (this.state.detailLead && this.state.detailLead.id === leadId) {
                    this.state.detailLead = await this.orm.call(
                        "crm.pipeline.service", "get_lead_detail", [leadId]
                    );
                }
            },
        });
    }

    // ── Notes (description autosave) ──────────────────────────────────────────


    async onSaveDescription(leadId, html) {
        const result = await this.orm.call(
            "crm.pipeline.service", "update_lead_description", [leadId, html]
        );
        if (this.state.detailLead && this.state.detailLead.id === leadId) {
            this.state.detailLead = {
                ...this.state.detailLead,
                description: (result && result.description) || html,
            };
        }
    }

    async onSaveContact(leadId, vals) {
        const result = await this.orm.call(
            "crm.pipeline.service", "update_lead_contact", [leadId, vals]
        );
        if (!result || !result.success) return;
        const patch = {
            contact_name: result.contact_name || "",
            email_from:   result.email_from   || "",
            phone:        result.phone        || "",
        };
        if (this.state.detailLead && this.state.detailLead.id === leadId) {
            this.state.detailLead = { ...this.state.detailLead, ...patch };
        }
        // Update the lead in the kanban column too
        for (const stageId of Object.keys(this.state.stageLeads)) {
            const slot = this.state.stageLeads[stageId];
            const idx = slot.leads.findIndex(l => l.id === leadId);
            if (idx >= 0) {
                slot.leads[idx] = { ...slot.leads[idx], ...patch };
            }
        }
    }

    // ── Automations Drawer ────────────────────────────────────────────────────

    async openAutomations() {
        this.state.automationsOpen = true;
        this.state.automationsLoading = true;
        try {
            const data = await this.orm.call(
                "crm.pipeline.service", "get_crm_automations", []
            );
            this.state.automations      = data.automations || [];
            this.state.automationsAdmin = !!data.is_admin;
        } finally {
            this.state.automationsLoading = false;
        }
    }

    closeAutomations() {
        this.state.automationsOpen = false;
    }

    async onToggleAutomation(key, enabled) {
        try {
            await this.orm.call(
                "crm.pipeline.service", "set_crm_automation", [key, enabled]
            );
            const a = this.state.automations.find(x => x.key === key);
            if (a) a.enabled = enabled;
            this.notification.add(
                (enabled ? "Enabled: " : "Disabled: ") + (a ? a.label : key),
                { type: "success" }
            );
        } catch (e) {
            this.notification.add(e.message || "Could not toggle automation", { type: "danger" });
        }
    }

    openAutomationSettings() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Scheduled Actions",
            res_model: "ir.cron",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
            target: "current",
            domain: [["model_id.model", "=", "crm.lead"]],
        });
    }

    // ── Templates Drawer ──────────────────────────────────────────────────────

    async openTemplates() {
        this.state.templatesOpen = true;
        this.state.templatesLoading = true;
        try {
            const data = await this.orm.call(
                "crm.pipeline.service", "list_templates", []
            );
            this.state.templates = {
                email: (data && data.email) || [],
                sms:   (data && data.sms)   || [],
            };
            // If email is empty but sms has rows, default to sms tab
            if (!this.state.templates.email.length && this.state.templates.sms.length) {
                this.state.templatesTab = "sms";
            }
        } finally {
            this.state.templatesLoading = false;
        }
    }

    closeTemplates() {
        this.state.templatesOpen = false;
    }

    setTemplatesTab(tab) {
        this.state.templatesTab = tab;
    }

    openTemplateForm(model, id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: model,
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
        this.state.templatesOpen = false;
    }

    openTemplateList(model) {
        const name = model === "sms.template" ? "SMS Templates" : "Email Templates";
        this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: model,
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
            target: "current",
            domain: [["model", "=", "crm.lead"]],
        });
        this.state.templatesOpen = false;
    }

    async addTemplateCard(model, id) {
        // Open a Marketing Card create form pre-scoped to crm.lead so the user
        // can build a new card.campaign that will then be linkable from the template.
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "New Marketing Card",
            res_model: "card.campaign",
            view_mode: "form",
            views: [[false, "form"]],
            target: "current",
            context: {
                default_res_model: "crm.lead",
                default_name: "New CRM Card",
            },
        });
        this.state.templatesOpen = false;
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    _patchLead(updated) {
        const stageSlot = this.state.stageLeads[updated.stage_id];
        if (!stageSlot) return;
        const idx = stageSlot.leads.findIndex(l => l.id === updated.id);
        if (idx >= 0) stageSlot.leads[idx] = updated;
    }

    get hasSelection() {
        return this.state.selectedIds.size > 0;
    }

    get selectedCount() {
        return this.state.selectedIds.size;
    }
}

registry.category("actions").add("dojo_crm.CrmPipelineApp", CrmPipelineApp);
