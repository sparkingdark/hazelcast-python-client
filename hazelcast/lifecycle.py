import logging
import uuid

from hazelcast import six
from hazelcast.util import create_git_info, enum

LifecycleState = enum(
    STARTING="STARTING",
    STARTED="STARTED",
    SHUTTING_DOWN="SHUTTING_DOWN",
    SHUTDOWN="SHUTDOWN",
    CONNECTED="CONNECTED",
    DISCONNECTED="DISCONNECTED",
)


class LifecycleService(object):
    """
    Lifecycle service for the Hazelcast client. Allows to determine
    state of the client and add or remove lifecycle listeners.
    """

    def __init__(self, internal_lifecycle_service):
        self._service = internal_lifecycle_service

    def is_running(self):
        """
        Checks whether or not the instance is running.

        :return: ``True``, if the client is active and running, ``False`` otherwise.
        :rtype: bool
        """
        return self._service.running

    def add_listener(self, on_state_change):
        """
        Adds a listener to listen for lifecycle events.

        :param on_state_change: Function to be called when lifecycle state is changed.
        :type on_state_change: function

        :return: Registration id of the listener
        :rtype: str
        """
        return self._service.add_listener(on_state_change)

    def remove_listener(self, registration_id):
        """
        Removes a lifecycle listener.

        :param registration_id: The id of the listener to be removed.
        :type registration_id: str

        :return: ``True`` if the listener is removed successfully, ``False`` otherwise.
        :rtype: bool
        """
        self._service.remove_listener(registration_id)


class _InternalLifecycleService(object):
    logger = logging.getLogger("HazelcastClient.LifecycleService")

    def __init__(self, client, logger_extras):
        self._client = client
        self._logger_extras = logger_extras
        self.running = False
        self._listeners = {}

        for listener in client.config.lifecycle_listeners:
            self.add_listener(listener)

        self._git_info = create_git_info()

    def start(self):
        if self.running:
            return

        self.fire_lifecycle_event(LifecycleState.STARTING)
        self.running = True
        self.fire_lifecycle_event(LifecycleState.STARTED)

    def shutdown(self):
        self.running = False

    def add_listener(self, on_state_change):
        listener_id = str(uuid.uuid4())
        self._listeners[listener_id] = on_state_change
        return listener_id

    def remove_listener(self, registration_id):
        try:
            self._listeners.pop(registration_id)
            return True
        except KeyError:
            return False

    def fire_lifecycle_event(self, new_state):
        self.logger.info(self._git_info + "HazelcastClient is %s", new_state, extra=self._logger_extras)
        for on_state_change in six.itervalues(self._listeners):
            if on_state_change:
                try:
                    on_state_change(new_state)
                except:
                    self.logger.exception("Exception in lifecycle listener", extra=self._logger_extras)
