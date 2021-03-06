import logging
import random
import threading
import uuid
from collections import OrderedDict

from hazelcast import six
from hazelcast.errors import TargetDisconnectedError, IllegalStateError
from hazelcast.util import check_not_none


class _MemberListSnapshot(object):
    __slots__ = ("version", "members")

    def __init__(self, version, members):
        self.version = version
        self.members = members


class ClientInfo(object):
    """
    Local information of the client.
    """

    __slots__ = ("uuid", "address", "name", "labels")

    def __init__(self, client_uuid, address, name, labels):
        self.uuid = client_uuid
        """Unique id of this client instance."""

        self.address = address
        """Local address that is used to communicate with cluster."""

        self.name = name
        """Name of the client."""

        self.labels = labels
        """Read-only set of all labels of this client."""

    def __repr__(self):
        return "ClientInfo(uuid=%s, address=%s, name=%s, labels=%s)" % (self.uuid, self.address, self.name, self.labels)


_EMPTY_SNAPSHOT = _MemberListSnapshot(-1, OrderedDict())
_INITIAL_MEMBERS_TIMEOUT_SECONDS = 120


class ClusterService(object):
    """
    Cluster service for Hazelcast clients.

    It provides access to the members in the cluster
    and one can register for changes in the cluster members.
    """

    def __init__(self, internal_cluster_service):
        self._service = internal_cluster_service

    def add_listener(self, member_added=None, member_removed=None, fire_for_existing=False):
        """
        Adds a membership listener to listen for membership updates.

        It will be notified when a member is added to cluster or removed from cluster.
        There is no check for duplicate registrations, so if you register the listener
        twice, it will get events twice.

        :param member_added: Function to be called when a member is added to the cluster.
        :type member_added: function
        :param member_removed: Function to be called when a member is removed from the cluster.
        :type member_removed: function
        :param fire_for_existing: Whether or not fire member_added for existing members.
        :type fire_for_existing: bool

        :return: Registration id of the listener which will be used for removing this listener.
        :rtype: str
        """
        return self._service.add_listener(member_added, member_removed, fire_for_existing)

    def remove_listener(self, registration_id):
        """
        Removes the specified membership listener.

        :param registration_id: Registration id of the listener to be removed.
        :type registration_id: str

        :return: ``True`` if the registration is removed, ``False`` otherwise.
        :rtype: bool
        """
        return self._service.remove_listener(registration_id)

    def get_members(self, member_selector=None):
        """
        Lists the current members in the cluster.

        Every member in the cluster returns the members in the same order.
        To obtain the oldest member in the cluster, you can retrieve the first item in the list.

        :param member_selector: Function to filter members to return.
            If not provided, the returned list will contain all the available cluster members.
        :type member_selector: function

        :return: Current members in the cluster
        :rtype: list[:class:`~hazelcast.core.MemberInfo`]
        """
        return self._service.get_members(member_selector)


