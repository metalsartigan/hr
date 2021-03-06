# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    This module copyright (C) 2015 Therp BV <http://therp.nl>.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
from openerp import SUPERUSER_ID
from openerp.api import Environment


def pre_init_hook(cr):
    adjust_employee_partners_pre(cr)


def adjust_employee_partners_pre(cr):
    cr.execute('update hr_employee e set address_id=null '
               'from res_company c where address_id=c.partner_id')
    # set work address to user's partner if any
    cr.execute(
        '''update hr_employee e
        set
        address_id=u.partner_id
        from
        resource_resource r,
        res_users u
        where e.resource_id=r.id and r.user_id=u.id and e.address_id is null
        ''')
    # copy unset fields on the linked partner records from the employee
    cr.execute(
        '''update res_partner p
        set
        phone=coalesce(nullif(trim(p.phone), ''), e.work_phone),
        email=coalesce(nullif(trim(p.email), ''), e.work_email),
        mobile=coalesce(nullif(trim(p.mobile), ''), e.mobile_phone),
        image=coalesce(p.image, e.image)
        from
        hr_employee e
        where e.address_id=p.id
        ''')
    # point all remaining employees without address_id to a company partner to
    # satisfy newly introduced non null constraint
    cr.execute('update hr_employee e set address_id=c.partner_id '
               'from res_company c where e.address_id is null')


def post_init_hook(cr, pool):
    env = Environment(cr, SUPERUSER_ID, {})
    adjust_employee_partners_post(env)


def adjust_employee_partners_post(env):
    companies = env['res.company'].with_context(active_test=False).search([])
    company_partners = companies.mapped('partner_id')
    # recalculate images for partners we possibly touched in pre-init
    recalculate_ids = env['hr.employee'].with_context(active_test=False)\
        .search([('address_id', 'not in', company_partners.ids)])\
        .mapped('address_id.id')
    env['res.partner']._model._store_set_values(
        env.cr, env.uid, recalculate_ids, ['image_small', 'image_medium'],
        env.context)
    # create a new partner for all employees pointing to a company address
    employees = env['hr.employee'].with_context(active_test=False).search(
        [('address_id', 'in', company_partners.ids)], order='id')
    # we need to read related values from the database because the related
    # fields already cover our fields
    if not employees.ids:
        return
    env.cr.execute(
        'select work_phone, work_email, mobile_phone, image '
        'from hr_employee where id in %s order by id',
        (tuple(employees.ids),))
    employee_db_data = env.cr.dictfetchall()
    for employee, db_data in zip(employees, employee_db_data):
        employee.address_id = env['res.partner'].create({
            'employee': True,
            'name': employee.name,
            'phone': db_data['work_phone'],
            'email': db_data['work_email'],
            'mobile': db_data['mobile_phone'],
            'image': db_data['image'],
            'active': employee.active,
        })


def uninstall_hook(cr, pool):
    cr.execute('alter table hr_employee alter column address_id drop not null')
