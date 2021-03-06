#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import collections
import inspect

from neutron_lib.callbacks import manager


# TODO(armax): consider adding locking
_CALLBACK_MANAGER = None

# stores a dictionary keyed on function pointers with a list of
# (resource, event) tuples to subscribe to on class initialization
_REGISTERED_CLASS_METHODS = collections.defaultdict(list)


def _get_callback_manager():
    global _CALLBACK_MANAGER
    if _CALLBACK_MANAGER is None:
        _CALLBACK_MANAGER = manager.CallbacksManager()
    return _CALLBACK_MANAGER


def subscribe(callback, resource, event):
    _get_callback_manager().subscribe(callback, resource, event)


def unsubscribe(callback, resource, event):
    _get_callback_manager().unsubscribe(callback, resource, event)


def unsubscribe_by_resource(callback, resource):
    _get_callback_manager().unsubscribe_by_resource(callback, resource)


def unsubscribe_all(callback):
    _get_callback_manager().unsubscribe_all(callback)


# NOTE(boden): This method is deprecated in favor of publish() and will be
# removed in Queens, but not deprecation message to reduce log flooding
def notify(resource, event, trigger, **kwargs):
    _get_callback_manager().notify(resource, event, trigger, **kwargs)


def publish(resource, event, trigger, payload=None):
    _get_callback_manager().publish(resource, event, trigger, payload=payload)


def clear():
    _get_callback_manager().clear()


def receives(resource, events):
    """Use to decorate methods on classes before initialization.

    Any classes that use this must themselves be decorated with the
    @has_registry_receivers decorator to setup the __new__ method to
    actually register the instance methods after initialization.
    """
    def decorator(f):
        for e in events:
            _REGISTERED_CLASS_METHODS[f].append((resource, e))
        return f
    return decorator


def has_registry_receivers(klass):
    """Decorator to setup __new__ method in classes to subscribe bound methods.

    Any method decorated with @receives above is an unbound method on a class.
    This decorator sets up the class __new__ method to subscribe the bound
    method in the callback registry after object instantiation.
    """
    orig_new = klass.__new__
    new_inherited = '__new__' not in klass.__dict__

    @staticmethod
    def replacement_new(cls, *args, **kwargs):
        if new_inherited:
            # class didn't define __new__ so we need to call inherited __new__
            super_new = super(klass, cls).__new__
            if super_new is object.__new__:
                # object.__new__ doesn't accept args nor kwargs
                instance = super_new(cls)
            else:
                instance = super_new(cls, *args, **kwargs)
        else:
            instance = orig_new(cls, *args, **kwargs)
        if getattr(instance, '_DECORATED_METHODS_SUBSCRIBED', False):
            # Avoid running this logic twice for classes inheriting other
            # classes with this same decorator. Only one needs to execute
            # to subscribe all decorated methods.
            return instance
        for name, unbound_method in inspect.getmembers(cls):
            if (not inspect.ismethod(unbound_method) and
                    not inspect.isfunction(unbound_method)):
                continue
            # handle py27/py34 difference
            func = getattr(unbound_method, 'im_func', unbound_method)
            if func not in _REGISTERED_CLASS_METHODS:
                continue
            for resource, event in _REGISTERED_CLASS_METHODS[func]:
                # subscribe the bound method
                subscribe(getattr(instance, name), resource, event)
        setattr(instance, '_DECORATED_METHODS_SUBSCRIBED', True)
        return instance
    klass.__new__ = replacement_new
    return klass