class _InternalClusterService(object):
    logger = logging.getLogger("HazelcastClient.ClusterService")

    def __init__(self, client, logger_extras):
        self._client = client
        self._connection_manager = None
        self._logger_extras = logger_extras
        config = client.config
        self._labels = frozenset(config.labels)
        self._listeners = {}
        self._member_list_snapshot = _EMPTY_SNAPSHOT
        self._initial_list_fetched = threading.Event()

    def start(self, connection_manager, membership_listeners):
        self._connection_manager = connection_manager
        for listener in membership_listeners:
            self.add_listener(*listener)

    def get_member(self, member_uuid):
        check_not_none(uuid, "UUID must not be null")
        snapshot = self._member_list_snapshot
        return snapshot.members.get(member_uuid, None)

    def get_members(self, member_selector=None):
        snapshot = self._member_list_snapshot
        if not member_selector:
            return list(snapshot.members.values())

        members = []
        for member in six.itervalues(snapshot.members):
            if member_selector(member):
                members.append(member)
        return members

    def size(self):
        """
        Returns the size of the cluster.

        :return: (int), size of the cluster.
        """
        snapshot = self._member_list_snapshot
        return len(snapshot.members)

    def get_local_client(self):
        """
        Returns the info representing the local client.

        :return: (:class: `~hazelcast.cluster.ClientInfo`), client info
        """
        connection_manager = self._connection_manager
        connection = connection_manager.get_random_connection()
        local_address = None if not connection else connection.local_address
        return ClientInfo(connection_manager.client_uuid, local_address, self._client.name, self._labels)

    def add_listener(self, member_added=None, member_removed=None, fire_for_existing=False):
        registration_id = str(uuid.uuid4())
        self._listeners[registration_id] = (member_added, member_removed)

        if fire_for_existing and member_added:
            snapshot = self._member_list_snapshot
            for member in six.itervalues(snapshot.members):
                member_added(member)

        return registration_id

    def remove_listener(self, registration_id):
        """
        Removes the specified membership listener.

        :param registration_id: (str), registration id of the listener to be deleted.
        :return: (bool), if the registration is removed, ``false`` otherwise.
        """
        try:
            self._listeners.pop(registration_id)
            return True
        except KeyError:
            return False

    def wait_initial_member_list_fetched(self):
        """
        Blocks until the initial member list is fetched from the cluster.
        If it is not received within the timeout, an error is raised.

        :raises IllegalStateError: If the member list could not be fetched
        """
        fetched = self._initial_list_fetched.wait(_INITIAL_MEMBERS_TIMEOUT_SECONDS)
        if not fetched:
            raise IllegalStateError("Could not get initial member list from cluster!")

    def clear_member_list_version(self):
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug("Resetting the member list version", extra=self._logger_extras)

        current = self._member_list_snapshot
        if current is not _EMPTY_SNAPSHOT:
            self._member_list_snapshot = _MemberListSnapshot(0, current.members)

    def handle_members_view_event(self, version, member_infos):
        snapshot = self._create_snapshot(version, member_infos)
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug("Handling new snapshot with membership version: %s, member string: %s"
                         % (version, self._members_string(snapshot)), extra=self._logger_extras)

        current = self._member_list_snapshot
        if version >= current.version:
            self._apply_new_state_and_fire_events(current, snapshot)

        if current is _EMPTY_SNAPSHOT:
            self._initial_list_fetched.set()

    def _apply_new_state_and_fire_events(self, current, snapshot):
        self._member_list_snapshot = snapshot
        removals, additions = self._detect_membership_events(current, snapshot)

        # Removal events should be fired first
        for removed_member in removals:
            for _, handler in six.itervalues(self._listeners):
                if handler:
                    try:
                        handler(removed_member)
                    except:
                        self.logger.exception("Exception in membership lister", extra=self._logger_extras)

        for added_member in additions:
            for handler, _ in six.itervalues(self._listeners):
                if handler:
                    try:
                        handler(added_member)
                    except:
                        self.logger.exception("Exception in membership lister", extra=self._logger_extras)

    def _detect_membership_events(self, old, new):
        new_members = []
        dead_members = set(six.itervalues(old.members))
        for member in six.itervalues(new.members):
            try:
                dead_members.remove(member)
            except KeyError:
                new_members.append(member)

        for dead_member in dead_members:
            connection = self._connection_manager.get_connection(dead_member.uuid)
            if connection:
                connection.close(None, TargetDisconnectedError("The client has closed the connection to this member, "
                                                               "after receiving a member left event from the cluster. "
                                                               "%s" % connection))

        if (len(new_members) + len(dead_members)) > 0:
            if len(new.members) > 0:
                self.logger.info(self._members_string(new), extra=self._logger_extras)

        return dead_members, new_members

    @staticmethod
    def _members_string(snapshot):
        members = snapshot.members
        n = len(members)
        return "\n\nMembers [%s] {\n\t%s\n}\n" % (n, "\n\t".join(map(str, six.itervalues(members))))

    @staticmethod
    def _create_snapshot(version, member_infos):
        new_members = OrderedDict()
        for member_info in member_infos:
            new_members[member_info.uuid] = member_info
        return _MemberListSnapshot(version, new_members)


