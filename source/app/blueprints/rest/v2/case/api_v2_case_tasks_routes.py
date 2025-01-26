#  IRIS Source Code
#  Copyright (C) 2024 - DFIR-IRIS
#  contact@dfir-iris.org
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 3 of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

from flask import Blueprint
from flask import request

from app.blueprints.rest.endpoints import response_api_deleted
from app.blueprints.rest.endpoints import response_api_not_found
from app.blueprints.rest.endpoints import response_api_error
from app.blueprints.rest.endpoints import response_api_created
from app.blueprints.access_controls import ac_api_return_access_denied
from app.blueprints.access_controls import ac_api_requires
from app.schema.marshables import CaseTaskSchema
from app.business.errors import ObjectNotFoundError
from app.business.errors import BusinessProcessingError
from app.business.tasks import tasks_delete
from app.business.tasks import tasks_create
from app.business.tasks import tasks_get
from app.models.authorization import CaseAccessLevel
from app.iris_engine.access_control.utils import ac_fast_check_current_user_has_case_access

api_v2_tasks_blueprint = Blueprint('case_tasks_rest_v2',
                                   __name__,
                                   url_prefix='/api/v2')


@api_v2_tasks_blueprint.route('/cases/<int:identifier>/tasks', methods=['POST'])
@ac_api_requires()
def case_add_task(identifier):
    if not ac_fast_check_current_user_has_case_access(identifier, [CaseAccessLevel.full_access]):
        return ac_api_return_access_denied(caseid=identifier)

    task_schema = CaseTaskSchema()
    try:
        _, case = tasks_create(identifier, request.get_json())
        return response_api_created(task_schema.dump(case))
    except BusinessProcessingError as e:
        return response_api_error(e.get_message())


@api_v2_tasks_blueprint.route('/tasks/<int:identifier>', methods=['GET'])
@ac_api_requires()
def case_task_view(identifier):
    try:
        task = tasks_get(identifier)
        if not ac_fast_check_current_user_has_case_access(task.task_case_id, [CaseAccessLevel.read_only, CaseAccessLevel.full_access]):
            return ac_api_return_access_denied(caseid=task.task_case_id)

        task_schema = CaseTaskSchema()
        return response_api_created(task_schema.dump(task))
    except ObjectNotFoundError:
        return response_api_not_found()


@api_v2_tasks_blueprint.route('/tasks/<int:identifier>', methods=['DELETE'])
@ac_api_requires()
def case_delete_task(identifier):
    try:
        task = tasks_get(identifier)
        if not ac_fast_check_current_user_has_case_access(task.task_case_id, [CaseAccessLevel.full_access]):
            return ac_api_return_access_denied(caseid=identifier)

        tasks_delete(task)
        return response_api_deleted()
    except ObjectNotFoundError:
        return response_api_not_found()
    except BusinessProcessingError as e:
        return response_api_error(e.get_message())
