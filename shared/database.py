"""Backward-compatible re-export. Use shared.db directly for new code."""
from shared.db import DatabaseService, db_service, SCHEMA_SQL, _db_row_to_api_format, _parse_timestamp

__all__ = ["DatabaseService", "db_service", "SCHEMA_SQL", "_db_row_to_api_format", "_parse_timestamp"]