class AbstractLoadBalancer(object):
    """Load balancer allows you to send operations to one of a number of endpoints (Members).
    It is up to the implementation to use different load balancing policies.

    If the client is configured with smart routing,
    only the operations that are not key based will be routed to the endpoint
    returned by the load balancer. If it is not, the load balancer will not be used.
    """
    def __init__(self):
        self._cluster_service = None
        self._members = []

    def init(self, cluster_service, config):
        """
        Initializes the load balancer.

        :param cluster_service: (:class:`~hazelcast.cluster.ClusterService`), The cluster service to select members from
        :param config: (:class:`~hazelcast.config.ClientConfig`), The client config
        :return:
        """
        self._cluster_service = cluster_service
        cluster_service.add_listener(self._listener, self._listener, True)

    def next(self):
        """
        Returns the next member to route to.
        :return: (:class:`~hazelcast.core.Member`), Returns the next member or None if no member is available
        """
        raise NotImplementedError("next")

    def _listener(self, _):
        self._members = self._cluster_service.get_members()


class RoundRobinLB(AbstractLoadBalancer):
    """A load balancer implementation that relies on using round robin
    to a next member to send a request to.

    Round robin is done based on best effort basis, the order of members for concurrent calls to
    the next() is not guaranteed.
    """

    def __init__(self):
        super(RoundRobinLB, self).__init__()
        self._idx = 0

    def next(self):
        members = self._members
        if not members:
            return None

        n = len(members)
        idx = self._idx % n
        self._idx += 1
        return members[idx]


class RandomLB(AbstractLoadBalancer):
    """A load balancer that selects a random member to route to.
    """

    def next(self):
        members = self._members
        if not members:
            return None
        idx = random.randrange(0, len(members))
        return members[idx]


class VectorClock(object):
    """
    Vector clock consisting of distinct replica logical clocks.

    See https://en.wikipedia.org/wiki/Vector_clock
    The vector clock may be read from different thread but concurrent
    updates must be synchronized externally. There is no guarantee for
    concurrent updates.
    """

    def __init__(self):
        self._replica_timestamps = {}

    def is_after(self, other):
        """
        Returns true if this vector clock is causally strictly after the
        provided vector clock. This means that it the provided clock is neither
        equal to, greater than or concurrent to this vector clock.

        :param other: (:class:`~hazelcast.cluster.VectorClock`), Vector clock to be compared
        :return: (bool), True if this vector clock is strictly after the other vector clock, False otherwise
        """
        any_timestamp_greater = False
        for replica_id, other_timestamp in other.entry_set():
            local_timestamp = self._replica_timestamps.get(replica_id)

            if local_timestamp is None or local_timestamp < other_timestamp:
                return False
            elif local_timestamp > other_timestamp:
                any_timestamp_greater = True

        # there is at least one local timestamp greater or local vector clock has additional timestamps
        return any_timestamp_greater or other.size() < self.size()

    def set_replica_timestamp(self, replica_id, timestamp):
        """
        Sets the logical timestamp for the given replica ID.

        :param replica_id: (str), Replica ID.
        :param timestamp: (int), Timestamp for the given replica ID.
        """
        self._replica_timestamps[replica_id] = timestamp

    def entry_set(self):
        """
        Returns the entry set of the replica timestamps in a format
        of list of tuples. Each tuple contains the replica ID and the
        timestamp associated with it.

        :return: (list), List of tuples.
        """
        return list(self._replica_timestamps.items())

    def size(self):
        """
        Returns the number of timestamps that are in the
        replica timestamps dictionary.

        :return: (int), Number of timestamps in the replica timestamps.
        """
        return len(self._replica_timestamps)
