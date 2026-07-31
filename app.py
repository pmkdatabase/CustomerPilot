from flask import Flask, render_template, redirect, url_for, flash, request, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Product, Purchase, ReplacementRequest, AuthorizedUser
from datetime import datetime
import os

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-secret-change-in-production"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///customerpilot.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message_category = "warning"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return redirect(url_for("dashboard") if current_user.is_authenticated else url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email     = request.form["email"].strip().lower()
        full_name = request.form["full_name"].strip()
        password  = request.form["password"]
        if User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "danger")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
        else:
            user = User(email=email, full_name=full_name,
                        password_hash=generate_password_hash(password))
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("Welcome to CustomerPilot!", "success")
            return redirect(url_for("dashboard"))
    return render_template("auth/register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email    = request.form["email"].strip().lower()
        password = request.form["password"]
        user     = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("auth/login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ── Customer ──────────────────────────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    if current_user.is_admin:
        return redirect(url_for("admin_dashboard"))
    purchases = Purchase.query.filter_by(user_id=current_user.id).all()
    return render_template("customer/dashboard.html", purchases=purchases)


@app.route("/purchase/<int:purchase_id>")
@login_required
def purchase_detail(purchase_id):
    p = Purchase.query.get_or_404(purchase_id)
    if p.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    return render_template("customer/purchase_detail.html", purchase=p)


@app.route("/purchase/<int:purchase_id>/replacement", methods=["POST"])
@login_required
def request_replacement(purchase_id):
    p = Purchase.query.get_or_404(purchase_id)
    if p.user_id != current_user.id:
        abort(403)
    reason = request.form["reason"].strip()
    if not reason:
        flash("Please describe the reason for replacement.", "danger")
        return redirect(url_for("purchase_detail", purchase_id=purchase_id))
    rr = ReplacementRequest(purchase_id=purchase_id, reason=reason)
    db.session.add(rr)
    db.session.commit()
    flash("Replacement request submitted.", "success")
    return redirect(url_for("purchase_detail", purchase_id=purchase_id))


@app.route("/purchase/<int:purchase_id>/authorize", methods=["POST"])
@login_required
def add_authorized_user(purchase_id):
    p = Purchase.query.get_or_404(purchase_id)
    if p.user_id != current_user.id:
        abort(403)
    name  = request.form["name"].strip()
    email = request.form["email"].strip().lower()
    if not name or not email:
        flash("Name and email are required.", "danger")
        return redirect(url_for("purchase_detail", purchase_id=purchase_id))
    au = AuthorizedUser(purchase_id=purchase_id, name=name, email=email)
    db.session.add(au)
    db.session.commit()
    flash(f"{name} added as an authorized user.", "success")
    return redirect(url_for("purchase_detail", purchase_id=purchase_id))


@app.route("/purchase/<int:purchase_id>/authorize/<int:auth_id>/remove", methods=["POST"])
@login_required
def remove_authorized_user(purchase_id, auth_id):
    p  = Purchase.query.get_or_404(purchase_id)
    au = AuthorizedUser.query.get_or_404(auth_id)
    if p.user_id != current_user.id:
        abort(403)
    db.session.delete(au)
    db.session.commit()
    flash("Authorized user removed.", "info")
    return redirect(url_for("purchase_detail", purchase_id=purchase_id))


# ── Admin ─────────────────────────────────────────────────────────────────────

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


@app.route("/admin")
@login_required
@admin_required
def admin_dashboard():
    users     = User.query.filter_by(is_admin=False).order_by(User.created_at.desc()).all()
    pending   = ReplacementRequest.query.filter_by(status="pending").count()
    return render_template("admin/dashboard.html", users=users, pending=pending)


@app.route("/admin/replacements")
@login_required
@admin_required
def admin_replacements():
    requests = (ReplacementRequest.query
                .order_by(ReplacementRequest.created_at.desc()).all())
    return render_template("admin/replacements.html", requests=requests)


@app.route("/admin/replacement/<int:rr_id>/<action>", methods=["POST"])
@login_required
@admin_required
def admin_replacement_action(rr_id, action):
    rr = ReplacementRequest.query.get_or_404(rr_id)
    if action in ("approved", "rejected"):
        rr.status = action
        db.session.commit()
        flash(f"Request {action}.", "success")
    return redirect(url_for("admin_replacements"))


@app.route("/admin/products", methods=["GET", "POST"])
@login_required
@admin_required
def admin_products():
    if request.method == "POST":
        name = request.form["name"].strip()
        sku  = request.form["sku"].strip()
        desc = request.form["description"].strip()
        if not name or not sku:
            flash("Name and SKU are required.", "danger")
        elif Product.query.filter_by(sku=sku).first():
            flash("SKU already exists.", "danger")
        else:
            db.session.add(Product(name=name, sku=sku, description=desc))
            db.session.commit()
            flash("Product added.", "success")
    products = Product.query.order_by(Product.name).all()
    return render_template("admin/products.html", products=products)


@app.route("/admin/assign", methods=["GET", "POST"])
@login_required
@admin_required
def admin_assign():
    if request.method == "POST":
        user_id    = request.form["user_id"]
        product_id = request.form["product_id"]
        serial_no  = request.form["serial_no"].strip()
        p = Purchase(user_id=user_id, product_id=product_id, serial_no=serial_no)
        db.session.add(p)
        db.session.commit()
        flash("Product assigned to customer.", "success")
        return redirect(url_for("admin_assign"))
    users    = User.query.filter_by(is_admin=False).order_by(User.full_name).all()
    products = Product.query.order_by(Product.name).all()
    return render_template("admin/assign.html", users=users, products=products)


# ── Seed & run ────────────────────────────────────────────────────────────────

def seed_demo():
    if User.query.first():
        return
    admin = User(email="admin@demo.com", full_name="Admin",
                 password_hash=generate_password_hash("Admin@2026!"), is_admin=True)
    customer = User(email="customer@demo.com", full_name="Jane Smith",
                    password_hash=generate_password_hash("Customer@2026!"))
    db.session.add_all([admin, customer])
    db.session.flush()

    p1 = Product(name="ControlMaster Pro", sku="CMP-001",
                 description="Industrial control system software")
    p2 = Product(name="DataSync Module", sku="DSM-002",
                 description="Real-time data synchronization module")
    db.session.add_all([p1, p2])
    db.session.flush()

    pur = Purchase(user_id=customer.id, product_id=p1.id, serial_no="SN-10042")
    db.session.add(pur)
    db.session.commit()
    print("Demo data seeded. admin@demo.com / Admin@2026!  |  customer@demo.com / Customer@2026!")


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        seed_demo()
    app.run(debug=True)
