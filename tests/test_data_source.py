import pytest

from sophys.cli.core.data_source import DataSource, LocalInMemoryDataSource, RedisDataSource


data_sources_list = (LocalInMemoryDataSource, RedisDataSource)


@pytest.fixture(params=data_sources_list)
def data_source(request):
    args = ()

    if request.param == RedisDataSource:
        args = ("localhost", 12345)

        import fakeredis
        from threading import Thread

        redis_server = fakeredis.TcpFakeServer(args, server_type="redis", bind_and_activate=False)
        redis_server.daemon_threads = True
        redis_server.allow_reuse_address = True
        redis_server.server_bind()
        redis_server.server_activate()

        redis_server_thread = Thread(target=redis_server.serve_forever, args=(0.05,), daemon=True)
        redis_server_thread.start()

    yield (request.param)(*args)

    if request.param == RedisDataSource:
        redis_server.shutdown()
        redis_server.server_close()
        redis_server_thread.join()


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
