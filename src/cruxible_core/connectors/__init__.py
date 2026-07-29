"""Data source connectors for schema discovery and metadata ingestion.

Each connector implements the :class:`SchemaConnector` protocol to
connect to an external data source, discover tables/collections/files,
infer their schema, and return structured metadata that can be converted
into ontology proposals.
"""

from cruxible_core.connectors.base import (
    ColumnMeta,
    DiscoveredRelationship,
    DiscoveredSchema,
    DiscoveredTable,
    SchemaConnector,
    SchemaDiscoveryResult,
)
from cruxible_core.connectors.hive import HiveConnector
from cruxible_core.connectors.oceanbase import OceanBaseConnector
from cruxible_core.connectors.sftp import SFTPConnector

__all__ = [
    "SchemaConnector",
    "SchemaDiscoveryResult",
    "DiscoveredSchema",
    "DiscoveredTable",
    "DiscoveredRelationship",
    "ColumnMeta",
    "HiveConnector",
    "OceanBaseConnector",
    "SFTPConnector",
]
