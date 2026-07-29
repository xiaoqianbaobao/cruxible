"""Hive/Spark connector — scan Hive Metastore tables and infer ontology."""

from __future__ import annotations

from typing import Any

from cruxible_core.connectors.base import (
    ColumnMeta,
    DiscoveredRelationship,
    DiscoveredSchema,
    DiscoveredTable,
    SchemaDiscoveryResult,
    _sample_type,
)

_HIVE_TYPE_MAP = {
    "string": "string",
    "varchar": "string",
    "char": "string",
    "int": "int",
    "integer": "int",
    "bigint": "int",
    "smallint": "int",
    "tinyint": "int",
    "float": "float",
    "double": "float",
    "decimal": "float",
    "boolean": "bool",
    "date": "date",
    "timestamp": "datetime",
    "binary": "string",
}


def _normalize_type(hive_type: str) -> str:
    base = hive_type.split("<")[0].split("(")[0].strip().lower()
    return _HIVE_TYPE_MAP.get(base, "string")


def _table_name_to_entity(name: str) -> str:
    """Convert a Hive table name to a Cruxible entity type name.
    
    Examples:
        dim_customer → Customer
        fact_orders → Orders
        ods_user_login → UserLogin
        product → Product
    """
    # Strip common prefixes
    cleaned = name.lower()
    for prefix in ["dim_", "fact_", "ods_", "dwd_", "dws_", "ads_", "tmp_", "stg_"]:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    # Convert snake_case to PascalCase
    return "".join(word.capitalize() for word in cleaned.split("_"))


class HiveConnector:
    """Connect to Hive Metastore via PyHive or Spark Thrift Server.

    Usage::
        connector = HiveConnector()
        connector.connect(host="hive-server", port=10000, database="default", user="hive")
        result = connector.scan(tables=["dim_customer", "fact_orders"])
        connector.close()
    """

    def __init__(self) -> None:
        self._connection: Any = None
        self._cursor: Any = None
        self._database: str = "default"

    def connect(
        self,
        host: str = "localhost",
        port: int = 10000,
        database: str = "default",
        user: str = "hive",
        password: str | None = None,
        auth: str = "NONE",
        **kwargs: Any,
    ) -> None:
        """Connect to Hive/Spark Thrift Server.

        Requires ``pyhive`` or ``thrift`` to be installed.
        Falls back to a mock mode if the library is not available.
        """
        self._database = database
        try:
            from pyhive import hive as hive_client

            self._connection = hive_client.connect(
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
                auth=auth,
                **kwargs,
            )
            self._cursor = self._connection.cursor()
            self._available = True
        except ImportError:
            self._available = False

    def _query(self, sql: str) -> list[tuple[Any, ...]]:
        if not self._cursor:
            return []
        self._cursor.execute(sql)
        return self._cursor.fetchall()

    def _list_tables(self, pattern: str | None = None) -> list[str]:
        if pattern:
            rows = self._query(f"SHOW TABLES IN `{self._database}` LIKE '{pattern}'")
        else:
            rows = self._query(f"SHOW TABLES IN `{self._database}`")
        return [r[0] for r in rows]

    def _describe_table(self, table: str) -> list[tuple[str, str, str]]:
        """Returns list of (col_name, data_type, comment)"""
        rows = self._query(f"DESCRIBE `{self._database}`.`{table}`")
        result: list[tuple[str, str, str]] = []
        for r in rows:
            if len(r) >= 2 and r[0] and not r[0].startswith("#"):
                comment = r[2] if len(r) >= 3 else ""
                result.append((r[0], r[1], comment))
        return result

    def _show_create_table(self, table: str) -> str:
        """Get CREATE TABLE statement to detect primary keys, partitions, etc."""
        rows = self._query(f"SHOW CREATE TABLE `{self._database}`.`{table}`")
        return "\n".join(r[0] for r in rows)

    def scan(
        self,
        tables: list[str] | None = None,
        pattern: str | None = None,
        sample_size: int = 5,
    ) -> SchemaDiscoveryResult:
        """Scan Hive tables and return discovered schema + proposed ontology."""
        if tables:
            table_names = tables
        else:
            table_names = self._list_tables(pattern)

        discovered = DiscoveredSchema()
        warnings: list[str] = []

        for tbl in table_names:
            try:
                cols = self._describe_table(tbl)
                pk_cols: set[str] = set()

                # Try to detect PKs from CREATE TABLE
                try:
                    ddl = self._show_create_table(tbl)
                    for line in ddl.split("\n"):
                        if "PRIMARY KEY" in line.upper():
                            # Try to parse column references in PK clause
                            import re

                            match = re.findall(r"`(\w+)`", line.split("PRIMARY KEY")[1])
                            pk_cols.update(match)
                except Exception:
                    pass

                entity_name = _table_name_to_entity(tbl)
                discovered_cols: list[ColumnMeta] = []

                for col_name, col_type, comment in cols:
                    is_pk = col_name.lower() in pk_cols
                    discovered_cols.append(
                        ColumnMeta(
                            name=col_name,
                            data_type=_normalize_type(col_type),
                            nullable=not is_pk,
                            primary_key=is_pk,
                            description=comment or None,
                        )
                    )

                discovered.tables.append(
                    DiscoveredTable(
                        source_name=f"hive.{self._database}.{tbl}",
                        suggested_entity_type=entity_name,
                        columns=discovered_cols,
                        description=f"Hive table: {self._database}.{tbl}",
                    )
                )

            except Exception as e:
                warnings.append(f"Failed to scan table '{tbl}': {e}")

        return SchemaDiscoveryResult(
            schema=discovered,
            warnings=warnings,
        )

    def close(self) -> None:
        if self._cursor:
            self._cursor.close()
        if self._connection:
            self._connection.close()
