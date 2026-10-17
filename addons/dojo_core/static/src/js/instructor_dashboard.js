/** @odoo-module **/

import { Component, proxy, onWillStart, onMounted, signal } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { DojoVoiceAssistant } from "@ai_assistant/js/voice_assistant";
import { MiniCalendar } from "@dojo_core/js/mini_calendar";

class InstructorDashboard extends Component {
    static template = "dojo_core.InstructorDashboard";
    static components = { DojoVoiceAssistant, MiniCalendar };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.rootRef = signal.ref();

        const _pad = n => String(n).padStart(2, "0");
        const _now = new Date();
        const _todayStr = `${_now.getFullYear()}-${_pad(_now.getMonth() + 1)}-${_pad(_now.getDate())}`;
        this.state = proxy({
            loading: true,
            profile: null,
            sessionsToday: [],
            upcomingSessions: [],
            todos: [],
            kiosks: [],
            recentStudents: [],
            studentPage: 0,
            // calendar day-view panel
            selectedDate: _todayStr,
        });

        onWillStart(() => this._loadData());

        onMounted(() => {
            const el = this.rootRef.el;
            if (!el) return;
            let node = el.parentElement;
            while (node && node !== document.body) {
                const computed = getComputedStyle(node);
                if (computed.overflow === "hidden" || computed.overflowY === "hidden") {
                    node.style.overflowY = "auto";
                }
                node = node.parentElement;
            }
        });
    }

    async _loadData() {
        const pad = (n) => String(n).padStart(2, "0");
        const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
        const now = new Date();
        const today = iso(now);
        const tomorrow = iso(new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1));
        const twoWeeks = iso(new Date(now.getFullYear(), now.getMonth(), now.getDate() + 14));

        // Server resolves the current user — no client-side UID needed
        const profile = await this.orm.call(
            "dojo.instructor.profile", "get_my_profile_data", []
        );

        if (!profile) {
            if (user.isAdmin) {
                this.action.doAction("dojo_core.action_admin_dashboard_client", { clearBreadcrumbs: true });
                return;
            }
            this.state.loading = false;
            return;
        }

        this.state.profile = profile;
        this.state.recentStudents = (profile && profile.recent_students) || [];
        this.state.studentPage = 0;

        const [sessionsToday, upcomingSessions, todos, kiosks] = await Promise.all([
            this.orm.searchRead(
                "dojo.class.session",
                [
                    ["instructor_profile_id", "=", profile.id],
                    ["start_datetime", ">=", today + " 00:00:00"],
                    ["start_datetime", "<=", today + " 23:59:59"],
                ],
                ["template_id", "start_datetime", "end_datetime",
                    "capacity", "seats_taken", "state"],
                { order: "start_datetime asc" }
            ),
            this.orm.searchRead(
                "dojo.class.session",
                [
                    ["instructor_profile_id", "=", profile.id],
                    ["start_datetime", ">=", tomorrow + " 00:00:00"],
                    ["start_datetime", "<=", twoWeeks + " 23:59:59"],
                ],
                ["template_id", "start_datetime", "capacity", "seats_taken", "state"],
                { order: "start_datetime asc" }
            ),
            this.orm.searchRead(
                "project.task",
                [
                    ["user_ids", "in", [profile.user_id]],
                    ["stage_id.fold", "=", false],
                ],
                ["name", "project_id", "date_deadline", "priority", "stage_id"],
                { order: "date_deadline asc", limit: 25 }
            ),
            this.orm.searchRead(
                "dojo.kiosk.config",
                [["active", "=", true]],
                ["name", "kiosk_url"],
                { order: "name asc" }
            ).catch(() => []),
        ]);

        this.state.sessionsToday = sessionsToday;
        this.state.upcomingSessions = upcomingSessions;
        this.state.todos = todos;
        this.state.kiosks = kiosks;
        this.state.loading = false;
    }

    /** "2025-03-15 09:00:00" (UTC) → "Mar 15 · 9:00 AM" local */
    fmtDt(dtStr) {
        if (!dtStr) return "—";
        const d = new Date(dtStr.replace(" ", "T") + "Z");
        return d.toLocaleString(undefined, {
            month: "short", day: "numeric",
            hour: "numeric", minute: "2-digit",
        });
    }

    /** "2025-03-15" or "2025-03-15 00:00:00" → "Mar 15, 2025" */
    fmtDate(dateStr) {
        if (!dateStr) return "—";
        const [y, m, d] = dateStr.slice(0, 10).split("-").map(Number);
        return new Date(y, m - 1, d).toLocaleDateString(undefined, {
            month: "short", day: "numeric", year: "numeric",
        });
    }

    /** "2025-03-15 09:00:00" (UTC) → "9:00 AM" local time only */
    fmtTime(dtStr) {
        if (!dtStr) return "—";
        const d = new Date(dtStr.replace(" ", "T") + "Z");
        return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
    }

    /** Today's greeting */
    get greeting() {
        const h = new Date().getHours();
        if (h < 12) return "Good morning";
        if (h < 17) return "Good afternoon";
        return "Good evening";
    }

    /** Today's display date */
    get todayLabel() {
        return new Date().toLocaleDateString(undefined, {
            weekday: "long", month: "long", day: "numeric", year: "numeric",
        });
    }

    /** Fill rate as integer 0-100 */
    fillPct(s) { return s.capacity ? Math.round((s.seats_taken / s.capacity) * 100) : 0; }

    stateBadgeClass(s) {
        return {
            draft: "o_di_badge_secondary",
            open: "o_di_badge_success",
            done: "o_di_badge_primary",
            cancelled: "o_di_badge_danger",
        }[s] || "o_di_badge_secondary";
    }

    stateLabel(s) {
        return { draft: "Draft", open: "Open", done: "Done", cancelled: "Cancelled" }[s] || s;
    }

    // ── Student carousel ──────────────────────────────────────────────
    static STUDENT_PAGE_SIZE = 6;

    get visibleStudents() {
        const ps = InstructorDashboard.STUDENT_PAGE_SIZE;
        return this.state.recentStudents.slice(
            this.state.studentPage * ps,
            (this.state.studentPage + 1) * ps
        );
    }

    get totalStudentPages() {
        return Math.max(
            1,
            Math.ceil(this.state.recentStudents.length / InstructorDashboard.STUDENT_PAGE_SIZE)
        );
    }

    prevStudentPage() {
        if (this.state.studentPage > 0) this.state.studentPage--;
    }

    nextStudentPage() {
        if (this.state.studentPage < this.totalStudentPages - 1) this.state.studentPage++;
    }

    openStudentProfile(memberId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "dojo.member",
            res_id: memberId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openTodaysClasses() { this.action.doAction("dojo_core.action_my_sessions_today"); }
    openMyStudents() { this.action.doAction("dojo_core.action_my_students"); }
    openCalendar() { this.action.doAction("dojo_core.action_my_sessions_calendar"); }
    openTodos() { this.action.doAction("dojo_core.action_my_todos"); }

    onDayClick(dateStr) {
        this.state.selectedDate = dateStr;
    }

    get selectedDaySessions() {
        const date = this.state.selectedDate;
        if (!date) return [];
        const all = [...this.state.sessionsToday, ...this.state.upcomingSessions];
        return all.filter(s => s.start_datetime && s.start_datetime.slice(0, 10) === date);
    }

    get selectedDateLabel() {
        const d = this.state.selectedDate;
        if (!d) return "";
        const [y, m, day] = d.split("-").map(Number);
        return new Date(y, m - 1, day).toLocaleDateString(undefined, {
            weekday: "short", month: "long", day: "numeric",
        });
    }

    /** Dates (YYYY-MM-DD) of all loaded sessions for the mini calendar dots */
    get calendarSessionDates() {
        const dates = new Set();
        const extractDate = dt => dt ? dt.slice(0, 10) : null;
        for (const s of this.state.sessionsToday) {
            const d = extractDate(s.start_datetime);
            if (d) dates.add(d);
        }
        for (const s of this.state.upcomingSessions) {
            const d = extractDate(s.start_datetime);
            if (d) dates.add(d);
        }
        return [...dates];
    }
    openSessionRecord(id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "dojo.class.session",
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openKiosk() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Kiosks",
            res_model: "dojo.kiosk.config",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
        });
    }
    launchKioskUrl(url) {
        if (url) window.open(url, "_blank");
    }

    pct(rate) {
        if (rate === undefined || rate === null) return "—";
        return Math.round(rate) + "%";
    }

    async _reload() {
        this.state.loading = true;
        await this._loadData();
    }

    async openQuickAttendance(sessionId) {
        // Pre-create the wizard server-side via orm.call so default_get fires
        // with default_session_id in context and persists all enrolled students
        // as real DB line records. The dialog only sends WRITE commands after
        // that — member_id is always set.
        const wizardId = await this.orm.call(
            "dojo.attendance.quick.wizard",
            "create",
            [{}],
            { context: { default_session_id: sessionId } },
        );
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Mark Attendance",
            res_model: "dojo.attendance.quick.wizard",
            res_id: wizardId,
            view_mode: "form",
            views: [[false, "form"]],
            target: "new",
        }, {
            onClose: () => this._loadData(),
        });
    }
}

registry.category("actions").add("dojo_instructor_dashboard", InstructorDashboard);
