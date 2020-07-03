from hazelcast.serialization.api import IdentifiedDataSerializable

FACTORY_ID = -41


class AbstractAggregator(IdentifiedDataSerializable):
    attribute_path: str

    def __init__(self, attribute_path):
        self.attribute_path = attribute_path

    def get_factory_id(self):
        return FACTORY_ID

    def get_class_id(self):
        raise NotImplementedError("get_class_id not implemented!!!")

    def read_data(self, input):
        raise NotImplementedError("read_data not implemented!!!")

    def write_data(self, output):
        raise NotImplementedError("write_data not implemented!!!")


class CountAggregator(AbstractAggregator):
    CLASS_ID = 4

    def get_class_id(self):
        return self.CLASS_ID

    def read_data(self, input):
        self.attribute_path = input.read_utf()
        input.read_long(self)

    def write_data(self, output):
        output.write_utf(self.attribute_path)
        output.write_long(0)


class FloatAverageAggregator(AbstractAggregator):
    CLASS_ID = 6

    def get_class_id(self):
        return self.CLASS_ID

    def read_data(self, input):
        self.attribute_path = input.read_utf()
        input.read_double(self)
        input.read_long(self)

    def write_data(self, output):
        output.write_utf(self.attribute_path)
        output.write_double(0)
        output.write_long(0)


class FloatSumAggregator(AbstractAggregator):
    CLASS_ID = 7

    def get_class_id(self):
        return self.CLASS_ID

    def read_data(self, input):
        self.attribute_path = input.read_utf()
        input.read_double(self)

    def write_data(self, output):
        output.write_utf(self.attribute_path)
        output.write_double(0)


class AverageAggregator(AbstractAggregator):
    CLASS_ID = 16

    def get_class_id(self):
        return self.CLASS_ID

    def read_data(self, input):
        self.attribute_path = input.read_utf()
        input.read_long(self)
        input.read_long(self)

    def write_data(self, output):
        output.write_utf(self.attribute_path)
        output.write_long(0)
        output.write_long(0)


class FixedPointSumAggregator(AbstractAggregator):
    CLASS_ID = 8

    def get_class_id(self):
        return self.CLASS_ID

    def read_data(self, input):
        self.attribute_path = input.read_utf()
        input.read_long(self)

    def write_data(self, output):
        output.write_utf(self.attribute_path)
        output.write_long(0)


class FloatingPointSumAggregator(AbstractAggregator):
    CLASS_ID = 9

    def get_class_id(self):
        return self.CLASS_ID

    def read_data(self, input):
        self.attribute_path = input.read_utf()
        input.read_double(self)

    def write_data(self, output):
        output.write_utf(self.attribute_path)
        output.write_long(0)


class MaxAggregator(AbstractAggregator):
    CLASS_ID = 14

    def get_class_id(self):
        return self.CLASS_ID

    def read_data(self, input):
        self.attribute_path = input.read_utf()
        input.read_object(self)

    def write_data(self, output):
        output.write_utf(self.attribute_path)
        output.write_object(0)


class MinAggregator(AbstractAggregator):
    CLASS_ID = 15

    def get_class_id(self):
        return self.CLASS_ID

    def read_data(self, input):
        self.attribute_path = input.read_utf()
        input.read_object(self)

    def write_data(self, output):
        output.write_utf(self.attribute_path)
        output.write_object(0)


class SumAggregator(AbstractAggregator):
    CLASS_ID = 11

    def get_class_id(self):
        return self.CLASS_ID

    def read_data(self, input):
        self.attribute_path = input.read_utf()
        input.read_long(self)

    def write_data(self, output):
        output.write_utf(self.attribute_path)
        output.write_long(0)


class MaxByAggregator(AbstractAggregator):

    CLASS_ID = 17

    def get_class_id(self):
        return self.CLASS_ID

    def read_data(self, input):
        self.attribute_path = input.read_utf()
        input.read_object(self)
        input.read_object(self)

    def write_data(self, output):
        output.write_utf(self.attribute_path)
        output.write_object(0)
        output.write_object(0)


class MinByAggregator(AbstractAggregator):

    CLASS_ID = 18

    def get_class_id(self):
        return self.CLASS_ID

    def read_data(self, input):
        self.attribute_path = input.read_utf()
        input.read_object(self)
        input.read_object(self)

    def write_data(self, output):
        output.write_utf(self.attribute_path)
        output.write_object(0)
        output.write_object(0)


class DistinctValuesAggregator(AbstractAggregator):

    CLASS_ID = 5

    def get_class_id(self):
        return self.CLASS_ID

    values = set()

    def read_data(self, input):

        self.attribute_path = input.read_utf()
        count = input.read_int
        for _ in range(0, count):
            value = input.read_object()
            self.values.add(value)

    def write_data(self, output):
        output.write_utf(self.attribute_path)
        output.write_int(len(self.values))
        for value in self.values:
            output.write_object(value)

class CanonicalizingHashSet(AbstractAggregator):

    CLASS_ID = 19
"""
    def get_class_id(self):
        return self.CLASS_ID

    def read_data(self, input):
        

    def write_data(self, output):
"""