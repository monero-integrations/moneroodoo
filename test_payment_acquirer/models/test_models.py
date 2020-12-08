from odoo import fields, models


class TestRelatedAction(models.Model):

    _name = "test.related.action"
    _description = "Test model for related actions"

    def testing_related_action__no(self):
        return

    def testing_related_action__return_none(self):
        return

    def testing_related_action__kwargs(self):
        return

    def testing_related_action__store(self):
        return
