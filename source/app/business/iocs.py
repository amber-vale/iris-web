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
import logging

from flask_login import current_user
from marshmallow.exceptions import ValidationError

from app import db
from app.models import Ioc
from app.datamgmt.case.case_iocs_db import add_ioc
from app.datamgmt.case.case_iocs_db import check_ioc_type_id
from app.datamgmt.case.case_iocs_db import get_iocs
from app.datamgmt.case.case_iocs_db import delete_ioc
from app.datamgmt.states import update_ioc_state
from app.schema.marshables import IocSchema
from app.iris_engine.module_handler.module_handler import call_modules_hook
from app.iris_engine.utils.tracker import track_activity
from app.business.errors import BusinessProcessingError
from app.datamgmt.case.case_iocs_db import get_ioc


def _load(request_data):
    try:
        add_ioc_schema = IocSchema()
        return add_ioc_schema.load(request_data)
    except ValidationError as e:
        raise BusinessProcessingError('Data error', e.messages)


def iocs_get_by_identifier(ioc_identifier):
    return get_ioc(ioc_identifier)


def iocs_create(request_json, case_identifier):

    # TODO ideally schema validation should be done before, outside the business logic in the REST API
    #      for that the hook should be called after schema validation
    request_data = call_modules_hook('on_preload_ioc_create', data=request_json, caseid=case_identifier)
    ioc = _load({**request_data, "case_id": case_identifier})

    if not check_ioc_type_id(type_id=ioc.ioc_type_id):
        raise BusinessProcessingError('Not a valid IOC type')

    ioc, existed = add_ioc(ioc=ioc, user_id=current_user.id, caseid=case_identifier)

    ioc = call_modules_hook('on_postload_ioc_create', data=ioc, caseid=case_identifier)

    if ioc:
        track_activity(f'added ioc "{ioc.ioc_value}"', caseid=case_identifier)

        msg = 'IOC added'
        return ioc, msg

    raise BusinessProcessingError('Unable to create IOC for internal reasons')


# TODO most probably this method should not require a case_identifier... Since the IOC gets modified for all cases...
def iocs_update(identifier, request_json):

    try:
        ioc = get_ioc(identifier)
        if not ioc:
            raise BusinessProcessingError('Invalid IOC ID for this case')

        # TODO ideally schema validation should be done before, outside the business logic in the REST API
        #      for that the hook should be called after schema validation
        request_data = call_modules_hook('on_preload_ioc_update', data=request_json, caseid=ioc.case_id)

        # validate before saving
        ioc_schema = IocSchema()
        request_data['ioc_id'] = identifier
        request_data['case_id'] = ioc.case_id
        ioc_sc = ioc_schema.load(request_data, instance=ioc, partial=True)
        ioc_sc.user_id = current_user.id

        if not check_ioc_type_id(type_id=ioc_sc.ioc_type_id):
            raise BusinessProcessingError('Not a valid IOC type')

        update_ioc_state(ioc.case_id)
        db.session.commit()

        ioc_sc = call_modules_hook('on_postload_ioc_update', data=ioc_sc, caseid=ioc.case_id)

        if ioc_sc:
            track_activity(f'updated ioc "{ioc_sc.ioc_value}"', caseid=ioc.case_id)
            return ioc, f'Updated ioc "{ioc_sc.ioc_value}"'

        raise BusinessProcessingError('Unable to update ioc for internal reasons')

    # TODO most probably the scope of this try catch could be reduced, this exception is probably raised only on load
    except ValidationError as e:
        raise BusinessProcessingError('Data error', e.messages)

    except Exception as e:
        raise BusinessProcessingError('Unexpected error server-side', e)


def iocs_delete(identifier):

    call_modules_hook('on_preload_ioc_delete', data=identifier)
    ioc = get_ioc(identifier)

    if not ioc:
        raise BusinessProcessingError('Not a valid IOC for this case')

    delete_ioc(ioc, ioc.case_id)

    call_modules_hook('on_postload_ioc_delete', data=identifier, caseid=ioc.case_id)

    track_activity(f'deleted IOC "{ioc.ioc_value}"', caseid=ioc.case_id)
    return f'IOC {identifier} deleted'


def iocs_exports_to_json(case_id):
    iocs = get_iocs(case_id)

    iocs_serialized = IocSchema().dump(iocs, many=True)

    return iocs_serialized


def iocs_build_filter_query(ioc_id: int = None,
                            ioc_uuid: str = None,
                            ioc_value: str = None,
                            ioc_type_id: int = None,
                            ioc_description: str = None,
                            ioc_tlp_id: int = None,
                            ioc_tags: str = None,
                            ioc_misp: str = None,
                            user_id: float = None,
                            linked_cases: float = None):
    """
    Get a list of iocs from the database, filtered by the given parameters
    """
    conditions = []
    if ioc_id is not None:
        conditions.append(Ioc.ioc_id == ioc_id)
    if ioc_uuid is not None:
        conditions.append(Ioc.ioc_uuid == ioc_uuid)
    if ioc_value is not None:
        conditions.append(Ioc.ioc_value == ioc_value)
    if ioc_type_id is not None:
        conditions.append(Ioc.ioc_type_id == ioc_type_id)
    if ioc_description is not None:
        conditions.append(Ioc.ioc_description == ioc_description)
    if ioc_tlp_id is not None:
        conditions.append(Ioc.ioc_tlp_id == ioc_tlp_id)
    if ioc_tags is not None:
        conditions.append(Ioc.ioc_tags == ioc_tags)
    if ioc_misp is not None:
        conditions.append(Ioc.ioc_misp == ioc_misp)
    if user_id is not None:
        conditions.append(Ioc.user_id == user_id)

    query = Ioc.query.filter(*conditions)

    if linked_cases is not None:
        logging.warning("Method 'iocs_build_filter_query' with providing 'linked_cases' is deprecated. It is no longer possible to query IOCs by linked cases.")

    return query
