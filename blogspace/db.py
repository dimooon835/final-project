"""SQLite connection and schema helpers."""
import os
import sqlite3
from flask import g
from werkzeug.security import generate_password_hash, check_password_hash

DB = os.path.join(os.path.dirname(os.path.dirname(__file__)), "blog.db")

def db():
    if "db_conn" not in g:
        g.db_conn = sqlite3.connect(DB)
        g.db_conn.row_factory = sqlite3.Row
        g.db_conn.execute("PRAGMA foreign_keys = ON")
    return g.db_conn

def close_db(error=None):
    conn = g.pop("db_conn", None)
    if conn is not None:
        conn.close()

def init_db():
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        banned INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS categories(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    );
    CREATE TABLE IF NOT EXISTS tags(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    );
    CREATE TABLE IF NOT EXISTS posts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        category_id INTEGER,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE SET NULL
    );
    CREATE TABLE IF NOT EXISTS post_tags(
        post_id INTEGER NOT NULL,
        tag_id INTEGER NOT NULL,
        PRIMARY KEY(post_id, tag_id),
        FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE,
        FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS comments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        body TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS likes(
        post_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        PRIMARY KEY(post_id, user_id),
        FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)
    admin_password = os.environ.get("ADMIN_PASSWORD")
    if admin_password:
        existing_admin = conn.execute("SELECT id,password FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()
        if not existing_admin:
            conn.execute("INSERT INTO users(username,email,password,role) VALUES(?,?,?,?)",
                         ("admin", os.environ.get("ADMIN_EMAIL", "admin@example.com"),
                          generate_password_hash(admin_password), "admin"))
        elif check_password_hash(existing_admin["password"], "admin123"):
            conn.execute("UPDATE users SET password=? WHERE id=?",
                         (generate_password_hash(admin_password), existing_admin["id"]))
    if conn.execute("SELECT COUNT(*) c FROM categories").fetchone()["c"] == 0:
        conn.executemany(
            "INSERT INTO categories(name) VALUES(?)",
            [("Программирование",), ("Игры",), ("YouTube",)]
        )
    conn.commit()


def save_tags(conn, post_id, raw):
    conn.execute("DELETE FROM post_tags WHERE post_id=?", (post_id,))
    names = [x.strip().lower() for x in raw.split(",") if x.strip()]
    for name in dict.fromkeys(names):
        conn.execute("INSERT OR IGNORE INTO tags(name) VALUES(?)", (name,))
        tag_id = conn.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()["id"]
        conn.execute(
            "INSERT OR IGNORE INTO post_tags(post_id,tag_id) VALUES(?,?)",
            (post_id, tag_id)
        )

