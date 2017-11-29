"""
Auto-generated class for Service
"""
from .ServiceState import ServiceState
from six import string_types

from . import client_support


class Service(object):
    """
    auto-generated. don't touch.
    """

    @staticmethod
    def create(**kwargs):
        """
        :type guid: str
        :type name: str
        :type state: list[ServiceState]
        :type template: str
        :type version: str
        :rtype: Service
        """

        return Service(**kwargs)

    def __init__(self, json=None, **kwargs):
        if json is None and not kwargs:
            raise ValueError('No data or kwargs present')

        class_name = 'Service'
        data = json or kwargs

        # set attributes
        data_types = [string_types]
        self.guid = client_support.set_property('guid', data, data_types, False, [], False, True, class_name)
        data_types = [string_types]
        self.name = client_support.set_property('name', data, data_types, False, [], False, True, class_name)
        data_types = [ServiceState]
        self.state = client_support.set_property('state', data, data_types, False, [], True, True, class_name)
        data_types = [string_types]
        self.template = client_support.set_property('template', data, data_types, False, [], False, True, class_name)
        data_types = [string_types]
        self.version = client_support.set_property('version', data, data_types, False, [], False, True, class_name)

    def __str__(self):
        return self.as_json(indent=4)

    def as_json(self, indent=0):
        return client_support.to_json(self, indent=indent)

    def as_dict(self):
        return client_support.to_dict(self)
