"""Administrative routes."""
from flask import Blueprint, request, redirect, url_for, flash, abort, render_template
from .db import db
from .auth import admin_required

admin_bp = Blueprint("admin", __name__)

@admin_bp.route("/admin")
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

    return render_template(
        "admin.html", stats=stats, users=users, posts=posts,
        comments=comments, categories=categories, tags=tags
    )


@admin_bp.route("/admin/user/<int:user_id>/ban", methods=["POST"])
@admin_required
def ban_user(user_id):
    conn = db()
    user = conn.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
    if user and user["role"] != "admin":
        conn.execute("UPDATE users SET banned=1 WHERE id=?", (user_id,))
    conn.commit()
    return redirect(url_for('admin.admin'))


@admin_bp.route("/admin/user/<int:user_id>/unban", methods=["POST"])
@admin_required
def unban_user(user_id):
    conn = db()
    conn.execute("UPDATE users SET banned=0 WHERE id=?", (user_id,))
    conn.commit()
    return redirect(url_for('admin.admin'))


@admin_bp.route("/admin/post/<int:post_id>/delete", methods=["POST"])
@admin_required
def admin_delete_post(post_id):
    conn = db()
    conn.execute("DELETE FROM posts WHERE id=?", (post_id,))
    conn.commit()
    return redirect(url_for('admin.admin'))


@admin_bp.route("/admin/comment/<int:comment_id>/delete", methods=["POST"])
@admin_required
def admin_delete_comment(comment_id):
    conn = db()
    conn.execute("DELETE FROM comments WHERE id=?", (comment_id,))
    conn.commit()
    return redirect(url_for('admin.admin'))


@admin_bp.route("/admin/category", methods=["POST"])
@admin_required
def add_category():
    name = request.form.get("name", "").strip()[:80]
    if name:
        conn = db()
        conn.execute("INSERT OR IGNORE INTO categories(name) VALUES(?)", (name,))
        conn.commit()
    return redirect(url_for('admin.admin'))


@admin_bp.route("/admin/category/<int:category_id>/delete", methods=["POST"])
@admin_required
def delete_category(category_id):
    conn = db()
    conn.execute("DELETE FROM categories WHERE id=?", (category_id,))
    conn.commit()
    flash("Категория удалена. Связанные посты теперь отображаются как «Без категории».", "success")
    return redirect(url_for('admin.admin'))


@admin_bp.route("/admin/tag/<int:tag_id>/delete", methods=["POST"])
@admin_required
def delete_tag(tag_id):
    conn = db()
    conn.execute("DELETE FROM tags WHERE id=?", (tag_id,))
    conn.commit()
    return redirect(url_for('admin.admin'))

