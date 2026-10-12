import os, sqlite3
from flask import current_app, g
from werkzeug.security import generate_password_hash


SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT NOT NULL UNIQUE,email TEXT NOT NULL UNIQUE,password TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'user',banned INTEGER NOT NULL DEFAULT 0,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS categories(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS tags(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS posts(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,category_id INTEGER,title TEXT NOT NULL,body TEXT NOT NULL,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE SET NULL);
CREATE TABLE IF NOT EXISTS post_tags(post_id INTEGER NOT NULL,tag_id INTEGER NOT NULL,PRIMARY KEY(post_id,tag_id),FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE,FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS comments(id INTEGER PRIMARY KEY AUTOINCREMENT,post_id INTEGER NOT NULL,user_id INTEGER NOT NULL,body TEXT NOT NULL,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS likes(post_id INTEGER NOT NULL,user_id INTEGER NOT NULL,PRIMARY KEY(post_id,user_id),FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
"""

def get_db():
    if "db" not in g:
        g.db=sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory=sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

def close_db():
    db=g.pop("db",None)
    if db: db.close()

def init_db():
    db=get_db(); db.executescript(SCHEMA)
    for c in ("Программирование","Игры","YouTube"):
        db.execute("INSERT OR IGNORE INTO categories(name) VALUES(?)",(c,))
    admin_name=os.getenv("ADMIN_USERNAME","admin").strip()
    admin_email=os.getenv("ADMIN_EMAIL","admin@example.com").strip().lower()
    admin_password=os.getenv("ADMIN_PASSWORD")
    if admin_password and not db.execute("SELECT 1 FROM users WHERE username=?",(admin_name,)).fetchone():
        db.execute("INSERT INTO users(username,email,password,role) VALUES(?,?,?,?)",
                   (admin_name,admin_email,generate_password_hash(admin_password),"admin"))
    db.commit()