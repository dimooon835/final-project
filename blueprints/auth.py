import re,time,secrets
from flask import Blueprint,flash,redirect,render_template,request,session,url_for
from werkzeug.security import check_password_hash,generate_password_hash
from db import get_db


bp=Blueprint("auth",__name__)
def safe_next(v):
    from app import safe_next as s; return s(v)

@bp.route("/register",methods=["GET","POST"])
def register():
    f=request.form if request.method=="POST" else {}
    if request.method=="POST":
        u=f.get("username","").strip(); e=f.get("email","").strip().lower(); p=f.get("password",""); c=f.get("password_confirm","")
        ok=True
        if not(3<=len(u)<=32) or not re.fullmatch(r"[A-Za-z0-9_.-]+",u): flash("Логин: 3–32 символа, только буквы, цифры, ., _ и -.","error"); ok=False
        elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+",e) or len(e)>254: flash("Введите корректный email.","error"); ok=False
        elif not(6<=len(p)<=128): flash("Пароль должен быть длиной 6–128 символов.","error"); ok=False
        elif p!=c: flash("Пароли не совпадают.","error"); ok=False
        if ok:
            try:
                db=get_db(); db.execute("INSERT INTO users(username,email,password) VALUES(?,?,?)",(u,e,generate_password_hash(p))); db.commit()
                flash("Регистрация завершена.","success"); return redirect(url_for("auth.login"))
            except Exception: flash("Такой логин или email уже используется.","error")
    return render_template("register.html",form=f)

@bp.route("/login",methods=["GET","POST"])
def login():
    f=request.form if request.method=="POST" else {}; nxt=f.get("next","") if request.method=="POST" else request.args.get("next","")
    if request.method=="POST":
        attempts=[x for x in session.get("login_attempts",[]) if time.time()-x<900]
        if len(attempts)>=10: flash("Слишком много попыток. Попробуйте через 15 минут.","error"); return render_template("login.html",form=f,next_url=safe_next(nxt))
        u=get_db().execute("SELECT * FROM users WHERE username=?",(f.get("username","").strip(),)).fetchone()
        if u and check_password_hash(u["password"],f.get("password","")) and not u["banned"]:
            session.clear(); session["user_id"]=u["id"]; session["_csrf"]=secrets.token_urlsafe(32); return redirect(safe_next(nxt))
        attempts.append(time.time()); session["login_attempts"]=attempts; flash("Неверный логин или пароль.","error")
    return render_template("login.html",form=f,next_url=safe_next(nxt))

@bp.post("/logout")
def logout(): session.clear(); flash("Вы вышли из аккаунта.","success"); return redirect(url_for("posts.index"))