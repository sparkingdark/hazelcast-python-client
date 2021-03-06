import logging

from hazelcast.errors import ClientOfflineError
from hazelcast.hash import hash_to_index


class _PartitionTable(object):
    __slots__ = ("connection", "version", "partitions")

    def __init__(self, connection, version, partitions):
        self.connection = connection
        self.version = version
        self.partitions = partitions

    def __repr__(self):
        return "PartitionTable(connection=%s, version=%s)" % (self.connection, self.version)


class PartitionService(object):
    """
    Allows to retrieve information about the partition count, the partition owner or the partitionId of a key.
    """

    def __init__(self, internal_partition_service):
        self._service = internal_partition_service

    def get_partition_owner(self, partition_id):
        """
        Returns the owner of the partition if it's set, ``None`` otherwise.

        :param partition_id: The partition id.
        :type partition_id: int

        :return: Owner of partition
        :rtype: :class:`uuid.UUID`
        """
        return self._service.get_partition_owner(partition_id)

    def get_partition_id(self, key_data):
        """
        Returns the partition id for a key data.

        :param key_data: The key data.
        :type key_data: :class:`~hazelcast.serialization.data.Data`

        :return: The partition id.
        :rtype: int
        """
        return self._service.get_partition_id(key_data)

    def get_partition_count(self):
        """
        Returns partition count of the connected cluster.

        If partition table is not fetched yet, this method returns ``0``.

        :return: The partition count
        :rtype: int
        """
        return self._service.partition_count


class _InternalPartitionService(object):
    logger = logging.getLogger("HazelcastClient.PartitionService")

    def __init__(self, client, logger_extras):
        self.partition_count = 0
        self._client = client
        self._logger_extras = logger_extras
        self._partition_table = _PartitionTable(None, -1, dict())

    def handle_partitions_view_event(self, connection, partitions, version):
        """Handles the incoming partition view event and updates the partition table
        if it is not empty, coming from a new connection or not stale.
        """
        should_log = self.logger.isEnabledFor(logging.DEBUG)
        if should_log:
            self.logger.debug("Handling new partition table with version: %s" % version,
                              extra=self._logger_extras)

        table = self._partition_table
        if not self._should_be_applied(connection, partitions, version, table, should_log):
            return

        new_partitions = self._prepare_partitions(partitions)
        new_table = _PartitionTable(connection, version, new_partitions)
        self._partition_table = new_table

    def get_partition_owner(self, partition_id):
        table = self._partition_table
        return table.partitions.get(partition_id, None)

    def get_partition_id(self, key):
        count = self.partition_count
        if count == 0:
            # Partition count can not be zero for the SYNC mode.
            # On the SYNC mode, we are waiting for the first connection to be established.
            # We are initializing the partition count with the value coming from the server with authentication.
            # This error is used only for ASYNC mode client.
            raise ClientOfflineError()

        return hash_to_index(key.get_partition_hash(), count)

    def check_and_set_partition_count(self, partition_count):
        """
        :param partition_count: (int)
        :return: (bool), True if partition count can be set for the first time,
            or it is equal to one that is already available, returns False otherwise
        """
        if self.partition_count == 0:
            self.partition_count = partition_count
            return True
        return self.partition_count == partition_count

    def _should_be_applied(self, connection, partitions, version, current, should_log):
        if not partitions:
            if should_log:
                self.logger.debug("Partition view will not be applied since response is empty. "
                                  "Sending connection: %s, version: %s, current table: %s"
                                  % (connection, version, current),
                                  extra=self._logger_extras)
            return False

        if connection != current.connection:
            if should_log:
                self.logger.debug("Partition view event coming from a new connection. Old: %s, new: %s"
                                  % (current.connection, connection), extra=self._logger_extras)
            return True

        if version <= current.version:
            if should_log:
                self.logger.debug("Partition view will not be applied since response state version is older. "
                                  "Sending connection: %s, version: %s, current table: %s"
                                  % (connection, version, current),
                                  extra=self._logger_extras)
            return False

        return True

    @staticmethod
    def _prepare_partitions(partitions):
        new_partitions = dict()
        for uuid, partition_list in partitions:
            for partition in partition_list:
                new_partitions[partition] = uuid
        return new_partitions


def string_partition_strategy(key):
    if key is None:
        return None
    try:
        index_of = key.index('@')
        return key[index_of + 1:]
    except ValueError:
        return key
