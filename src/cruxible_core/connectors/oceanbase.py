"""OceanBase connector — scan OB tables via SQLAlchemy and infer ontology."""

from __future__ import annotations

from typing import Any

from cruxible_core.connectors.base import (
    ColumnMeta,
    DiscoveredRelationship,
    DiscoveredSchema,
    DiscoveredTable,
    SchemaDiscoveryResult,
)

_OB_TYPE_MAP = {
    "varchar": "string",
    "char": "string",
    "text": "string",
    "longtext": "string",
    "mediumtext": "string",
    "int": "int",
    "integer": "int",
    "bigint": "int",
    "smallint": "int",
    "tinyint": "int",
    "float": "float",
    "double": "float",
    "decimal": "float",
    "number": "float",
    "boolean": "bool",
    "date": "date",
    "datetime": "datetime",
    "timestamp": "datetime",
    "blob": "string",
    "json": "json",
}


def _normalize_type(ob_type: str) -> str:
    base = ob_type.split("(")[0].strip().lower()
    return _OB_TYPE_MAP.get(base, "string")


def _table_name_to_entity(name: str) -> str:
    """Convert OB table name to entity type name (PascalCase, strip prefixes)."""
    cleaned = name.lower()
    for prefix in ["t_", "tb_", "dim_", "fact_", "ods_", "tmp_", "bak_"]:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    return "".join(word.capitalize() for word in cleaned.split("_"))


class OceanBaseConnector:
    """Connect to OceanBase via pymysql-compatible driver.

    Usage::
        connector = OceanBaseConnector()
        connector.connect(host="ob-server", port=2883, database="testdb",
                          user="root", password="xxx")
        result = connector.scan()
        connector.close()
    """

    def __init__(self) -> None:
        self._connection: Any = None
        self._cursor: Any = None
        self._database: str = ""

    def connect(
        self,
        host: str = "localhost",
        port: int = 2883,
        database: str = "",
        user: str = "root",
        password: str = "",
        **kwargs: Any,
    ) -> None:
        """Connect to OceanBase using mysql-connector-python or pymysql."""
        self._database = database
        try:
            import pymysql

            self._connection = pymysql.connect(
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
                charset="utf8mb4",
                **kwargs,
            )
            self._cursor = self._connection.cursor()
        except ImportError:
            pass

    def _query(self, sql: str) -> list[tuple[Any, ...]]:
        if not self._cursor:
            return []
        self._cursor.execute(sql)
        return self._cursor.fetchall()

    def _list_tables(self) -> list[str]:
        rows = self._query(
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
            f"WHERE TABLE_SCHEMA = '{self._database}' "
            "AND TABLE_TYPE = 'BASE TABLE' "
            "ORDER BY TABLE_NAME"
        )
        return [r[0] for r in rows]

    def _describe_table(self, table: str) -> list[dict[str, Any]]:
        rows = self._query(
            "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, "
            "COLUMN_KEY, COLUMN_COMMENT, CHARACTER_MAXIMUM_LENGTH "
            "FROM INFORMATION_SCHEMA.COLUMNS "
            f"WHERE TABLE_SCHEMA = '{self._database}' AND TABLE_NAME = '{table}' "
            "ORDER BY ORDINAL_POSITION"
        )
        result: list[dict[str, Any]] = []
        for r in rows:
            result.append({
                "name": r[0],
                "data_type": r[1],
                "nullable": r[2] == "YES",
                "column_key": r[3] or "",
                "comment": r[4] or "",
                "max_length": r[5],
            })
        return result

    def _find_foreign_keys(self) -> list[dict[str, str]]:
        rows = self._query(
            "SELECT COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME, "
            "TABLE_NAME, CONSTRAINT_NAME "
            "FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE "
            f"WHERE TABLE_SCHEMA = '{self._database}' "
            "AND REFERENCED_TABLE_NAME IS NOT NULL"
        )
        result: list[dict[str, str]] = []
        for r in rows:
            result.append({
                "column_name": r[0],
                "ref_table": r[1],
                "ref_column": r[2],
                "table_name": r[3],
                "constraint_name": r[4],
            })
        return result

    def scan(
        self,
        tables: list[str] | None = None,
        sample_size: int = 5,
    ) -> SchemaDiscoveryResult:
        """Scan OceanBase tables and return discovered schema + proposed ontology."""
        if tables:
            table_names = tables
        else:
            table_names = self._list_tables()

        # Build table name lookup for FK inference
        fk_list = self._find_foreign_keys()

        discovered = DiscoveredSchema()
        warnings: list[str] = []

        for tbl in table_names:
            try:
                cols = self._describe_table(tbl)
                entity_name = _table_name_to_entity(tbl)

                discovered_cols: list[ColumnMeta] = []
                for col in cols:
                    is_pk = col["column_key"] in ("PRI",)
                    discovered_cols.append(
                        ColumnMeta(
                            name=col["name"],
                            data_type=_normalize_type(col["data_type"]),
                            nullable=col["nullable"] and not is_pk,
                            primary_key=is_pk,
                            description=col["comment"] or None,
                            max_length=col["max_length"],
                        )
                    )

                discovered.tables.append(
                    DiscoveredTable(
                        source_name=f"oceanbase.{self._database}.{tbl}",
                        suggested_entity_type=entity_name,
                        columns=discovered_cols,
                        description=f"OceanBase table: {self._database}.{tbl}",
                    )
                )
            except Exception as e:
                warnings.append(f"Failed to scan table '{tbl}': {e}")

        # Build FK-based relationships
        for fk in fk_list:
            from_entity = _table_name_to_entity(fk["table_name"])
            to_entity = _table_name_to_entity(fk["ref_table"])
            discovered.relationships.append(
                DiscoveredRelationship(
                    from_entity_type=from_entity,
                    from_column=fk["column_name"],
                    to_entity_type=to_entity,
                    to_column=fk["ref_column"],
                    suggested_relationship_name=f"{from_entity.lower()}_ref_{to_entity.lower()}",
                )
            )

        result = SchemaDiscoveryResult(schema=discovered, warnings=warnings)
        return result

    def close(self) -> None:
        if self._cursor:
            self._cursor.close()
        if self._connection:
            self._connection.close()
