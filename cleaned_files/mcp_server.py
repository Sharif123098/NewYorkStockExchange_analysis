# Connecting LLM

import os
import re
import sqlite3
from pathlib import Path
from contextlib import closing

import pandas as pd
from google import genai

# Set your GEMINI_API_KEY environment variable first
client = genai.Client()

# Replace this with your actual database file path
DB_PATH = Path(r"stocks.db")

MODEL = "gemini-3.8-flash"


# LLM inspect database

def get_schema(conn):
    tables = conn.execute("""
        SELECT type, name, sql
        FROM sqlite_master
        WHERE type IN ('table', 'view')
          AND name NOT LIKE 'sqlite_%'
        ORDER BY type, name
    """).fetchall()

    return "\n\n".join(
        f"{kind.upper()}: {name}\n{definition}"
        for kind, name, definition in tables
        if definition
    )


# Natural language query function

def ask_database(question):
    db_uri = DB_PATH.resolve().as_uri() + "?mode=ro"

    # Read the schema without modifying the database
    with closing(sqlite3.connect(db_uri, uri=True)) as conn:
        schema = get_schema(conn)

    prompt = f"""
    You are a SQLite SQL expert.

    Convert the user's question into one valid SQLite query.

    DATABASE SCHEMA:
    {schema}

    RULES:
    - Use only existing tables and columns.
    - Return SQL only, without Markdown or explanations.
    - Generate read-only SELECT queries only.
    - WITH ... SELECT queries are allowed.
    - For detailed row results, use LIMIT 100 by default.
    - Do not invent data or column names.

    USER QUESTION:
    {question}
    """

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt
    )

    sql = re.sub(
        r"\A```(?:sql)?\s*|\s*```\Z",
        "",
        response.text.strip(),
        flags=re.IGNORECASE
    ).strip().rstrip(";").strip()

    # Basic safety validation
    if not re.match(r"^(SELECT|WITH)\b", sql, re.IGNORECASE):
        raise ValueError("Only SELECT queries are allowed.")

    if ";" in sql:
        raise ValueError("Multiple SQL statements are not allowed.")

    # Execute the query in read-only mode
    with closing(sqlite3.connect(db_uri, uri=True)) as conn:
        conn.execute("PRAGMA query_only = ON")
        results = pd.read_sql_query(sql, conn)

    print("Generated SQL:\n", sql)

    return results


# Question

ask_database(
    "Show me the 10 stocks with the highest closing prices."
)
