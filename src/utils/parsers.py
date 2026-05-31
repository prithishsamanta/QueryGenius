# src/utils/parsers.py
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Dict


def fetch_schema_from_db(db: Session, table_names: List[str]) -> List[Dict]:
    """
    Fetch schema information for the given tables from pg_catalog.

    Retrieves column names, data types, nullability, and existing indexes
    for each requested table. Used to build schema context for LLM prompts
    so recommendations reference actual column names and avoid suggesting
    indexes that already exist.

    Args:
        db: SQLAlchemy session connected to the target database
        table_names: List of table names to introspect

    Returns:
        List of table schema dicts, each containing:
            - table: table name
            - columns: list of column dicts (name, type, nullable)
            - indexes: list of index dicts (name, columns, unique)

    Raises:
        ValueError: If table_names is empty

    Example:
        >>> schema = fetch_schema_from_db(db, ["users", "orders"])
        >>> schema[0]["table"]
        'users'
        >>> schema[0]["columns"][0]["name"]
        'id'
    """
    if not table_names:
        raise ValueError("table_names cannot be empty")

    schema = []

    for table_name in table_names:
        # Fetch columns from information_schema
        columns_result = db.execute(
            text("""
                SELECT
                    column_name,
                    data_type,
                    is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = :table_name
                ORDER BY ordinal_position
            """),
            {"table_name": table_name}
        ).fetchall()

        if not columns_result:
            # Table does not exist in this database — skip silently
            continue

        columns = [
            {
                "name": row.column_name,
                "type": row.data_type,
                "nullable": row.is_nullable == "YES",
            }
            for row in columns_result
        ]

        # Fetch indexes from pg_catalog
        indexes_result = db.execute(
            text("""
                SELECT
                    i.relname AS index_name,
                    array_agg(a.attname ORDER BY array_position(ix.indkey, a.attnum)) AS index_columns,
                    ix.indisunique AS is_unique
                FROM pg_class t
                JOIN pg_index ix ON t.oid = ix.indrelid
                JOIN pg_class i ON i.oid = ix.indexrelid
                JOIN pg_attribute a ON a.attrelid = t.oid
                    AND a.attnum = ANY(ix.indkey)
                WHERE t.relname = :table_name
                  AND t.relkind = 'r'
                GROUP BY i.relname, ix.indisunique
                ORDER BY i.relname
            """),
            {"table_name": table_name}
        ).fetchall()

        indexes = [
            {
                "name": row.index_name,
                "columns": list(row.index_columns),
                "unique": row.is_unique,
            }
            for row in indexes_result
        ]

        schema.append({
            "table": table_name,
            "columns": columns,
            "indexes": indexes,
        })

    return schema


def format_schema_for_prompt(schema: List[Dict]) -> str:
    """
    Format schema dicts into a compact, readable string for LLM prompts.

    Args:
        schema: List of table schema dicts from fetch_schema_from_db()

    Returns:
        Formatted schema string ready for injection into a prompt

    Example:
        >>> print(format_schema_for_prompt(schema))
        Table: users
          Columns: id (integer, NOT NULL), email (text, NOT NULL), ...
          Indexes: users_pkey (id) UNIQUE, ix_users_email (email)
    """
    if not schema:
        return "No schema context provided."

    lines = []
    for table in schema:
        lines.append(f"Table: {table['table']}")

        col_parts = []
        for col in table["columns"]:
            nullable = "NULL" if col["nullable"] else "NOT NULL"
            col_parts.append(f"{col['name']} ({col['type']}, {nullable})")
        lines.append(f"  Columns: {', '.join(col_parts)}")

        if table["indexes"]:
            idx_parts = []
            for idx in table["indexes"]:
                cols = ", ".join(idx["columns"])
                unique = " UNIQUE" if idx["unique"] else ""
                idx_parts.append(f"{idx['name']} ({cols}){unique}")
            lines.append(f"  Indexes: {', '.join(idx_parts)}")
        else:
            lines.append("  Indexes: none")

        lines.append("")

    return "\n".join(lines).strip()
