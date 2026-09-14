from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
import sqlite3, os
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")
DB = os.path.join(os.path.dirname(__file__), "blog.db")

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

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

    if not conn.execute("SELECT 1 FROM users WHERE username='admin'").fetchone():
        conn.execute(
            "INSERT INTO users(username,email,password,role) VALUES(?,?,?,?)",
            ("admin", "admin@example.com", generate_password_hash("admin123"), "admin")
        )
    if conn.execute("SELECT COUNT(*) c FROM categories").fetchone()["c"] == 0:
        conn.executemany(
            "INSERT INTO categories(name) VALUES(?)",
            [("Программирование",), ("Игры",), ("YouTube",)]
        )
    conn.commit()
    conn.close()

def current_user():
    if "user_id" not in session:
        return None
    conn = db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    conn.close()
    return user

@app.context_processor
def inject():
    return {"current_user": current_user()}

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            return redirect(url_for("login", next=request.path))
        if user["banned"]:
            session.clear()
            flash("Ваш аккаунт заблокирован.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped

def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user or user["role"] != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped

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

@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    tag = request.args.get("tag", "").strip().lower()
    cat = request.args.get("category", "").strip()
    page = max(int(request.args.get("page", 1) or 1), 1)
    per_page = 6
    offset = (page - 1) * per_page

    conn = db()
    where, args = [], []

    if q:
        where.append("(p.title LIKE ? OR p.body LIKE ?)")
        args += [f"%{q}%", f"%{q}%"]
    if tag:
        where.append("""EXISTS(
            SELECT 1 FROM post_tags pt2
            JOIN tags t2 ON t2.id=pt2.tag_id
            WHERE pt2.post_id=p.id AND t2.name=?
        )""")
        args.append(tag)
    if cat:
        where.append("c.id=?")
        args.append(cat)

    condition = " WHERE " + " AND ".join(where) if where else ""
    total = conn.execute(
        f"SELECT COUNT(*) c FROM posts p LEFT JOIN categories c ON c.id=p.category_id{condition}",
        args
    ).fetchone()["c"]

    posts = conn.execute(f"""
        SELECT p.*, u.username, c.name category,
        (SELECT COUNT(*) FROM likes l WHERE l.post_id=p.id) likes,
        (SELECT COUNT(*) FROM comments cm WHERE cm.post_id=p.id) comments
        FROM posts p
        JOIN users u ON u.id=p.user_id
        LEFT JOIN categories c ON c.id=p.category_id
        {condition}
        ORDER BY p.created_at DESC
        LIMIT ? OFFSET ?
    """, args + [per_page, offset]).fetchall()

    categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    conn.close()

    pages = max((total + per_page - 1) // per_page, 1)
    return render_template(
        "index.html", posts=posts, categories=categories,
        page=page, pages=pages, q=q, tag=tag, cat=cat
    )

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        if len(username) < 3 or len(password) < 6:
            flash("Логин должен быть от 3 символов, пароль — от 6.", "error")
        else:
            conn = db()
            try:
                conn.execute(
                    "INSERT INTO users(username,email,password) VALUES(?,?,?)",
                    (username, email, generate_password_hash(password))
                )
                conn.commit()
                flash("Регистрация успешна. Теперь войдите.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("Такой логин или email уже занят.", "error")
            finally:
                conn.close()
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identity = request.form["identity"].strip()
        conn = db()
        user = conn.execute(
            "SELECT * FROM users WHERE username=? OR email=?",
            (identity, identity.lower())
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], request.form["password"]) and not user["banned"]:
            session["user_id"] = user["id"]
            return redirect(request.args.get("next") or url_for("index"))

        flash("Неверные данные или аккаунт заблокирован.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/post/<int:post_id>")
def post(post_id):
    conn = db()
    post_item = conn.execute("""
        SELECT p.*, u.username, c.name category,
        (SELECT COUNT(*) FROM likes WHERE post_id=p.id) likes
        FROM posts p
        JOIN users u ON u.id=p.user_id
        LEFT JOIN categories c ON c.id=p.category_id
        WHERE p.id=?
    """, (post_id,)).fetchone()

    if not post_item:
        abort(404)

    comments = conn.execute("""
        SELECT cm.*, u.username
        FROM comments cm JOIN users u ON u.id=cm.user_id
        WHERE cm.post_id=? ORDER BY cm.created_at
    """, (post_id,)).fetchall()

    tags = conn.execute("""
        SELECT t.name FROM tags t
        JOIN post_tags pt ON pt.tag_id=t.id
        WHERE pt.post_id=? ORDER BY t.name
    """, (post_id,)).fetchall()

    liked = False
    user = current_user()
    if user:
        liked = bool(conn.execute(
            "SELECT 1 FROM likes WHERE post_id=? AND user_id=?",
            (post_id, user["id"])
        ).fetchone())

    conn.close()
    return render_template(
        "post.html", post=post_item, comments=comments,
        tags=tags, liked=liked
    )

@app.route("/post/new", methods=["GET", "POST"])
@login_required
def new_post():
    conn = db()
    categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()

    if request.method == "POST":
        title = request.form["title"].strip()
        body = request.form["body"].strip()
        if not title or not body:
            flash("Заголовок и текст обязательны.", "error")
        else:
            cur = conn.execute(
                "INSERT INTO posts(title,body,user_id,category_id) VALUES(?,?,?,?)",
                (title, body, current_user()["id"], request.form.get("category") or None)
            )
            save_tags(conn, cur.lastrowid, request.form.get("tags", ""))
            conn.commit()
            conn.close()
            return redirect(url_for("post", post_id=cur.lastrowid))

    conn.close()
    return render_template("post_form.html", post=None, categories=categories, tags="")

@app.route("/post/<int:post_id>/edit", methods=["GET", "POST"])
@login_required
def edit_post(post_id):
    conn = db()
    post_item = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    user = current_user()

    if not post_item:
        abort(404)
    if post_item["user_id"] != user["id"] and user["role"] != "admin":
        abort(403)

    categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()

    if request.method == "POST":
        conn.execute("""
            UPDATE posts SET title=?, body=?, category_id=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        """, (
            request.form["title"].strip(),
            request.form["body"].strip(),
            request.form.get("category") or None,
            post_id
        ))
        save_tags(conn, post_id, request.form.get("tags", ""))
        conn.commit()
        conn.close()
        return redirect(url_for("post", post_id=post_id))

    tag_rows = conn.execute("""
        SELECT t.name FROM tags t JOIN post_tags pt ON pt.tag_id=t.id
        WHERE pt.post_id=?
    """, (post_id,)).fetchall()
    tags = ", ".join(x["name"] for x in tag_rows)
    conn.close()

    return render_template(
        "post_form.html", post=post_item,
        categories=categories, tags=tags
    )

@app.route("/post/<int:post_id>/delete", methods=["POST"])
@login_required
def delete_post(post_id):
    conn = db()
    post_item = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    user = current_user()

    if not post_item:
        abort(404)
    if post_item["user_id"] != user["id"] and user["role"] != "admin":
        abort(403)

    conn.execute("DELETE FROM posts WHERE id=?", (post_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

@app.route("/post/<int:post_id>/comment", methods=["POST"])
@login_required
def comment(post_id):
    body = request.form["body"].strip()
    if body:
        conn = db()
        conn.execute(
            "INSERT INTO comments(post_id,user_id,body) VALUES(?,?,?)",
            (post_id, current_user()["id"], body)
        )
        conn.commit()
        conn.close()
    return redirect(url_for("post", post_id=post_id))

@app.route("/post/<int:post_id>/like", methods=["POST"])
@login_required
def like(post_id):
    conn = db()
    user_id = current_user()["id"]

    exists = conn.execute(
        "SELECT 1 FROM likes WHERE post_id=? AND user_id=?",
        (post_id, user_id)
    ).fetchone()

    if exists:
        conn.execute("DELETE FROM likes WHERE post_id=? AND user_id=?", (post_id, user_id))
    else:
        conn.execute("INSERT OR IGNORE INTO likes(post_id,user_id) VALUES(?,?)", (post_id, user_id))

    conn.commit()
    conn.close()
    return redirect(request.referrer or url_for("post", post_id=post_id))

@app.route("/admin")
@admin_required
def admin():
    conn = db()
    stats = {
        "Пользователи": conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"],
        "Посты": conn.execute("SELECT COUNT(*) c FROM posts").fetchone()["c"],
        "Комментарии": conn.execute("SELECT COUNT(*) c FROM comments").fetchone()["c"],
        "Лайки": conn.execute("SELECT COUNT(*) c FROM likes").fetchone()["c"],
    }
    users = conn.execute(
        "SELECT id,username,email,role,banned,created_at FROM users ORDER BY id DESC"
    ).fetchall()
    posts = conn.execute("""
        SELECT p.*,u.username FROM posts p JOIN users u ON u.id=p.user_id
        ORDER BY p.id DESC
    """).fetchall()
    comments = conn.execute("""
        SELECT cm.*,u.username,p.title FROM comments cm
        JOIN users u ON u.id=cm.user_id JOIN posts p ON p.id=cm.post_id
        ORDER BY cm.id DESC
    """).fetchall()
    categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    tags = conn.execute("SELECT * FROM tags ORDER BY name").fetchall()
    conn.close()

    return render_template(
        "admin.html", stats=stats, users=users, posts=posts,
        comments=comments, categories=categories, tags=tags
    )

@app.route("/admin/user/<int:user_id>/ban", methods=["POST"])
@admin_required
def ban_user(user_id):
    conn = db()
    user = conn.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
    if user and user["role"] != "admin":
        conn.execute("UPDATE users SET banned=1 WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin"))

@app.route("/admin/user/<int:user_id>/unban", methods=["POST"])
@admin_required
def unban_user(user_id):
    conn = db()
    conn.execute("UPDATE users SET banned=0 WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin"))

@app.route("/admin/post/<int:post_id>/delete", methods=["POST"])
@admin_required
def admin_delete_post(post_id):
    conn = db()
    conn.execute("DELETE FROM posts WHERE id=?", (post_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin"))

@app.route("/admin/comment/<int:comment_id>/delete", methods=["POST"])
@admin_required
def admin_delete_comment(comment_id):
    conn = db()
    conn.execute("DELETE FROM comments WHERE id=?", (comment_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin"))

@app.route("/admin/category", methods=["POST"])
@admin_required
def add_category():
    name = request.form["name"].strip()
    if name:
        conn = db()
        conn.execute("INSERT OR IGNORE INTO categories(name) VALUES(?)", (name,))
        conn.commit()
        conn.close()
    return redirect(url_for("admin"))

@app.route("/admin/category/<int:category_id>/delete", methods=["POST"])
@admin_required
def delete_category(category_id):
    conn = db()
    conn.execute("DELETE FROM categories WHERE id=?", (category_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin"))

@app.route("/admin/tag/<int:tag_id>/delete", methods=["POST"])
@admin_required
def delete_tag(tag_id):
    conn = db()
    conn.execute("DELETE FROM tags WHERE id=?", (tag_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin"))

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
