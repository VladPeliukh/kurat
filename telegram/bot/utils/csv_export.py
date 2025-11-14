from __future__ import annotations

import csv
from collections.abc import Iterable, Sequence
from io import StringIO


def build_simple_table_csv(
    headers: Sequence[object],
    rows: Iterable[Sequence[object]],
    *,
    delimiter: str = ";",
    include_bom: bool = True,
) -> bytes:
    """Serialize headers and rows into CSV bytes suitable for spreadsheet apps."""
    buffer = StringIO()
    writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\r\n")

    if headers:
        writer.writerow(headers)
    for row in rows:
        writer.writerow(row)

    data = buffer.getvalue()
    if include_bom:
        data = "\ufeff" + data
    return data.encode("utf-8")


__all__ = ["build_simple_table_csv"]
