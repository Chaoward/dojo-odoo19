# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class GymEquipmentCategory(models.Model):
    _name = "gym.equipment.category"
    _description = "Gym Equipment Category"
    _order = "name"

    name = fields.Char(string="Name", required=True, translate=True)
    code = fields.Char(string="Code", translate=True)
    description = fields.Text(string="Description", translate=True)
    active = fields.Boolean(default=True)
    equipment_ids = fields.One2many("gym.equipment", "category_id", string="Equipment")

    _sql_constraints = [
        ("name_uniq", "unique(name)", "Equipment category name must be unique."),
    ]


class GymEquipment(models.Model):
    _name = "gym.equipment"
    _description = "Gym Equipment"
    _order = "name"

    name = fields.Char(string="Equipment Name", required=True, translate=True)
    category_id = fields.Many2one(
        "gym.equipment.category",
        string="Category",
        required=True,
        domain=[("active", "=", True)],
    )
    description = fields.Text(string="Description", translate=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
    )

    _sql_constraints = [
        ("name_company_uniq", "unique(name, company_id)", "Equipment name must be unique per company."),
    ]


class GymTrainerSpecialization(models.Model):
    _name = "gym.trainer.specialization"
    _description = "Trainer Specialization"
    _order = "name"

    name = fields.Char(string="Specialization", required=True, translate=True)
    description = fields.Text(string="Description", translate=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("name_uniq", "unique(name)", "Specialization name must be unique."),
    ]


class GymExerciseCategory(models.Model):
    _name = "gym.exercise.category"
    _description = "Exercise Category"
    _order = "name"

    name = fields.Char(string="Name", required=True, translate=True)
    description = fields.Text(string="Description", translate=True)
    active = fields.Boolean(default=True)
    exercise_ids = fields.One2many("gym.exercise", "category_id", string="Exercises")

    _sql_constraints = [
        ("name_uniq", "unique(name)", "Exercise category name must be unique."),
    ]


class GymExercise(models.Model):
    _name = "gym.exercise"
    _description = "Exercise"
    _order = "name"

    name = fields.Char(string="Exercise Name", required=True, translate=True)
    category_id = fields.Many2one(
        "gym.exercise.category",
        string="Category",
        required=True,
        domain=[("active", "=", True)],
    )
    muscle_group = fields.Char(string="Muscle Group", translate=True)
    equipment_ids = fields.Many2many(
        "gym.equipment",
        "gym_exercise_equipment_rel",
        "exercise_id",
        "equipment_id",
        string="Equipment",
        domain=[("active", "=", True)],
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
    )

    _sql_constraints = [
        ("name_company_uniq", "unique(name, company_id)", "Exercise name must be unique per company."),
    ]


class GymFoodCategory(models.Model):
    _name = "gym.food.category"
    _description = "Food Category"
    _order = "name"

    name = fields.Char(string="Name", required=True, translate=True)
    description = fields.Text(string="Description", translate=True)
    active = fields.Boolean(default=True)
    food_ids = fields.One2many("gym.food", "category_id", string="Foods")

    _sql_constraints = [
        ("name_uniq", "unique(name)", "Food category name must be unique."),
    ]


class GymFood(models.Model):
    _name = "gym.food"
    _description = "Food Item"
    _order = "name"

    name = fields.Char(string="Food Name", required=True, translate=True)
    category_id = fields.Many2one(
        "gym.food.category",
        string="Category",
        required=True,
        domain=[("active", "=", True)],
    )
    calories_per_100g = fields.Float(string="Calories per 100g", required=True)
    protein_g = fields.Float(string="Protein (g)")
    carbs_g = fields.Float(string="Carbs (g)")
    fat_g = fields.Float(string="Fat (g)")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
    )

    _sql_constraints = [
        ("name_company_uniq", "unique(name, company_id)", "Food name must be unique per company."),
    ]

    @api.constrains("calories_per_100g")
    def _check_calories(self):
        for rec in self:
            if rec.calories_per_100g < 0:
                raise ValidationError(_("Calories per 100g must be 0 or greater."))
