"""Authentication routes and access-control helpers."""
import os, re, sqlite3, time
from functools import wraps
from urllib.parse import urlparse
from flask import Blueprint, request, redirect, url_for, session, flash, abort, render_template, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from .db import db

auth_bp = Blueprint("auth", __name__)
LOGIN_ATTEMPTS = {}
LOGIN_WINDOW_SECONDS = 900
LOGIN_MAX_ATTEMPTS = 5

def current_user():
    if "user_id" not in session:
        return None
    conn = db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    if user and user["banned"]:
        session.clear()
        return None
    return user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            return redirect(url_for('auth.login', next=request.path))
        if user["banned"]:
            session.clear()
            flash("Ваш аккаунт заблокирован.", "error")
            return redirect(url_for('auth.login'))
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


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if password != request.form.get("password_confirm", ""):
            flash("Пароли не совпадают.", "error")
        elif (not 3 <= len(username) <= 30 or not re.fullmatch(r"[A-Za-zА-Яа-яЁё0-9_.-]+", username)
              or len(password) < 6 or len(password) > 128 or len(email) > 254
              or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)):
            flash("Проверьте логин (3–30 символов), email и пароль (6–128 символов).", "error")
        else:
            conn = db()
            try:
                conn.execute(
                    "INSERT INTO users(username,email,password) VALUES(?,?,?)",
                    (username, email, generate_password_hash(password))
                )
                conn.commit()
                flash("Регистрация успешна. Теперь войдите.", "success")
                return redirect(url_for('auth.login'))
            except sqlite3.IntegrityError:
                flash("Такой логин или email уже занят.", "error")
            finally:
                pass
    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identity = request.form.get("identity", "").strip()
        key = request.remote_addr or "unknown"
        now = time.time()
        attempts = [t for t in LOGIN_ATTEMPTS.get(key, []) if now - t < LOGIN_WINDOW_SECONDS]
        LOGIN_ATTEMPTS[key] = attempts
        user = None
        if len(attempts) < LOGIN_MAX_ATTEMPTS:
            user = db().execute("SELECT * FROM users WHERE username=? OR email=?",
                                (identity, identity.lower())).fetchone()
        password = request.form.get("password", "")
        if len(attempts) < LOGIN_MAX_ATTEMPTS and user and check_password_hash(user["password"], password) and not user["banned"]:
            LOGIN_ATTEMPTS.pop(key, None)
            session.clear()
            session["user_id"] = user["id"]
            target = request.args.get("next", "")
            if target.startswith("/") and not target.startswith("//") and not urlparse(target).netloc:
                return redirect(target)
            return redirect(url_for('posts.index'))
        attempts.append(now)
        LOGIN_ATTEMPTS[key] = attempts
        flash("Неверные данные или аккаунт заблокирован. При превышении лимита подождите 15 минут.", "error")
    return render_template("login.html")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for('posts.index'))

