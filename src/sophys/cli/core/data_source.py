import enum
import logging
import typing

import numpy as np


class DataSource:
    # TODO: Move these definitions to extensions
    class DataType(enum.StrEnum):
        DETECTORS = "detector"
        MAIN_DETECTOR = "main_detector"
        BEFORE = "before"
        DURING = "during"
        AFTER = "after"

        METADATA = "metadata"

    def __init__(self):
        self._logger = logging.getLogger("sophys_cli.data_source")

    def get(self, type: DataType) -> np.array:
        raise NotImplementedError

    def add(self, type: DataType, *values: typing.Iterable[str]):
        raise NotImplementedError

    def remove(self, type: DataType, *values: typing.Iterable[str]):
        raise NotImplementedError


class LocalInMemoryDataSource(DataSource):
    """Data source backed by an in-memory dictionary."""

    def __init__(self):
        super().__init__()

        self._data_source: dict[str, set] = dict()

    def get(self, type: DataSource.DataType) -> np.array:
        return np.array(list(self._data_source.get(type, [])))

    def add(self, type: DataSource.DataType, *values: typing.Iterable[str]):
        if type not in self._data_source:
            self._data_source[type] = {*values}
            return

        self._data_source[type].update({*values})

    def remove(self, type: DataSource.DataType, *values: typing.Iterable[str]):
        if type not in self._data_source:
            return

        self._data_source[type].difference_update({*values})


class LocalFileDataSource(DataSource):
    """Data source backed by a local CSV file."""

    def __init__(self, path: str):
        super().__init__()

        try:
            import pandas as pd
        except ImportError:
            self._logger.critical("Could not import pandas, required by LocalFileDataSource.", exc_info=True)

        assert path.endswith(".csv"), "LocalFileDataSource only accepts CSV files."

        self._file_contents = pd.read_csv(path)

    def get(self, type: DataSource.DataType) -> np.array:
        return self._file_contents.loc[self._file_contents.type == type]["name"].to_numpy()


class RedisDataSource(DataSource):
    """Data source backed by a remote Redis server."""

    def _data_type_to_redis_key(self, type: DataSource.DataType) -> str:
        match type:
            case DataSource.DataType.DETECTORS:
                return "sophys_detectors"
            case DataSource.DataType.MAIN_DETECTOR:
                return "sophys_detectors_main"
            case DataSource.DataType.BEFORE:
                return "sophys_metadata_read_before"
            case DataSource.DataType.DURING:
                return "sophys_metadata_read_during"
            case DataSource.DataType.AFTER:
                return "sophys_metadata_read_after"
            case _:
                raise KeyError(f"No redis key found for type {type}.")

    def __init__(self, host: str, port: int):
        super().__init__()

        try:
            import redis
        except ImportError:
            self._logger.critical("Could not import redis, required by RedisDataSource", exc_info=True)

        self._redis = redis.Redis(host=host, port=port, decode_responses=True)

    def get(self, type: DataSource.DataType) -> np.array:
        redis_key = self._data_type_to_redis_key(type)
        if len(self._redis.keys(redis_key)) == 0:
            return np.array([])

        return np.array(list(self._redis.smembers(redis_key)))

    def add(self, type: DataSource.DataType, *values: typing.Iterable[str]):
        redis_key = self._data_type_to_redis_key(type)
        self._redis.sadd(redis_key, *values)

    def remove(self, type: DataSource.DataType, *values: typing.Iterable[str]):
        redis_key = self._data_type_to_redis_key(type)
        self._redis.srem(redis_key, *values)
