from hazelcast.protocol.codec import \
    queue_add_all_codec, \
    queue_add_listener_codec, \
    queue_clear_codec, \
    queue_compare_and_remove_all_codec, \
    queue_compare_and_retain_all_codec, \
    queue_contains_all_codec, \
    queue_contains_codec, \
    queue_drain_to_max_size_codec, \
    queue_is_empty_codec, \
    queue_iterator_codec, \
    queue_offer_codec, \
    queue_peek_codec, \
    queue_poll_codec, \
    queue_put_codec, \
    queue_remaining_capacity_codec, \
    queue_remove_codec, \
    queue_remove_listener_codec, \
    queue_size_codec, \
    queue_take_codec
from hazelcast.proxy.base import PartitionSpecificProxy, ItemEvent, ItemEventType
from hazelcast.util import check_not_none, to_millis, ImmutableLazyDataList


class Empty(Exception):
    pass


class Full(Exception):
    pass


class Queue(PartitionSpecificProxy):
    """
    Concurrent, blocking, distributed, observable queue. Queue is not a partitioned data-structure. All of the Queue
    content is stored in a single machine (and in the backup). Queue will not scale by adding more members
    in the cluster.
    """
    def add(self, item):
        """
        Adds the specified item to this queue if there is available space.

        :param item: (object), the specified item.
        :return: (bool), ``true`` if element is successfully added, ``false`` otherwise.
        """
        def result_fnc(f):
            if f.result():
                return True
            raise Full("Queue is full!")

        return self.offer(item).continue_with(result_fnc)

    def add_all(self, items):
        """
        Adds the elements in the specified collection to this queue.

        :param items: (Collection), collection which includes the items to be added.
        :return: (bool), ``true`` if this queue is changed after call, ``false`` otherwise.
        """
        check_not_none(items, "Value can't be None")
        data_items = []
        for item in items:
            check_not_none(item, "Value can't be None")
            data_items.append(self._to_data(item))

        request = queue_add_all_codec.encode_request(self.name, data_items)
        return self._invoke(request, queue_add_all_codec.decode_response)

    def add_listener(self, include_value=False, item_added_func=None, item_removed_func=None):
        """
        Adds an item listener for this queue. Listener will be notified for all queue add/remove events.

        :param include_value: (bool), whether received events include the updated item or not (optional).
        :param item_added_func: Function to be called when an item is added to this set (optional).
        :param item_removed_func: Function to be called when an item is deleted from this set (optional).
        :return: (str), a registration id which is used as a key to remove the listener.
        """
        codec = queue_add_listener_codec
        request = codec.encode_request(self.name, include_value, self._is_smart)

        def handle_event_item(item, uuid, event_type):
            item = item if include_value else None
            member = self._context.cluster_service.get_member(uuid)

            item_event = ItemEvent(self.name, item, event_type, member, self._to_object)
            if event_type == ItemEventType.added:
                if item_added_func:
                    item_added_func(item_event)
            else:
                if item_removed_func:
                    item_removed_func(item_event)

        return self._register_listener(request, lambda r: codec.decode_response(r),
                                       lambda reg_id: queue_remove_listener_codec.encode_request(self.name, reg_id),
                                       lambda m: codec.handle(m, handle_event_item))

    def clear(self):
        """
        Clears this queue. Queue will be empty after this call.
        """
        request = queue_clear_codec.encode_request(self.name)
        return self._invoke(request)

    def contains(self, item):
        """
        Determines whether this queue contains the specified item or not.

        :param item: (object), the specified item to be searched.
        :return: (bool), ``true`` if the specified item exists in this queue, ``false`` otherwise.
        """
        check_not_none(item, "Item can't be None")
        item_data = self._to_data(item)
        request = queue_contains_codec.encode_request(self.name, item_data)
        return self._invoke(request, queue_contains_codec.decode_response)

    def contains_all(self, items):
        """
        Determines whether this queue contains all of the items in the specified collection or not.

        :param items: (Collection), the specified collection which includes the items to be searched.
        :return: (bool), ``true`` if all of the items in the specified collection exist in this queue, ``false`` otherwise.
        """
        check_not_none(items, "Items can't be None")
        data_items = []
        for item in items:
            check_not_none(item, "item can't be None")
            data_items.append(self._to_data(item))

        request = queue_contains_all_codec.encode_request(self.name, data_items)
        return self._invoke(request, queue_contains_all_codec.decode_response)

    def drain_to(self, target_list, max_size=-1):
        """
        Transfers all available items to the given `target_list` and removes these items from this queue. If a max_size is
        specified, it transfers at most the given number of items. In case of a failure, an item can exist in both
        collections or none of them.

        This operation may be more efficient than polling elements repeatedly and putting into collection.

        :param target_list: (`list`), the list where the items in this queue will be transferred.
        :param max_size: (int), the maximum number items to transfer (optional).
        :return: (int), number of transferred items.

        """
        def handler(message):
            response = queue_drain_to_max_size_codec.decode_response(message)
            target_list.extend(map(self._to_object, response))
            return len(response)
        
        request = queue_drain_to_max_size_codec.encode_request(self.name, max_size)
        return self._invoke(request, handler)

    def iterator(self):
        """
        Returns all of the items in this queue.

        :return: (Sequence), collection of items in this queue.
        """
        def handler(message):
            return ImmutableLazyDataList(queue_iterator_codec.decode_response(message), self._to_object)

        request = queue_iterator_codec.encode_request(self.name)
        return self._invoke(request, handler)

    def is_empty(self):
        """
        Determines whether this set is empty or not.

        :return: (bool), ``true`` if this queue is empty, ``false`` otherwise.
        """
        request = queue_is_empty_codec.encode_request(self.name)
        return self._invoke(request, queue_is_empty_codec.decode_response)

    def offer(self, item, timeout=0):
        """
        Inserts the specified element into this queue if it is possible to do so immediately without violating capacity
        restrictions. Returns ``true`` upon success. If there is no space currently available:
            * If a timeout is provided, it waits until this timeout elapses and returns the result.
            * If a timeout is not provided, returns ``false`` immediately.

        :param item: (object), the item to be added.
        :param timeout: (long), maximum time in seconds to wait for addition (optional).
        :return: (bool), ``true`` if the element was added to this queue, ``false`` otherwise.
        """
        check_not_none(item, "Value can't be None")
        element_data = self._to_data(item)
        request = queue_offer_codec.encode_request(self.name, element_data, to_millis(timeout))
        return self._invoke(request, queue_offer_codec.decode_response)

    def peek(self):
        """
        Retrieves the head of queue without removing it from the queue. If the queue is empty, returns ``None``.

        :return: (object), the head of this queue, or ``None`` if this queue is empty.
        """
        def handler(message):
            return self._to_object(queue_peek_codec.decode_response(message))

        request = queue_peek_codec.encode_request(self.name)
        return self._invoke(request, handler)

    def poll(self, timeout=0):
        """
        Retrieves and removes the head of this queue, if this queue is empty:
            * If a timeout is provided, it waits until this timeout elapses and returns the result.
            * If a timeout is not provided, returns ``None``.

        :param timeout: (long), maximum time in seconds to wait for addition (optional).
        :return: (object), the head of this queue, or ``None`` if this queue is empty or specified timeout elapses before an
        item is added to the queue.
        """
        def handler(message):
            return self._to_object(queue_poll_codec.decode_response(message))

        request = queue_poll_codec.encode_request(self.name, to_millis(timeout))
        return self._invoke(request, handler)

    def put(self, item):
        """
        Adds the specified element into this queue. If there is no space, it waits until necessary space becomes
        available.

        :param item: (object), the specified item.
        """
        check_not_none(item, "Value can't be None")
        element_data = self._to_data(item)
        request = queue_put_codec.encode_request(self.name, element_data)
        return self._invoke(request)

    def remaining_capacity(self):
        """
        Returns the remaining capacity of this queue.

        :return: (int), remaining capacity of this queue.
        """
        request = queue_remaining_capacity_codec.encode_request(self.name)
        return self._invoke(request, queue_remaining_capacity_codec.decode_response)

    def remove(self, item):
        """
        Removes the specified element from the queue if it exists.

        :param item: (object), the specified element to be removed.
        :return: (bool), ``true`` if the specified element exists in this queue.
        """
        check_not_none(item, "Value can't be None")
        item_data = self._to_data(item)
        request = queue_remove_codec.encode_request(self.name, item_data)
        return self._invoke(request, queue_remove_codec.decode_response)

    def remove_all(self, items):
        """
        Removes all of the elements of the specified collection from this queue.

        :param items: (Collection), the specified collection.
        :return: (bool), ``true`` if the call changed this queue, ``false`` otherwise.
        """
        check_not_none(items, "Value can't be None")
        data_items = []
        for item in items:
            check_not_none(item, "Value can't be None")
            data_items.append(self._to_data(item))

        request = queue_compare_and_remove_all_codec.encode_request(self.name, data_items)
        return self._invoke(request, queue_compare_and_remove_all_codec.decode_response)

    def remove_listener(self, registration_id):
        """
        Removes the specified item listener. Returns silently if the specified listener was not added before.

        :param registration_id: (str), id of the listener to be deleted.
        :return: (bool), ``true`` if the item listener is removed, ``false`` otherwise.
        """
        return self._deregister_listener(registration_id)

    def retain_all(self, items):
        """
        Removes the items which are not contained in the specified collection. In other words, only the items that
        are contained in the specified collection will be retained.

        :param items: (Collection), collection which includes the elements to be retained in this set.
        :return: (bool), ``true`` if this queue changed as a result of the call.
        """
        check_not_none(items, "Value can't be None")
        data_items = []
        for item in items:
            check_not_none(item, "Value can't be None")
            data_items.append(self._to_data(item))
        request = queue_compare_and_retain_all_codec.encode_request(self.name, data_items)
        return self._invoke(request, queue_compare_and_retain_all_codec.decode_response)

    def size(self):
        """
        Returns the number of elements in this collection. If the size is greater than sys.maxint, it returns
        sys.maxint.

        :return: (int), size of the queue.
        """
        request = queue_size_codec.encode_request(self.name)
        return self._invoke(request, queue_size_codec.decode_response)

    def take(self):
        """
        Retrieves and removes the head of this queue, if necessary, waits until an item becomes available.

        :return: (object), the head of this queue.
        """
        def handler(message):
            return self._to_object(queue_take_codec.decode_response(message))

        request = queue_take_codec.encode_request(self.name)
        return self._invoke(request, handler)
