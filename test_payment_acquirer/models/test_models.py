# Copyright 2016 Camptocamp SA
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html)

from odoo import fields, models

from odoo.addons.queue_job.exception import RetryableJobError

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
