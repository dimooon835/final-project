"""Public feed, post, comment and like routes."""
from flask import Blueprint, request, redirect, url_for, flash, abort, render_template
from .db import db, save_tags
from .auth import current_user, login_required

posts_bp = Blueprint("posts", __name__)

@posts_bp.route("/")
def index():
    q = request.args.get("q", "").strip()
    tag = request.args.get("tag", "").strip().lower()
    cat = request.args.get("category", "").strip()
    author = request.args.get("author", "").strip()
    try:
        page = max(int(request.args.get("page", 1) or 1), 1)
    except (TypeError, ValueError):
        page = 1
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
    if author:
        try:
            where.append("p.user_id=?")
            args.append(int(author))
        except ValueError:
            author = ""

    condition = " WHERE " + " AND ".join(where) if where else ""
    total = conn.execute(
        f"SELECT COUNT(*) c FROM posts p LEFT JOIN categories c ON c.id=p.category_id{condition}",
        args
    ).fetchone()["c"]

    posts = conn.execute(f"""
        SELECT p.*, u.username, c.name category,
        (SELECT COUNT(*) FROM likes l WHERE l.post_id=p.id) likes,
        (SELECT COUNT(*) FROM comments cm WHERE cm.post_id=p.id) comments,
        (SELECT group_concat(t.name, '|') FROM post_tags pt JOIN tags t ON t.id=pt.tag_id WHERE pt.post_id=p.id) tag_names_raw
        FROM posts p
        JOIN users u ON u.id=p.user_id
        LEFT JOIN categories c ON c.id=p.category_id
        {condition}
        ORDER BY p.created_at DESC
        LIMIT ? OFFSET ?
    """, args + [per_page, offset]).fetchall()

    categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    posts = [dict(p) for p in posts]
    for item in posts:
        item["tag_names"] = item.get("tag_names_raw", "").split("|") if item.get("tag_names_raw") else []

    pages = max((total + per_page - 1) // per_page, 1)
    return render_template(
        "index.html", posts=posts, categories=categories,
        page=page, pages=pages, q=q, tag=tag, cat=cat, author=author
    )


@posts_bp.route("/post/<int:post_id>")
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

    return render_template(
        "post.html", post=post_item, comments=comments,
        tags=tags, liked=liked
    )


@posts_bp.route("/post/new", methods=["GET", "POST"])
@login_required
def new_post():
    conn = db()
    categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        if not title or not body or len(title) > 200 or len(body) > 50000:
            flash("Заголовок и текст обязательны; максимум 200 символов в заголовке и 50 000 в тексте.", "error")
        else:
            category_raw = request.form.get("category", "").strip()
            category_id = None
            if category_raw:
                try: category_id = int(category_raw)
                except ValueError: category_id = -1
                if not conn.execute("SELECT 1 FROM categories WHERE id=?", (category_id,)).fetchone():
                    flash("Выбрана несуществующая категория.", "error")
                    return render_template("post_form.html", post=None, categories=categories,
                                           tags=request.form.get("tags", ""), form_title=title,
                                           form_body=body, form_category=category_raw)
            cur = conn.execute(
                "INSERT INTO posts(title,body,user_id,category_id) VALUES(?,?,?,?)",
                (title, body, current_user()["id"], category_id)
            )
            save_tags(conn, cur.lastrowid, request.form.get("tags", ""))
            conn.commit()
            return redirect(url_for('posts.post', post_id=cur.lastrowid))

    return render_template("post_form.html", post=None, categories=categories, tags="")


@posts_bp.route("/post/<int:post_id>/edit", methods=["GET", "POST"])
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
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        category_raw = request.form.get("category", "").strip()
        category_id = None
        if category_raw:
            try: category_id = int(category_raw)
            except ValueError: category_id = -1
        if not title or not body or len(title) > 200 or len(body) > 50000:
            flash("Заголовок и текст обязательны; максимум 200 символов в заголовке и 50 000 в тексте.", "error")
            return render_template("post_form.html", post=post_item, categories=categories,
                                   tags=request.form.get("tags", ""), form_title=title,
                                   form_body=body, form_category=category_raw)
        if category_id is not None and not conn.execute("SELECT 1 FROM categories WHERE id=?", (category_id,)).fetchone():
            flash("Выбрана несуществующая категория.", "error")
            return render_template("post_form.html", post=post_item, categories=categories,
                                   tags=request.form.get("tags", ""), form_title=title,
                                   form_body=body, form_category=category_raw)
        conn.execute("UPDATE posts SET title=?, body=?, category_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                     (title, body, category_id, post_id))
        save_tags(conn, post_id, request.form.get("tags", "")[:500])
        conn.commit()
        return redirect(url_for('posts.post', post_id=post_id))

    tag_rows = conn.execute("""
        SELECT t.name FROM tags t JOIN post_tags pt ON pt.tag_id=t.id
        WHERE pt.post_id=?
    """, (post_id,)).fetchall()
    tags = ", ".join(x["name"] for x in tag_rows)

    return render_template(
        "post_form.html", post=post_item,
        categories=categories, tags=tags
    )


@posts_bp.route("/post/<int:post_id>/delete", methods=["POST"])
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
    return redirect(url_for('posts.index'))


@posts_bp.route("/post/<int:post_id>/comment", methods=["POST"])
@login_required
def comment(post_id):
    conn = db()
    if not conn.execute("SELECT 1 FROM posts WHERE id=?", (post_id,)).fetchone():
        abort(404)
    body = request.form.get("body", "").strip()
    if body and len(body) <= 2000:
        conn.execute("INSERT INTO comments(post_id,user_id,body) VALUES(?,?,?)",
                     (post_id, current_user()["id"], body))
        conn.commit()
    elif body:
        flash("Комментарий не должен превышать 2000 символов.", "error")
    return redirect(url_for('posts.post', post_id=post_id))


@posts_bp.route("/post/<int:post_id>/like", methods=["POST"])
@login_required
def like(post_id):
    conn = db()
    if not conn.execute("SELECT 1 FROM posts WHERE id=?", (post_id,)).fetchone():
        abort(404)
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
    return redirect(request.referrer or url_for('posts.post', post_id=post_id))


@posts_bp.route("/comment/<int:comment_id>/delete", methods=["POST"])
@login_required
def delete_comment(comment_id):
    conn = db()
    row = conn.execute("SELECT * FROM comments WHERE id=?", (comment_id,)).fetchone()
    if not row: abort(404)
    user = current_user()
    if row["user_id"] != user["id"] and user["role"] != "admin": abort(403)
    post_id = row["post_id"]
    conn.execute("DELETE FROM comments WHERE id=?", (comment_id,))
    conn.commit()
    return redirect(url_for('posts.post', post_id=post_id))

