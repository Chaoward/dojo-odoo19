# -*- coding: utf-8 -*-
from odoo import http
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError
from odoo.http import request


class GymPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        partner = request.env.user.partner_id
        if "membership_count" in counters:
            values["membership_count"] = (
                request.env["gym.membership"].search_count([("partner_id", "=", partner.id)])
                if request.env["gym.membership"].has_access("read")
                else 0
            )
        if "workout_plan_count" in counters:
            values["workout_plan_count"] = (
                request.env["gym.workout.plan"].search_count(self._gym_workout_plan_domain())
                if request.env["gym.workout.plan"].has_access("read")
                else 0
            )
        if "diet_plan_count" in counters:
            values["diet_plan_count"] = (
                request.env["gym.diet.plan"].search_count(self._gym_diet_plan_domain())
                if request.env["gym.diet.plan"].has_access("read")
                else 0
            )
        if "attendance_count" in counters:
            values["attendance_count"] = (
                request.env["gym.attendance"].search_count(self._gym_attendance_domain())
                if request.env["gym.attendance"].has_access("read")
                else 0
            )
        return values

    def _gym_membership_domain(self):
        return [("partner_id", "=", request.env.user.partner_id.id)]

    def _gym_workout_plan_domain(self):
        return [("membership_id.partner_id", "=", request.env.user.partner_id.id)]

    def _gym_diet_plan_domain(self):
        return [("membership_id.partner_id", "=", request.env.user.partner_id.id)]

    def _gym_attendance_domain(self):
        return [("partner_id", "=", request.env.user.partner_id.id)]

    @http.route(["/my/memberships", "/my/memberships/page/<int:page>"], type="http", auth="user", website=True)
    def portal_my_memberships(self, page=1, **kw):
        Membership = request.env["gym.membership"]
        domain = self._gym_membership_domain()

        pager_values = portal_pager(
            url="/my/memberships",
            total=Membership.search_count(domain),
            page=page,
            step=self._items_per_page,
        )
        memberships = Membership.search(
            domain,
            order="id desc",
            limit=self._items_per_page,
            offset=pager_values["offset"],
        )

        values = self._prepare_portal_layout_values()
        values.update(
            {
                "memberships": memberships,
                "page_name": "gym_membership",
                "pager": pager_values,
                "default_url": "/my/memberships",
            },
        )
        return request.render("eb_gym_management.portal_my_memberships", values)

    @http.route(["/my/memberships/<int:membership_id>"], type="http", auth="user", website=True)
    def portal_membership_detail(self, membership_id, **kw):
        try:
            membership_sudo = self._document_check_access("gym.membership", membership_id)
        except (AccessError, MissingError):
            return request.redirect("/my")

        attendances = (
            request.env["gym.attendance"]
            .sudo()
            .search([("membership_id", "=", membership_sudo.id)], order="check_in desc", limit=20)
        )
        open_attendance = attendances.filtered(lambda a: not a.check_out)[:1]

        values = self._prepare_portal_layout_values()
        values.update(
            {
                "membership": membership_sudo,
                "attendances": attendances,
                "open_attendance": open_attendance,
                "attendance_notice": kw.get("attendance_notice"),
                "page_name": "gym_membership",
            },
        )
        return request.render("eb_gym_management.portal_membership_detail", values)

    def _attendance_redirect(self, membership_id, notice, post):
        base_url = post.get("redirect") or "/my/memberships/%d" % membership_id
        separator = "&" if "?" in base_url else "?"
        return request.redirect("%s%sattendance_notice=%s" % (base_url, separator, notice))

    @http.route(
        ["/my/memberships/<int:membership_id>/checkin"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
    )
    def portal_membership_checkin(self, membership_id, **post):
        try:
            membership_sudo = self._document_check_access("gym.membership", membership_id)
        except (AccessError, MissingError):
            return request.redirect("/my")

        notice = False
        if membership_sudo.state == "on_hold":
            notice = "on_hold"
        elif membership_sudo.state != "active":
            notice = "not_active"
        else:
            open_attendance = (
                request.env["gym.attendance"]
                .sudo()
                .search(
                    [
                        ("membership_id", "=", membership_sudo.id),
                        ("check_out", "=", False),
                    ],
                    limit=1,
                )
            )
            if open_attendance:
                notice = "already_in"
            else:
                try:
                    request.env["gym.attendance"].sudo().create(
                        {
                            "partner_id": membership_sudo.partner_id.id,
                            "membership_id": membership_sudo.id,
                        },
                    )
                    notice = "checked_in"
                except (UserError, ValidationError):
                    request.env.cr.rollback()
                    notice = "checkin_failed"

        return self._attendance_redirect(membership_id, notice, post)

    @http.route(
        ["/my/memberships/<int:membership_id>/checkout"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
    )
    def portal_membership_checkout(self, membership_id, **post):
        try:
            membership_sudo = self._document_check_access("gym.membership", membership_id)
        except (AccessError, MissingError):
            return request.redirect("/my")

        notice = False
        open_attendance = (
            request.env["gym.attendance"]
            .sudo()
            .search(
                [
                    ("membership_id", "=", membership_sudo.id),
                    ("check_out", "=", False),
                ],
                limit=1,
            )
        )
        if not open_attendance:
            notice = "not_checked_in"
        else:
            try:
                open_attendance.action_check_out()
                notice = "checked_out"
            except (UserError, ValidationError):
                request.env.cr.rollback()
                notice = "checkout_failed"

        return self._attendance_redirect(membership_id, notice, post)

    @http.route(["/my/attendance", "/my/attendance/page/<int:page>"], type="http", auth="user", website=True)
    def portal_my_attendance(self, page=1, **kw):
        partner = request.env.user.partner_id
        active_membership = request.env["gym.membership"].search(
            [
                ("partner_id", "=", partner.id),
                ("state", "=", "active"),
            ],
            limit=1,
        )
        on_hold_membership = request.env["gym.membership"].search(
            [
                ("partner_id", "=", partner.id),
                ("state", "=", "on_hold"),
            ],
            limit=1,
        )

        Attendance = request.env["gym.attendance"]
        domain = self._gym_attendance_domain()

        pager_values = portal_pager(
            url="/my/attendance",
            total=Attendance.search_count(domain),
            page=page,
            step=self._items_per_page,
        )
        attendances = Attendance.search(
            domain,
            order="check_in desc",
            limit=self._items_per_page,
            offset=pager_values["offset"],
        ).sudo()
        open_attendance = Attendance.sudo().search(
            [
                ("partner_id", "=", partner.id),
                ("check_out", "=", False),
            ],
            limit=1,
        )

        values = self._prepare_portal_layout_values()
        values.update(
            {
                "active_membership": active_membership,
                "on_hold_membership": on_hold_membership,
                "attendances": attendances,
                "open_attendance": open_attendance,
                "attendance_notice": kw.get("attendance_notice"),
                "page_name": "gym_attendance",
                "pager": pager_values,
                "default_url": "/my/attendance",
            },
        )
        return request.render("eb_gym_management.portal_my_attendance", values)

    @http.route(["/my/workout-plans", "/my/workout-plans/page/<int:page>"], type="http", auth="user", website=True)
    def portal_my_workout_plans(self, page=1, **kw):
        WorkoutPlan = request.env["gym.workout.plan"]
        domain = self._gym_workout_plan_domain()

        pager_values = portal_pager(
            url="/my/workout-plans",
            total=WorkoutPlan.search_count(domain),
            page=page,
            step=self._items_per_page,
        )
        workout_plans = WorkoutPlan.search(
            domain,
            order="id desc",
            limit=self._items_per_page,
            offset=pager_values["offset"],
        ).sudo()

        values = self._prepare_portal_layout_values()
        values.update(
            {
                "workout_plans": workout_plans,
                "page_name": "gym_workout_plan",
                "pager": pager_values,
                "default_url": "/my/workout-plans",
            },
        )
        return request.render("eb_gym_management.portal_my_workout_plans", values)

    @http.route(["/my/diet-plans", "/my/diet-plans/page/<int:page>"], type="http", auth="user", website=True)
    def portal_my_diet_plans(self, page=1, **kw):
        DietPlan = request.env["gym.diet.plan"]
        domain = self._gym_diet_plan_domain()

        pager_values = portal_pager(
            url="/my/diet-plans",
            total=DietPlan.search_count(domain),
            page=page,
            step=self._items_per_page,
        )
        diet_plans = DietPlan.search(
            domain,
            order="id desc",
            limit=self._items_per_page,
            offset=pager_values["offset"],
        ).sudo()

        values = self._prepare_portal_layout_values()
        values.update(
            {
                "diet_plans": diet_plans,
                "page_name": "gym_diet_plan",
                "pager": pager_values,
                "default_url": "/my/diet-plans",
            },
        )
        return request.render("eb_gym_management.portal_my_diet_plans", values)

    @http.route(["/my/memberships/<int:membership_id>/workout/<int:plan_id>"], type="http", auth="user", website=True)
    def portal_workout_plan_detail(self, membership_id, plan_id, **kw):
        try:
            plan_sudo = self._document_check_access("gym.workout.plan", plan_id)
        except (AccessError, MissingError):
            return request.redirect("/my")
        if plan_sudo.membership_id.id != membership_id:
            return request.redirect("/my")

        days_order = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        lines_by_day = {day: plan_sudo.line_ids.filtered(lambda l: l.day_of_week == day) for day in days_order}

        values = self._prepare_portal_layout_values()
        values.update(
            {
                "membership": plan_sudo.membership_id,
                "plan": plan_sudo,
                "lines_by_day": lines_by_day,
                "days_order": days_order,
                "page_name": "gym_membership",
            },
        )
        return request.render("eb_gym_management.portal_workout_plan_detail", values)

    @http.route(["/my/memberships/<int:membership_id>/diet/<int:plan_id>"], type="http", auth="user", website=True)
    def portal_diet_plan_detail(self, membership_id, plan_id, **kw):
        try:
            plan_sudo = self._document_check_access("gym.diet.plan", plan_id)
        except (AccessError, MissingError):
            return request.redirect("/my")
        if plan_sudo.membership_id.id != membership_id:
            return request.redirect("/my")

        meals_order = ["breakfast", "mid_morning", "lunch", "evening_snack", "dinner"]
        lines_by_meal = {meal: plan_sudo.line_ids.filtered(lambda l: l.meal_type == meal) for meal in meals_order}

        values = self._prepare_portal_layout_values()
        values.update(
            {
                "membership": plan_sudo.membership_id,
                "plan": plan_sudo,
                "lines_by_meal": lines_by_meal,
                "meals_order": meals_order,
                "page_name": "gym_membership",
            },
        )
        return request.render("eb_gym_management.portal_diet_plan_detail", values)
