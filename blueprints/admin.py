from flask import Blueprint,abort,flash,redirect,render_template,request,url_for
from db import get_db
from app import admin_required


bp=Blueprint("admin",__name__,url_prefix="/admin")
@bp.get("/")
@admin_required
def dashboard():
    db=get_db();stats={x:db.execute(f"SELECT COUNT(*) FROM {x}").fetchone()[0] for x in ("users","posts","comments","likes")}
    return render_template("admin.html",stats=stats,users=db.execute("SELECT * FROM users ORDER BY id DESC").fetchall(),posts=db.execute("SELECT p.*,u.username FROM posts p JOIN users u ON u.id=p.user_id ORDER BY p.created_at DESC").fetchall(),comments=db.execute("SELECT c.*,u.username,p.title FROM comments c JOIN users u ON u.id=c.user_id JOIN posts p ON p.id=c.post_id ORDER BY c.created_at DESC").fetchall(),categories=db.execute("SELECT * FROM categories ORDER BY name").fetchall(),tags=db.execute("SELECT * FROM tags ORDER BY name").fetchall())
@bp.post("/user/<int:uid>/ban")

@admin_required
def ban(uid):
    db=get_db();u=db.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
    if not u:abort(404)
    if u["role"]!="admin":db.execute("UPDATE users SET banned=1 WHERE id=?",(uid,));db.commit()
    return redirect(url_for("admin.dashboard"))

@bp.post("/user/<int:uid>/unban")
@admin_required
def unban(uid):
    db=get_db()
    if not db.execute("SELECT 1 FROM users WHERE id=?",(uid,)).fetchone():abort(404)
    db.execute("UPDATE users SET banned=0 WHERE id=?",(uid,));db.commit();return redirect(url_for("admin.dashboard"))

@bp.post("/post/<int:pid>/delete")
@admin_required
def dp(pid):
    db=get_db()
    if not db.execute("SELECT 1 FROM posts WHERE id=?",(pid,)).fetchone():abort(404)
    db.execute("DELETE FROM posts WHERE id=?",(pid,));db.commit();return redirect(url_for("admin.dashboard"))

@bp.post("/comment/<int:cid>/delete")
@admin_required
def dc(cid):
    db=get_db()
    if not db.execute("SELECT 1 FROM comments WHERE id=?",(cid,)).fetchone():abort(404)
    db.execute("DELETE FROM comments WHERE id=?",(cid,));db.commit();return redirect(url_for("admin.dashboard"))

@bp.post("/category")
@admin_required
def addcat():
    n=" ".join(request.form.get("name","").strip().split());db=get_db()
    if not 2<=len(n)<=50:flash("Категория: 2–50 символов.","error")
    else:
        try:db.execute("INSERT INTO categories(name) VALUES(?)",(n,));db.commit()
        except Exception:flash("Такая категория уже существует.","error")
    return redirect(url_for("admin.dashboard"))

@bp.post("/category/<int:cid>/delete")
@admin_required
def delcat(cid):
    db=get_db();affected=db.execute("SELECT COUNT(*) FROM posts WHERE category_id=?",(cid,)).fetchone()[0]
    if not db.execute("SELECT 1 FROM categories WHERE id=?",(cid,)).fetchone():abort(404)
    db.execute("DELETE FROM categories WHERE id=?",(cid,));db.commit();flash(f"Категория удалена. {affected} пост(ов) теперь без категории.","success");return redirect(url_for("admin.dashboard"))

@bp.post("/tag/<int:tid>/delete")
@admin_required
def deltag(tid):
    db=get_db()
    if not db.execute("SELECT 1 FROM tags WHERE id=?",(tid,)).fetchone():abort(404)
    db.execute("DELETE FROM tags WHERE id=?",(tid,));db.commit();return redirect(url_for("admin.dashboard"))