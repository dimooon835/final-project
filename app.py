import os,secrets
from pathlib import Path
from functools import wraps
from urllib.parse import urlparse
from flask import Flask,abort,flash,redirect,render_template,request,session,url_for
from dotenv import load_dotenv
from db import get_db,close_db,init_db


load_dotenv(Path(__file__).resolve().parent/".env")
app=Flask(__name__)
app.config.update(SECRET_KEY=os.getenv("SECRET_KEY") or "dev-secret-change-me",DATABASE=str(Path(__file__).resolve().parent/"blog.db"),MAX_CONTENT_LENGTH=2*1024*1024,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE="Lax")

def csrf_token():
    session.setdefault("_csrf",secrets.token_urlsafe(32)); return session["_csrf"]

def current_user():
    uid=session.get("user_id")
    if not uid:return None
    u=get_db().execute("SELECT id,username,email,role,banned,created_at FROM users WHERE id=?",(uid,)).fetchone()
    if not u or u["banned"]: session.pop("user_id",None); return None
    return u

def login_required(fn):
    @wraps(fn)
    def wrap(*a,**kw):
        if not current_user(): flash("Войдите в аккаунт.","error"); return redirect(url_for("auth.login",next=request.path))
        return fn(*a,**kw)
    return wrap

def admin_required(fn):
    @wraps(fn)
    def wrap(*a,**kw):
        u=current_user()
        if not u: return redirect(url_for("auth.login",next=request.path))
        if u["role"]!="admin": abort(403)
        return fn(*a,**kw)
    return wrap

def safe_next(v):
    if not v:return url_for("posts.index")
    p=urlparse(v)
    return v if v.startswith("/") and not v.startswith("//") and not p.scheme and not p.netloc else url_for("posts.index")

@app.before_request
def csrf():
    if request.method=="POST" and request.form.get("_csrf")!=session.get("_csrf"): abort(400,"Недействительный CSRF-токен.")

@app.context_processor
def globals_(): return {"current_user":current_user,"csrf_token":csrf_token}

@app.template_filter("preview")
def preview(v,n=280):
    s=" ".join((v or "").split()); return s if len(s)<=n else s[:n].rstrip()+"…"

@app.errorhandler(400)
def e400(e): return render_template("error.html",code=400,title="Некорректный запрос",message=getattr(e,"description","Проверьте данные.")),400

@app.errorhandler(403)
def e403(e): return render_template("error.html",code=403,title="Доступ запрещён",message="У вас нет прав для этого действия."),403

@app.errorhandler(404)
def e404(e): return render_template("error.html",code=404,title="Не найдено",message="Запись или страница не существует."),404

@app.errorhandler(500)
def e500(e): return render_template("error.html",code=500,title="Ошибка сервера",message="Произошла внутренняя ошибка."),500

@app.teardown_appcontext
def td(e=None): close_db()


from blueprints.auth import bp as auth_bp
from blueprints.posts import bp as posts_bp
from blueprints.admin import bp as admin_bp


app.register_blueprint(auth_bp); app.register_blueprint(posts_bp); app.register_blueprint(admin_bp)
with app.app_context(): init_db()
if __name__=="__main__": app.run(debug=True)