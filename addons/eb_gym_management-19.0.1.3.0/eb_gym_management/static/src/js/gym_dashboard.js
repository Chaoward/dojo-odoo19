/** @odoo-module **/

import {
  Component,
  onWillStart,
  onMounted,
  onWillUnmount,
  useRef,
  useState,
  onPatched,
} from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const THEME = {
  text: "#0b0b0b",
  muted: "#898781",
  grid: "#e1e0d9",
  axis: "#c3c2b7",
  brand: "#2a78d6",
  surface: "#fcfcfb",
};

class GymDashboard extends Component {
  static template = "eb_gym_management.GymDashboard";
  static props = { ...standardActionServiceProps };

  setup() {
    this._t = _t;
    this.orm = useService("orm");
    this.actionService = useService("action");

    const savedRange = this._loadPreference("gym_dashboard_range", "6m");
    const savedTab = this._loadPreference("gym_dashboard_tab", "members");

    this.state = useState({
      data: {},
      activeTab: savedTab,
      dateRange: savedRange,
    });

    this.statusChartRef = useRef("statusChart");
    this.paymentChartRef = useRef("paymentChart");
    this.monthlyMembersChartRef = useRef("monthlyMembersChart");
    this.revenueChartRef = useRef("revenueChart");
    this.planChartRef = useRef("planChart");
    this.assessmentChartRef = useRef("assessmentChart");
    this.dailyAttendanceChartRef = useRef("dailyAttendanceChart");
    this.hourlyChartRef = useRef("hourlyChart");
    this.trainerChartRef = useRef("trainerChart");
    this.staffAttendanceChartRef = useRef("staffAttendanceChart");

    onWillStart(async () => {
      await this.refreshData();
    });

    onMounted(() => {
      this.renderCharts();
      this._onResize = this.resizeCharts.bind(this);
      window.addEventListener("resize", this._onResize);
    });

    onPatched(() => {
      this.renderCharts();
    });

    onWillUnmount(() => {
      if (this._onResize) {
        window.removeEventListener("resize", this._onResize);
      }
      if (this.charts) {
        Object.values(this.charts).forEach((chart) => chart.dispose());
        this.charts = {};
      }
    });
  }

  async refreshData() {
    this.state.data = await this.orm.call(
      "gym.membership",
      "get_dashboard_data",
      [this.state.dateRange],
    );
    if (this.charts) {
      this.renderCharts();
    }
  }

  _loadPreference(key, fallback) {
    try {
      return window.localStorage.getItem(key) || fallback;
    } catch {
      return fallback;
    }
  }

  _savePreference(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch {
      // Ignore storage failures in private mode or restricted browsers.
    }
  }

  switchTab(tab) {
    this.state.activeTab = tab;
    this._savePreference("gym_dashboard_tab", tab);
  }

  getRangeOptions() {
    return [
      { key: "3m", label: _t("3M") },
      { key: "6m", label: _t("6M") },
      { key: "12m", label: _t("12M") },
    ];
  }

  setRange(range) {
    if (range === this.state.dateRange) {
      return;
    }
    this.state.dateRange = range;
    this._savePreference("gym_dashboard_range", range);
    this.refreshData();
  }

  formatCurrency(amount) {
    const symbol = this.state.data.currency_symbol || "";
    const formatted = (amount || 0).toLocaleString();
    return this.state.data.currency_position === "before"
      ? `${symbol}${formatted}`
      : `${formatted} ${symbol}`;
  }

  getMonthStartIso(monthsAgo = 0) {
    const d = new Date();
    d.setDate(1);
    d.setMonth(d.getMonth() - monthsAgo);
    return d.toISOString().slice(0, 10);
  }

  getUpcomingLimit() {
    return 6;
  }

  getUpcomingRecords() {
    return (this.state.data.upcoming_expirations || []).slice(
      0,
      this.getUpcomingLimit(),
    );
  }

  hasMoreUpcoming() {
    return (
      (this.state.data.upcoming_expirations || []).length >
      this.getUpcomingLimit()
    );
  }

  getCheckedInLimit() {
    return 8;
  }

