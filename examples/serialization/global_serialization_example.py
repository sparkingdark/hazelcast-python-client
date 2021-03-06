import hazelcast

# We are using six.moves.cPickle to support both Python 2 and Python 3.
# You can use cPickle for Python 2 or pickle for Python 3
from hazelcast.six.moves import cPickle
from hazelcast.serialization.api import StreamSerializer


class ColorGroup(object):
    def __init__(self, id, name, colors):
        self.id = id
        self.name = name
        self.colors = colors


class GlobalSerializer(StreamSerializer):
    GLOBAL_SERIALIZER_ID = 5  # Should be greater than 0 and unique to each serializer

    def __init__(self):
        super(GlobalSerializer, self).__init__()

    def read(self, inp):
        utf = inp.read_utf()
        obj = cPickle.loads(utf.encode())
        return obj

    def write(self, out, obj):
        out.write_utf(cPickle.dumps(obj, 0).decode("utf-8"))

    def get_type_id(self):
        return self.GLOBAL_SERIALIZER_ID

    def destroy(self):
        pass


config = hazelcast.ClientConfig()
config.serialization.global_serializer = GlobalSerializer

client = hazelcast.HazelcastClient(config)

group = ColorGroup(id=1, name="Reds",
                   colors=["Crimson", "Red", "Ruby", "Maroon"])

my_map = client.get_map("map")

my_map.put("group1", group)

color_group = my_map.get("group1").result()

print("ID: {}\nName: {}\nColor: {}".format(color_group.id,
                                           color_group.name,
                                           color_group.colors))

client.shutdown()
