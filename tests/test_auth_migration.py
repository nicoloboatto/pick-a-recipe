"""Tests for the users-table migration: must never drop existing accounts.

Upstream's own migration used to detect a `password_hash` column (our
fork's local-auth marker) and respond by dropping the whole `users` table
to enforce "OIDC-only, no legacy local accounts." Since we deliberately
keep local auth alongside OIDC, that drop is neutralized into a purely
additive migration.

Tests `_migrate_schema()` directly against a throwaway, isolated SQLite
connection (not the shared test-session DB other test files use) so this
never touches or depends on global DATA_DIR state.
"""

import os
import sqlite3
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'ui'))

import database  # noqa: E402


class MigrationHealingTests(unittest.TestCase):
    def _legacy_conn(self):
        """An isolated in-memory DB with the old OIDC-only users table, plus
        the other tables _migrate_schema() also touches (empty is fine -
        it only needs them to exist for its ALTER/DELETE statements)."""
        conn = sqlite3.connect(':memory:')
        conn.row_factory = sqlite3.Row
        conn.execute('''
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                oidc_sub TEXT UNIQUE,
                email TEXT,
                name TEXT,
                avatar_url TEXT,
                is_admin INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('CREATE TABLE recipe_jobs (id TEXT PRIMARY KEY)')
        conn.execute('CREATE TABLE recipe_history (id INTEGER PRIMARY KEY, url TEXT, status TEXT)')
        conn.execute('CREATE TABLE pending_uploads (id TEXT PRIMARY KEY)')
        return conn

    def test_existing_oidc_user_survives_migration(self):
        conn = self._legacy_conn()
        conn.execute(
            "INSERT INTO users (username, oidc_sub, email, is_admin) "
            "VALUES ('alice', 'sub-123', 'alice@example.com', 1)"
        )
        conn.commit()

        database._migrate_schema(conn)

        row = conn.execute('SELECT * FROM users WHERE username = ?', ('alice',)).fetchone()
        self.assertIsNotNone(row, "existing OIDC user must survive migration, not be dropped")
        self.assertEqual(row['oidc_sub'], 'sub-123')
        # The additive migration adds password_hash with a safe empty default.
        self.assertEqual(row['password_hash'], '')

    def test_migration_adds_local_auth_columns(self):
        conn = self._legacy_conn()
        database._migrate_schema(conn)

        columns = {row[1] for row in conn.execute('PRAGMA table_info(users)').fetchall()}
        for expected in ('password_hash', 'auth_provider', 'must_change_password'):
            self.assertIn(expected, columns)

    def test_migration_is_idempotent(self):
        conn = self._legacy_conn()
        database._migrate_schema(conn)
        database._migrate_schema(conn)  # must not raise or duplicate columns
        columns = [row[1] for row in conn.execute('PRAGMA table_info(users)').fetchall()]
        self.assertEqual(len(columns), len(set(columns)))


if __name__ == "__main__":
    unittest.main()