  getCheckedInRecords() {
    return (this.state.data.checked_in_now || []).slice(
      0,
      this.getCheckedInLimit(),
    );
  }

  hasMoreCheckedIn() {
    return (
      (this.state.data.checked_in_now || []).length > this.getCheckedInLimit()
    );
  }

  getAwaitingPlanRecords() {
    return this.state.data.members_awaiting_plan || [];
  }

  hasMoreAwaitingPlan() {
    return (
      (this.state.data.members_awaiting_plan_count || 0) >
      this.getAwaitingPlanRecords().length
    );
  }

  getOnDutyStaffRecords() {
    return this.state.data.on_duty_staff || [];
  }

  _bindClick(chart, handler) {
    chart.off("click");
    chart.on("click", handler);
  }

  _openDomain(resModel, name, domain = []) {
    this.actionService.doAction({
      type: "ir.actions.act_window",
      name,
      res_model: resModel,
      view_mode: "list,form",
      views: [
        [false, "list"],
        [false, "form"],
      ],
      domain,
      context: { create: false },
      target: "current",
    });
  }

  openAction(resModel, name, domain = []) {
    this._openDomain(resModel, name, domain);
  }

  openRecord(resModel, resId) {
    this.actionService.doAction({
      type: "ir.actions.act_window",
      res_model: resModel,
      view_mode: "form",
      res_id: resId,
      views: [[false, "form"]],
      context: { create: false },
      target: "current",
    });
  }

  openExpiringSoon() {
    const weekAhead = new Date();
    weekAhead.setDate(weekAhead.getDate() + 7);
    this._openDomain("gym.membership", _t("Expiring Soon"), [
      ["state", "=", "active"],
      ["end_date", ">=", new Date().toISOString().slice(0, 10)],
      ["end_date", "<=", weekAhead.toISOString().slice(0, 10)],
    ]);
  }

  openPendingPayments() {
    this._openDomain("gym.membership", _t("Pending Payments"), [
      ["state", "!=", "cancelled"],
      ["payment_state", "in", ["not_paid", "partial"]],
    ]);
  }

  openRevenueInvoices() {
    this._openDomain("account.move", _t("Gym Revenue"), [
      ["move_type", "=", "out_invoice"],
      ["state", "=", "posted"],
      [
        "invoice_line_ids.product_id.product_tmpl_id.is_gym_membership_plan",
        "=",
        true,
      ],
      ["invoice_date", ">=", this.getMonthStartIso()],
    ]);
  }

