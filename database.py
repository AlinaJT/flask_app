import sqlite3
import click
from flask import current_app, g
import os
import tempfile

# Get or create database connection
def get_db():
    # Check if database connection exists in Flask's application context
    if 'db' not in g:
        # Use a unique temporary database for each test
        db_path = tempfile.mktemp(suffix='.db')
        g.db = sqlite3.connect(
            db_path,
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        # Configure database to return rows as dictionaries
        g.db.row_factory = sqlite3.Row
    return g.db

# Close database connection when application context ends
def close_db(e=None):
    # Remove database connection from application context
    db = g.pop('db', None)
    if db is not None:
        db.close()

# Initialize the database with schema
def init_db():
    db = get_db()
    # Get the absolute path to schema.sql
    schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema.sql')
    # Read and execute schema
    with open(schema_path, 'r') as f:
        db.executescript(f.read())
    db.commit()

# Flask CLI command to initialize database
@click.command('init-db')
def init_db_command():
    """Clear the existing data and create new tables."""
    init_db()
    click.echo('Initialized the database.')

# Register database functions with Flask application
def init_app(app):
    # Register function to close database when application context ends
    app.teardown_appcontext(close_db)
    # Add database initialization command to Flask CLI
    app.cli.add_command(init_db_command)
