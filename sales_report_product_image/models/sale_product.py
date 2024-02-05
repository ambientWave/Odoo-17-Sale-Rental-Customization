# See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api, _
import datetime
from pytz import timezone, UTC
from odoo.tools import format_datetime, format_time
import logging

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = "sale.order"

    print_image = fields.Boolean("Print Image", 
        help="""If ticked, you can see the product image in 
report of sale order/quotation""",default=True)
    image_sizes = fields.Selection(
        [("image", "Big sized Image"),
        ("image_medium", "Medium Sized Image"),
        ("image_small", "Small Sized Image"),
        ], "Image Sizes", default="image_small",
        help="Image size to be displayed in report")
    
    displayed_company_in_printed_document = fields.Selection(
        [("rodyan", "Rodyan"),
        ("cinearm", "CineArm"),
        ], default="rodyan",
        help="Select the company brand that you want to it be shown in the printed document", tracking=True)

    def action_update_rental_prices(self):
        self.ensure_one()
        self._recompute_rental_prices()
        if self.duration_days or self.remaining_hours:
                duration_in_days = self.duration_days if self.duration_days else 0
                remaining_duration_in_days = ((self.remaining_hours)/24) if self.remaining_hours else 0
                total_rental_duration_in_days = duration_in_days + remaining_duration_in_days
                if self.order_line:
                    # iterate through sale order lines
                    for rec in self.order_line:
                        # 
                        rec.rental_price_per_day = rec.price_unit/total_rental_duration_in_days
                        # 
                        rec.price_unit += (((rec.rental_company_fees * 0.01) * rec.rental_price_per_day) * total_rental_duration_in_days)

        self.message_post(body=_("Rental prices have been recomputed with the new period."))

    @api.onchange('order_line', 'analytic_account_id')
    def onchange_apply_analytic_distribution_to_lines(self):
        """
        """
        if self.analytic_account_id:
            if self.order_line:
                # iterate through sale order lines
                for rec in self.order_line:
                    # 
                    rec.analytic_distribution = {str(self.analytic_account_id.id): 100.0}


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    image_small = fields.Binary("Product Image", related="product_id.image_1920")
    rental_price_per_day = fields.Float("Rental Charging Price per Day", default=0.0, copy=True, compute='compute_rental_price_per_day', store=True)
    rental_duration_in_days = fields.Float("Rental Duration Expressed in Days", copy=True, default=0.0, store=True, compute='compute_rental_duration', inverse='set_rental_duration')
    rental_company_fees = fields.Float("Company Fees Percentage of Price per Day", default=0.0, copy=True, help='''Enter a number between 0 and 100
                                       This number represents the percentage of daily charging rate that would be added to the unit price''')


    # this method is triggered after onchange-tagged methods and before saving forms
    @api.depends('product_id')
    def compute_rental_price_per_day(self):
        '''
        the method is triggered even before the transaction is committed in modifying form view
        '''
        try:
            self.ensure_one()
            if self.order_id.is_rental_order:
                if self.rental_duration_in_days > 0:
                    self.rental_price_per_day = self._get_pricelist_price()/self.rental_duration_in_days
        except:
            pass
                
    @api.onchange('rental_company_fees', 'rental_duration_in_days', 'product_uom_qty')
    def set_price_unit_with_rental_company_fees(self):
        '''
        onchange-decorated methods called before any other ones and isn't called
        after a change in a dependent field by another method; only the change by the user
        '''
        # this method takes into consideration the duration
        if self.order_id.is_rental_order:
            if (self.rental_price_per_day != self.price_unit) and (self.rental_price_per_day == 0):
                # represents the initial case
                pass
            elif (self.rental_price_per_day == self.price_unit):
                shadow_price_per_day_value = self.rental_price_per_day
                updated_price_unit_with_duration = shadow_price_per_day_value * self.rental_duration_in_days # does this solve it? test with both values present
                updated_price_unit_with_duration_and_fees = updated_price_unit_with_duration + (((self.rental_company_fees * 0.01) * self.rental_price_per_day) * self.rental_duration_in_days)
                self.price_unit = updated_price_unit_with_duration_and_fees
            elif ((self.rental_price_per_day != self.price_unit) and (self.rental_price_per_day > 0)):
                shadow_price_per_day_value = self.rental_price_per_day
                updated_price_unit_with_duration = shadow_price_per_day_value * self.rental_duration_in_days # does this solve it? test with both values present
                updated_price_unit_with_duration_and_fees = updated_price_unit_with_duration + (((self.rental_company_fees * 0.01) * self.rental_price_per_day) * self.rental_duration_in_days)
                self.price_unit = updated_price_unit_with_duration_and_fees

    @api.depends('product_id', 'start_date', 'return_date')
    def compute_rental_duration(self):
        try:
            self.ensure_one()
            if self.order_id.is_rental_order:
                time_difference = self.return_date - self.start_date
                duration_in_seconds = time_difference.total_seconds()
                duration_tuple = divmod(duration_in_seconds, 86400) # there're 86400 seconds in one day
                self.rental_duration_in_days = duration_tuple[0] + (duration_tuple[1]/86400)
                if (self.rental_price_per_day == self.price_unit):
                    shadow_price_per_day_value = self.rental_price_per_day
                    updated_price_unit_with_duration_and_fees = (shadow_price_per_day_value * self.rental_duration_in_days) + (((self.rental_company_fees * 0.01) * self.rental_price_per_day) * self.rental_duration_in_days) if self.rental_company_fees > 0 else (self.rental_price_per_day) * (self.rental_duration_in_days)
                    self.price_unit = updated_price_unit_with_duration_and_fees
                elif ((self.rental_price_per_day != self.price_unit) and (self.rental_price_per_day > 0)):
                    shadow_price_per_day_value = self.rental_price_per_day
                    updated_price_unit_with_duration_and_fees = (shadow_price_per_day_value * self.rental_duration_in_days) + (((self.rental_company_fees * 0.01) * self.rental_price_per_day) * self.rental_duration_in_days) if self.rental_company_fees > 0 else (self.rental_price_per_day) * (self.rental_duration_in_days)
                    self.price_unit = updated_price_unit_with_duration_and_fees

        except:
            pass
    
    @api.onchange('rental_duration_in_days')
    def set_rental_duration(self):
        if self.order_id.is_rental_order:
            try:
                self.ensure_one()
                start_date = self.start_date

                end_date = start_date + datetime.timedelta(days=(self.rental_duration_in_days))
                _logger.error(f'end_date = {end_date}')
                self.return_date = end_date
                _logger.error(f'return_date = {self.return_date}')

                line_description = self.name
                line_description_split_list = line_description.split("\n")
                tz = self._get_tz()
                start_date = self.start_date
                return_date = self.return_date
                env = self.with_context(use_babel=True).env
                if start_date and return_date\
                and start_date.replace(tzinfo=UTC).astimezone(timezone(tz)).date()\
                    == return_date.replace(tzinfo=UTC).astimezone(timezone(tz)).date():
                    # If return day is the same as pickup day, don't display return_date Y/M/D in description.
                    return_date_part = format_time(env, return_date, tz=tz, time_format=False)
                else:
                    return_date_part = format_datetime(env, return_date, tz=tz, dt_format=False)
                start_date_part = format_datetime(env, start_date, tz=tz, dt_format=False)

                line_description_split_list[-1] = _(
                    "%(from_date)s to %(to_date)s", from_date=start_date_part, to_date=return_date_part
                )

                self.name = "\n".join(line_description_split_list)
            except:
                pass