  renderCharts() {
    const data = this.state.data;
    if (!data || Object.keys(data).length === 0) return;
    this.charts = this.charts || {};

    const initChart = (ref, name) => {
      if (ref.el) {
        if (this.charts[name]) {
          this.charts[name].dispose();
        }
        this.charts[name] = echarts.init(ref.el);
        return this.charts[name];
      }
      return null;
    };

    const baseAxis = {
      axisLabel: { color: THEME.muted },
      axisLine: { lineStyle: { color: THEME.axis } },
      splitLine: { lineStyle: { color: THEME.grid } },
    };

    const tooltipBase = {
      backgroundColor: THEME.surface,
      borderColor: THEME.grid,
      borderWidth: 1,
      padding: 10,
      textStyle: { color: THEME.text, fontSize: 12 },
      extraCssText:
        "box-shadow: 0 6px 16px rgba(11,11,11,0.14); border-radius: 8px;",
    };

    if (this.state.activeTab === "members") {
      const statusChart = initChart(this.statusChartRef, "status");
      if (statusChart) {
        const items = data.status_distribution || [];
        statusChart.setOption({
          color: items.map((i) => i.color),
          textStyle: { color: THEME.text },
          tooltip: {
            ...tooltipBase,
            trigger: "item",
            formatter: "{b}: {c} ({d}%)",
          },
          legend: {
            bottom: 0,
            type: "scroll",
            itemWidth: 12,
            itemHeight: 12,
            textStyle: { color: THEME.text },
          },
          series: [
            {
              type: "pie",
              radius: ["45%", "70%"],
              itemStyle: {
                borderRadius: 8,
                borderColor: THEME.surface,
                borderWidth: 2,
              },
              label: { show: false },
              data: items,
            },
          ],
        });
        this._bindClick(statusChart, (params) => {
          const item = params.data || {};
          if (item.state) {
            this._openDomain("gym.membership", _t("Memberships"), [
              ["state", "=", item.state],
            ]);
          }
        });
      }

      const paymentChart = initChart(this.paymentChartRef, "payment");
      if (paymentChart) {
        const items = data.payment_distribution || [];
        paymentChart.setOption({
          color: items.map((i) => i.color),
          textStyle: { color: THEME.text },
          tooltip: {
            ...tooltipBase,
            trigger: "item",
            formatter: "{b}: {c} ({d}%)",
          },
          legend: {
            bottom: 0,
            type: "scroll",
            itemWidth: 12,
            itemHeight: 12,
            textStyle: { color: THEME.text },
          },
          series: [
            {
              type: "pie",
              radius: ["45%", "70%"],
              itemStyle: {
                borderRadius: 8,
                borderColor: THEME.surface,
                borderWidth: 2,
              },
              label: { show: false },
              data: items,
            },
          ],
        });
        this._bindClick(paymentChart, (params) => {
          const item = params.data || {};
          if (item.state) {
            this._openDomain("gym.membership", _t("Memberships"), [
              ["payment_state", "=", item.state],
            ]);
          }
        });
      }

      const monthlyChart = initChart(this.monthlyMembersChartRef, "monthly");
      if (monthlyChart) {
        const series = data.monthly_new_members || [];
        monthlyChart.setOption({
          color: [THEME.brand],
          textStyle: { color: THEME.text },
          tooltip: { ...tooltipBase, trigger: "axis" },
          grid: {
            left: "3%",
            right: "4%",
            bottom: "12%",
            top: "8%",
            containLabel: true,
          },
          xAxis: {
            type: "category",
            data: series.map((i) => i.name),
            axisLabel: { ...baseAxis.axisLabel, interval: 0, rotate: 30 },
            axisLine: baseAxis.axisLine,
          },
          yAxis: { type: "value", minInterval: 1, ...baseAxis },
          series: [
            {
              name: _t("New Members"),
              data: series.map((i) => i.value),
              type: "line",
              smooth: true,
              symbolSize: 6,
              areaStyle: { opacity: 0.12 },
            },
          ],
        });
        this._bindClick(monthlyChart, (params) => {
          const item = series.find((i) => i.name === params.name);
          if (item && item.month_start) {
            const d = new Date(item.month_start);
            const monthEnd = new Date(d.getFullYear(), d.getMonth() + 1, 1)
              .toISOString()
              .slice(0, 10);
            this._openDomain("gym.membership", _t("New Memberships"), [
              ["start_date", ">=", item.month_start],
              ["start_date", "<", monthEnd],
            ]);
          }
        });
      }

      const revenueChart = initChart(this.revenueChartRef, "revenue");
      if (revenueChart) {
        const series = data.revenue_trend || [];
        revenueChart.setOption({
          color: [THEME.brand],
          textStyle: { color: THEME.text },
          tooltip: {
            ...tooltipBase,
            trigger: "axis",
            valueFormatter: (v) => this.formatCurrency(v),
          },
          grid: {
            left: "3%",
            right: "4%",
            bottom: "12%",
            top: "8%",
            containLabel: true,
          },
          xAxis: {
            type: "category",
            data: series.map((i) => i.name),
            axisLabel: { ...baseAxis.axisLabel, interval: 0, rotate: 30 },
            axisLine: baseAxis.axisLine,
          },
          yAxis: { type: "value", ...baseAxis },
          series: [
            {
              name: _t("Revenue"),
              data: series.map((i) => i.value),
              type: "bar",
              barMaxWidth: 32,
              itemStyle: { borderRadius: [4, 4, 0, 0] },
            },
          ],
        });
        this._bindClick(revenueChart, (params) => {
          const item = series.find((i) => i.name === params.name);
          if (item && item.month_start) {
            const d = new Date(item.month_start);
            const monthEnd = new Date(d.getFullYear(), d.getMonth() + 1, 1)
              .toISOString()
              .slice(0, 10);
            this._openDomain("account.move", _t("Revenue"), [
              ["move_type", "=", "out_invoice"],
              ["state", "=", "posted"],
              [
                "invoice_line_ids.product_id.product_tmpl_id.is_gym_membership_plan",
                "=",
                true,
              ],
              ["invoice_date", ">=", item.month_start],
              ["invoice_date", "<", monthEnd],
            ]);
          }
        });
      }

      const planChart = initChart(this.planChartRef, "plan");
      if (planChart) {
        const items = (data.plan_popularity || []).slice().reverse();
        planChart.setOption({
          color: [THEME.brand],
          tooltip: { ...tooltipBase, trigger: "axis" },
          grid: {
            left: "3%",
            right: "8%",
            bottom: "5%",
            top: "5%",
            containLabel: true,
          },
          xAxis: { type: "value", minInterval: 1, ...baseAxis },
          yAxis: {
            type: "category",
            data: items.map((i) => i.name),
            axisLabel: baseAxis.axisLabel,
            axisLine: baseAxis.axisLine,
          },
          series: [
            {
              name: _t("Members"),
              data: items.map((i) => i.value),
              type: "bar",
              barMaxWidth: 20,
              itemStyle: { borderRadius: [0, 4, 4, 0] },
            },
          ],
        });
        this._bindClick(planChart, (params) => {
          const item = items.find((i) => i.name === params.name);
          if (item) {
            this._openDomain("gym.membership", item.name, [
              ["plan_id", "=", item.plan_id],
            ]);
          }
        });
      }

      const assessmentChart = initChart(this.assessmentChartRef, "assessment");
      if (assessmentChart) {
        const items = data.assessment_pipeline || [];
        assessmentChart.setOption({
          tooltip: { ...tooltipBase, trigger: "axis" },
          grid: {
            left: "3%",
            right: "8%",
            bottom: "5%",
            top: "5%",
            containLabel: true,
          },
          xAxis: { type: "value", minInterval: 1, ...baseAxis },
          yAxis: {
            type: "category",
            data: items.map((i) => i.name),
            axisLabel: baseAxis.axisLabel,
            axisLine: baseAxis.axisLine,
          },
          series: [
            {
              name: _t("Assessments"),
              data: items.map((i) => ({
                value: i.value,
                itemStyle: { color: i.color },
              })),
              type: "bar",
              barMaxWidth: 22,
              itemStyle: { borderRadius: [0, 4, 4, 0] },
            },
          ],
        });
        this._bindClick(assessmentChart, (params) => {
          const item = items.find((i) => i.name === params.name);
          if (item && item.state) {
            this._openDomain("gym.health.assessment", item.name, [
              ["state", "=", item.state],
            ]);
          }
        });
      }
    } else {
      const dailyChart = initChart(this.dailyAttendanceChartRef, "daily");
      if (dailyChart) {
        const series = data.attendance_trend || [];
        dailyChart.setOption({
          color: [THEME.brand],
          tooltip: { ...tooltipBase, trigger: "axis" },
          grid: {
            left: "3%",
            right: "4%",
            bottom: "12%",
            top: "8%",
            containLabel: true,
          },
          xAxis: {
            type: "category",
            data: series.map((i) => i.name),
            axisLabel: { ...baseAxis.axisLabel, interval: 0, rotate: 30 },
            axisLine: baseAxis.axisLine,
          },
          yAxis: { type: "value", minInterval: 1, ...baseAxis },
          series: [
            {
              name: _t("Check-ins"),
              data: series.map((i) => i.value),
              type: "line",
              smooth: true,
              symbolSize: 6,
              areaStyle: { opacity: 0.12 },
            },
          ],
        });
        this._bindClick(dailyChart, (params) => {
          const item = series.find((i) => i.name === params.name);
          if (item && item.month_start) {
            const d = new Date(item.month_start);
            const monthEnd = new Date(d.getFullYear(), d.getMonth() + 1, 1)
              .toISOString()
              .slice(0, 10);
            this._openDomain("gym.attendance", _t("Attendance"), [
              ["check_in", ">=", item.month_start],
              ["check_in", "<", monthEnd],
            ]);
          }
        });
      }

      const hourlyChart = initChart(this.hourlyChartRef, "hourly");
      if (hourlyChart) {
        const series = data.hourly_attendance || [];
        hourlyChart.setOption({
          color: [THEME.brand],
          tooltip: { ...tooltipBase, trigger: "axis" },
          grid: {
            left: "3%",
            right: "4%",
            bottom: "12%",
            top: "8%",
            containLabel: true,
          },
          xAxis: {
            type: "category",
            data: series.map((i) => i.name),
            axisLabel: { ...baseAxis.axisLabel, interval: 1 },
            axisLine: baseAxis.axisLine,
          },
          yAxis: { type: "value", minInterval: 1, ...baseAxis },
          series: [
            {
              name: _t("Check-ins"),
              data: series.map((i) => i.value),
              type: "bar",
              barMaxWidth: 14,
              itemStyle: { borderRadius: [3, 3, 0, 0] },
            },
          ],
        });
      }

      const trainerChart = initChart(this.trainerChartRef, "trainer");
      if (trainerChart) {
        const items = (data.top_trainers || []).slice().reverse();
        trainerChart.setOption({
          color: [THEME.brand],
          tooltip: { ...tooltipBase, trigger: "axis" },
          grid: {
            left: "3%",
            right: "8%",
            bottom: "5%",
            top: "5%",
            containLabel: true,
          },
          xAxis: { type: "value", minInterval: 1, ...baseAxis },
          yAxis: {
            type: "category",
            data: items.map((i) => i.name),
            axisLabel: baseAxis.axisLabel,
            axisLine: baseAxis.axisLine,
          },
          series: [
            {
              name: _t("Active Members"),
              data: items.map((i) => i.value),
              type: "bar",
              barMaxWidth: 20,
              itemStyle: { borderRadius: [0, 4, 4, 0] },
            },
          ],
        });
        this._bindClick(trainerChart, (params) => {
          const item = items.find((i) => i.name === params.name);
          if (item) {
            this._openDomain("gym.membership", item.name, [
              ["trainer_id", "=", item.trainer_id],
              ["state", "=", "active"],
            ]);
          }
        });
      }

      const staffAttendanceChart = initChart(
        this.staffAttendanceChartRef,
        "staffAttendance",
      );
      if (staffAttendanceChart) {
        const series = data.staff_attendance_trend || [];
        staffAttendanceChart.setOption({
          color: [THEME.brand],
          tooltip: { ...tooltipBase, trigger: "axis" },
          grid: {
            left: "3%",
            right: "4%",
            bottom: "12%",
            top: "8%",
            containLabel: true,
          },
          xAxis: {
            type: "category",
            data: series.map((i) => i.name),
            axisLabel: { ...baseAxis.axisLabel, interval: 0, rotate: 30 },
            axisLine: baseAxis.axisLine,
          },
          yAxis: { type: "value", minInterval: 1, ...baseAxis },
          series: [
            {
              name: _t("Staff Check-ins"),
              data: series.map((i) => i.value),
              type: "line",
              smooth: true,
              symbolSize: 6,
              areaStyle: { opacity: 0.12 },
            },
          ],
        });
        this._bindClick(staffAttendanceChart, (params) => {
          const item = series.find((i) => i.name === params.name);
          if (item && item.month_start) {
            const d = new Date(item.month_start);
            const monthEnd = new Date(d.getFullYear(), d.getMonth() + 1, 1)
              .toISOString()
              .slice(0, 10);
            this._openDomain("hr.attendance", _t("Staff Attendance"), [
              ["check_in", ">=", item.month_start],
              ["check_in", "<", monthEnd],
            ]);
          }
        });
      }
    }
  }

  resizeCharts() {
    if (this.charts) {
      Object.values(this.charts).forEach((chart) => chart.resize());
    }
  }
}

registry.category("actions").add("gym_dashboard", GymDashboard);
