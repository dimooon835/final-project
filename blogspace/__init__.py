"""Application factory for BlogSpace."""
import os, secrets
from flask import Flask, request, session, abort, render_template
from dotenv import load_dotenv
from .db import init_db, close_db
from .auth import auth_bp, current_user
from .posts import posts_bp
from .admin import admin_bp


def create_app():
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
    app = Flask(__name__)
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key or len(secret_key) < 32:
        raise RuntimeError("Задайте SECRET_KEY длиной не менее 32 символов в .env или окружении.")
    app.config.update(SECRET_KEY=secret_key, SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE="Lax",
                      SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1")

    app.teardown_appcontext(close_db)
    app.register_blueprint(auth_bp)
    app.register_blueprint(posts_bp)
    app.register_blueprint(admin_bp)

    @app.before_request
    def protect_post_requests():
        if request.method == "POST":
            expected = session.get("_csrf_token")
            supplied = request.form.get("_csrf_token", "")
            if not expected or not secrets.compare_digest(expected, supplied):
                abort(400, description="Недействительный CSRF-токен.")

    @app.context_processor
    def inject_globals():
        if "_csrf_token" not in session:
            session["_csrf_token"] = secrets.token_urlsafe(32)
        return {"csrf_token": session["_csrf_token"], "current_user": current_user()}

    @app.errorhandler(400)
    def bad_request(error):
        return render_template("error.html", code=400, message="Некорректный запрос."), 400
    @app.errorhandler(403)
    def forbidden(error):
        return render_template("error.html", code=403, message="У вас нет доступа к этой странице."), 403
    @app.errorhandler(404)
    def not_found(error):
        return render_template("error.html", code=404, message="Страница не найдена."), 404
    @app.errorhandler(500)
    def server_error(error):
        app.logger.exception("Внутренняя ошибка сервера")
        return render_template("error.html", code=500, message="Внутренняя ошибка. Попробуйте позже."), 500

    with app.app_context():
        init_db()
    return app
