/** @odoo-module **/
import { Component, proxy } from "@odoo/owl";

export class MiniCalendar extends Component {
    static template = "dojo_core.MiniCalendar";
    static props = {
        sessionDates: { type: Array, optional: true },
        selectedDate: { type: String, optional: true },
        onNavigateCalendar: { type: Function, optional: true },
        onDayClick: { type: Function, optional: true },
    };
    static defaultProps = {
        sessionDates: [],
    };

    setup() {
        const now = new Date();
        this.state = proxy({
            year: now.getFullYear(),
            month: now.getMonth(), // 0-indexed
        });
    }

    _isoDate(d) {
        const pad = n => String(n).padStart(2, "0");
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    }

    get monthName() {
        return new Date(this.state.year, this.state.month, 1)
            .toLocaleDateString(undefined, { month: "long", year: "numeric" });
    }

    get isCurrentMonth() {
        const now = new Date();
        return this.state.year === now.getFullYear() && this.state.month === now.getMonth();
    }

    get calendarDays() {
        const { year, month } = this.state;
        const firstDay = new Date(year, month, 1);
        const lastDay = new Date(year, month + 1, 0);
        const sessionSet = new Set(this.props.sessionDates || []);
        const todayStr = this._isoDate(new Date());
        const selectedStr = this.props.selectedDate || "";
        const startDow = firstDay.getDay(); // 0 = Sunday

        const days = [];

        // Leading padding — days from previous month
        for (let day = 1 - startDow; day <= 0; day++) {
            const d = new Date(year, month, day);
            const dateStr = this._isoDate(d);
            days.push({
                dateStr,
                dayNum: d.getDate(),
                inMonth: false,
                isToday: false,
                isSelected: false,
                hasSession: sessionSet.has(dateStr),
            });
        }

        // Current month days
        for (let day = 1; day <= lastDay.getDate(); day++) {
            const d = new Date(year, month, day);
            const dateStr = this._isoDate(d);
            days.push({
                dateStr,
                dayNum: day,
                inMonth: true,
                isToday: dateStr === todayStr,
                isSelected: dateStr === selectedStr,
                hasSession: sessionSet.has(dateStr),
            });
        }

        // Trailing padding — days from next month
        const totalCells = Math.ceil(days.length / 7) * 7;
        let nextDay = 1;
        while (days.length < totalCells) {
            const d = new Date(year, month + 1, nextDay++);
            const dateStr = this._isoDate(d);
            days.push({
                dateStr,
                dayNum: d.getDate(),
                inMonth: false,
                isToday: false,
                isSelected: false,
                hasSession: sessionSet.has(dateStr),
            });
        }

        return days;
    }

    clickDay(day) {
        if (!day.inMonth) return;
        if (this.props.onDayClick) {
            this.props.onDayClick(day.dateStr);
        }
    }

    prevMonth() {
        if (this.state.month === 0) {
            this.state.year--;
            this.state.month = 11;
        } else {
            this.state.month--;
        }
    }

    nextMonth() {
        if (this.state.month === 11) {
            this.state.year++;
            this.state.month = 0;
        } else {
            this.state.month++;
        }
    }

    goToToday() {
        const now = new Date();
        this.state.year = now.getFullYear();
        this.state.month = now.getMonth();
    }

    navigateCalendar() {
        if (this.props.onNavigateCalendar) {
            this.props.onNavigateCalendar();
        }
    }
}
