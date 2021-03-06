import hazelcast

from hazelcast.serialization.predicate import is_between

client = hazelcast.HazelcastClient()

predicate_map = client.get_map("predicate-map")
for i in range(10):
    predicate_map.put("key" + str(i), i)

predicate = is_between("this", 3, 5)

entry_set = predicate_map.entry_set(predicate).result()

for key, value in entry_set:
    print("{} -> {}".format(key, value))

client.shutdown()
