from flask import Blueprint, render_template
from app.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("auth", __name__)


@bp.route("/")
def home():
    return render_template("home.html")
