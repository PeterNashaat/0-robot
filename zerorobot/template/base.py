"""
The base module defines the TemplateBase class.
It is the class every template should inherits from.
"""


import inspect
import os
import time
from uuid import uuid4

import gevent
from js9 import j
from zerorobot import service_collection as scol
from zerorobot.dsl.ZeroRobotAPI import ZeroRobotAPI
from zerorobot.task import PRIORITY_NORMAL, PRIORITY_SYSTEM, Task, TaskList
from zerorobot.template.data import ServiceData
from zerorobot.template.state import ServiceState
from zerorobot.template_collection import TemplateUID


class BadActionArgumentError(Exception):
    """
    Error return when the argument pass when trying to schedule an action
    doesn't match with the method signature
    """
    pass


class ActionNotFoundError(Exception):
    """
    Error raised when trying to schedule an action that doesn't exist
    """
    pass


class BadTemplateError(Exception):
    """
    Error raised when trying to load a service with a wrong template class
    """
    pass


class GreenletsMgr:
    """
    GreenletsMgr is a tools that lets you
    manage a group of greenlets

    it gives basic primitives to keep a reference of a greenlets and start/stop/get them
    """

    def __init__(self):
        self.gls = {}

    def add(self, key, gl):
        if not isinstance(gl, gevent.Greenlet):
            raise TypeError("gl should be a Greenlet not %s" % type(gl))

        if not gl.started:
            gl.start()

        self.gls[key] = gl

    def get(self, key):
        return self.gls[key]

    def stop(self, key):
        try:
            gl = self.get(key)
            gl.kill()
        except KeyError:
            pass

    def stop_all(self):
        for gl in self.gls.values():
            gl.kill()


class TemplateBase:
    """
    This is the base class any service should inherit from.

    The child class will implement actions on this class.
    """

    # The developer of the template need to set the version the template
    version = None
    # This is the unique identifier of the template. This is set during template loading
    template_uid = None
    # path of the template on disk. This is set during template loading
    template_dir = None

    def __init__(self, name, guid=None):
        self.guid = guid or str(uuid4())
        self.name = name
        self.parent = None

        self.api = ZeroRobotAPI()

        self.data = ServiceData(self)
        self.state = ServiceState()
        self.task_list = TaskList()

        # start the greenlets of this service
        self._gl_mgr = GreenletsMgr()
        self._gl_mgr.add('executor', gevent.Greenlet(self._run))

    @classmethod
    def load(cls, base_path):
        """
        load the service from it's file system serialized format

        @param base_path: path of the directory where
                          to load the service state and data from
        """
        if not os.path.exists(base_path):
            raise FileNotFoundError("Trying to load service from %s, but directory doesn't exists" % base_path)

        name = os.path.basename(base_path)
        service_info = j.data.serializer.yaml.load(os.path.join(base_path, 'service.yaml'))
        template_uid = TemplateUID.parse(service_info['template'])
        if template_uid != cls.template_uid:
            raise BadTemplateError("Trying to load service %s with template %s, while it requires %s"
                                   % (name, cls.template_uid, service_info['template']))

        if service_info['name'] != name:
            raise BadTemplateError("Trying to load service from folder %s, but name of the service is %s"
                                   % (base_path, service_info['name']))

        srv = cls(service_info['name'], service_info['guid'])
        if service_info['parent']:
            srv.parent = scol.get_by_guid(service_info['parent'])

        srv.state.load(os.path.join(base_path, 'state.yaml'))
        srv.data.load(os.path.join(base_path, 'data.yaml'))
        srv.task_list.load(os.path.join(base_path, 'tasks.yaml'), srv)

        return srv

    def save(self, base_path):
        """
        serialize the service state and data to a file

        @param base_path: path of the directory where
                          to save the service state and data
        return the path where the service is saved
        """
        parent = self.parent
        path = base_path
        while parent is not None:
            path = os.path.join(path, parent.name)
            parent = parent.parent

        path = os.path.join(path, self.name)

        os.makedirs(path, exist_ok=True)

        j.data.serializer.yaml.dump(os.path.join(path, 'service.yaml'), {
            'template': str(self.template_uid),
            'version': self.version,
            'name': self.name,
            'guid': self.guid,
            'parent': self.parent.guid if self.parent else None,
        })
        self.state.save(os.path.join(path, 'state.yaml'))
        self.data.save(os.path.join(path, 'data.yaml'))
        self.task_list.save(os.path.join(path, 'tasks.yaml'))
        return path

    def _run(self):
        """
        _run is responsible to walk over the task list to execute actions
        and handle responses from other service
        """
        while True:
            try:
                task = self.task_list.get()
                task.execute()
            except gevent.GreenletExit:
                # TODO: gracefull shutdown
                break

    def schedule_action(self, action, args=None, resp_q=None):
        """
        Add an action to the task list of this service.
        This method should never be called directly by the user.
        It will always be called by another service.
        Or from a local service or from a remote service trough RPC

        @param action: action is the name of the action to add to the task list
        @param args: dictionnary of the argument to pass to the action
        @param resp_q: is the response queue on which the result of the action need to be put
        """
        return self._schedule_action(action, args, resp_q)

    def _schedule_action(self, action, args=None, resp_q=None, priority=PRIORITY_NORMAL):
        if not hasattr(self, action):
            raise ActionNotFoundError("sel %s doesn't have action %s" % (self.name, action))

        method = getattr(self, action)
        if not callable(method):
            raise ActionNotFoundError("%s is not a function" % action)

        # make sure the argument we pass are correct
        s = inspect.signature(method)
        for param in s.parameters.values():
            if args is None:
                args = {}
            if param.default == inspect._empty and param.name not in args:
                raise BadActionArgumentError("parameter %s is mandatory but not passed to in args" % param.name)

        if args is not None:
            signature_keys = set(s.parameters.keys())
            args_keys = set(args.keys())
            diff = args_keys.difference(signature_keys)
            if len(diff) > 0:
                raise BadActionArgumentError('arguments "%s" are not present in the signature of the action' % ','.join(args_keys))

        task = Task(self, action, args, resp_q)
        self.task_list.put(task, priority=priority)
        return task

    def recurring_action(self, action, period):
        """
        configure an action to be executed every period second

        It will ensure that the action from service is schedule at best every period second.

        Since we dont' have control over how long other task from the task list take.
        we can only ensure that the action is never going to be schedule faster then every period second

        That means that it can be a longer time then period second during which the action is not executed

        @param action: a method or string that match the name of the method we want to make recurring
        @param period: minimum number of seconds between 2 scheduling of the action
        """
        if inspect.ismethod(action) or inspect.isfunction(action):
            action = action.__name__

        gl = gevent.Greenlet(_recurring_action, self, action, period)
        self._gl_mgr.add("recurring_" + action, gl)

    def delete(self):
        scol.delete(self)


def _recurring_action(service, action, period):
    """
    this function is intended to be run in a greenlet.
    It will ensure that the action from service is schedule at best every period second.

    Since we dont' have controle over how long other task from the task list take.
    we can only ensure that the action is never going to be schedule faster then every period second

    That means that it can be a longer time then period second during which the action is not executed
    """
    last = -1
    elapsed = -1
    while True:
        try:
            if last < 0 or elapsed >= period:
                task = service._schedule_action(action, priority=PRIORITY_SYSTEM)
                task.wait()
            else:
                gevent.sleep(0.5)

            elapsed = int(time.time()) - task.created
        except gevent.GreenletExit:
            break