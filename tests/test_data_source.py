import pytest

import numpy as np

from sophys.cli.core.data_source import DataSource, LocalInMemoryDataSource, RedisDataSource


data_sources_list = (LocalInMemoryDataSource, RedisDataSource)


@pytest.fixture(params=data_sources_list)
def data_source(request, tmp_path, mocker):
    args = ()
    if request.param == RedisDataSource:
        args = ("localhost", "0")

        # Mocked Redis object
        _redis_backend = dict()

        def keys(_r, x):
            return list(i for i in _redis_backend.keys() if i == x)

        def smembers(_r, x):
            return np.array(list(_redis_backend.get(x, [])))

        def sadd(_r, x, *a):
            _redis_backend[x] = set(a)

        def srem(_r, x, *a):
            _redis_backend[x].difference_update(set(a))

        import redis
        redis.Redis.__init__ = lambda *a, **k: None
        redis.Redis.keys = keys
        redis.Redis.smembers = smembers
        redis.Redis.sadd = sadd
        redis.Redis.srem = srem

    return (request.param)(*args)


def test_add_get_simple(data_source: DataSource):
    original_data = ("123", "456", "789")
    data_source.add(DataSource.DataType.DETECTORS, *original_data)
    data = tuple(sorted(data_source.get(DataSource.DataType.DETECTORS)))

    assert data == original_data


def test_add_get_duplicated(data_source: DataSource):
    original_data = ("123",)
    data_source.add(DataSource.DataType.DETECTORS, *original_data)
    data = tuple(sorted(data_source.get(DataSource.DataType.DETECTORS)))

    assert data == original_data

    data_source.add(DataSource.DataType.DETECTORS, *original_data)
    data = tuple(sorted(data_source.get(DataSource.DataType.DETECTORS)))

    assert data == original_data


def test_add_remove(data_source: DataSource):
    data_source.add(DataSource.DataType.DETECTORS, "123", "456")
    data_source.remove(DataSource.DataType.DETECTORS, "123")
    data = tuple(sorted(data_source.get(DataSource.DataType.DETECTORS)))

    assert data == ("456",)
