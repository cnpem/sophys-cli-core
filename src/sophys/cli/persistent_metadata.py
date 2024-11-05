from .data_source import DataSource


class PersistentMetadata:
    """Simple container wrapping DataSource to provide (semi)permanent metadata support."""

    def __init__(self, data_source: DataSource):
        self._data_source = data_source
        self._keys = dict()

    def add_entry(self, key: str, value: str) -> None:
        if key in self._keys:
            self.remove_entry(key)

        composed_key = f"{str(key)}={str(value)}"
        self._keys[key] = composed_key
        self._data_source.add(DataSource.DataType.METADATA, composed_key)

    def remove_entry(self, key: str) -> None:
        composed_key = self._keys.get(key, None)
        if composed_key is None:
            return

        self._data_source.remove(DataSource.DataType.METADATA, composed_key)
        del self._keys[key]

    def list_entries(self):
        return self._data_source.get(DataSource.DataType.METADATA)

    def list_key_value_pairs(self):
        return [i.split('=') for i in self.list_entries()]

    def pretty_print_entries(self, logger=print):
        key_val_pairs = self.list_key_value_pairs()
        biggest_key_length = max(len(i) for i, _ in key_val_pairs)

        for key, value in self.list_key_value_pairs():
            logger(f"  {key:<{biggest_key_length + 1}}: {value}")

    def populate_permanent_md(self, *_, md):
        return md.update({key: val for key, val in self.list_key_value_pairs()})
