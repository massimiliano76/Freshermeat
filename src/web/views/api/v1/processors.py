#! /usr/bin/env python
# -*- coding: utf-8 -*-

from flask import request
from flask_login import current_user
from flask_restless import ProcessingException

import lib.checks
from bootstrap import db
from notifications.notifications import new_request_notification
from web.views.common import login_user_bundle
from web.models import User, Project, Request


def auth_func(*args, **kw):
    if request.authorization:
        user = User.query.filter(name == request.authorization.username).first()
        if not user:
            raise ProcessingException("Couldn't authenticate your user",
                                      code=401)
        if not user.check_password(request.authorization.password):
            raise ProcessingException("Couldn't authenticate your user",
                                      code=401)
        if not user.is_active:
            raise ProcessingException("User is desactivated", code=401)
        login_user_bundle(user)
    if not current_user.is_authenticated:
        raise ProcessingException(description='Not authenticated!', code=401)
    return True


def post_preprocessor(data=None, **kw):
    """Accepts a single argument, `data`, which is the dictionary of
    fields to set on the new instance of the model.

    Checks if the project corresponding to user's request is enabled.
    Before the creation of a new request, the content submited by the user
    is checked against the appropriate functions.
    """
    project_id = data['project_id']
    project = Project.query.filter(Project.id == project_id).first()
    if not project.enabled:
        raise ProcessingException(
            "Project currently not available.", code=422)
    checks = []
    for info in project.required_informations:
        for check in info.get('checks', []):
            try:
                check_function = getattr(lib.checks, check)
            except AttributeError:
                # the check 'check' do not exists
                continue
            try:
                # 'parameter' is the content submitted by the user that we want
                # to check against check_function
                parameter = data['required_informations'][info['name']]
            except KeyError:
                # a non-required information that was not submitted by the user
                continue
            checks.append(check_function(parameter))
    if not all(checks):
        raise ProcessingException(
            "The values you submitted do not pass all checks!", code=422)


def post_postprocessor(result=None, **kw):
    """Accepts a single argument, `result`, which is the dictionary
    representation of the created instance of the model.

    Right after the creation a new request, a notification is sent to the
    project responsible.
    """
    new_request = None
    try:
        new_request = Request.query.filter(Request.id == result['id']).first()
    except Exception as e:
        print(e)

    if new_request:
        # send the notification...
        try:
            new_request_notification(new_request)
            new_request.notification_sent = True
            db.session.commit()
        except Exception as e:
            print(e)
