from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()


class User(UserMixin, db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name     = db.Column(db.String(150), nullable=False)
    is_admin      = db.Column(db.Boolean, default=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    purchases     = db.relationship("Purchase", backref="owner", lazy=True,
                                    foreign_keys="Purchase.user_id")


class Product(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(200), nullable=False)
    sku         = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)


class Purchase(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    product_id   = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    purchased_at = db.Column(db.DateTime, default=datetime.utcnow)
    serial_no    = db.Column(db.String(100))

    product      = db.relationship("Product")
    replacements = db.relationship("ReplacementRequest", backref="purchase", lazy=True)
    authorized   = db.relationship("AuthorizedUser", backref="purchase", lazy=True)


class ReplacementRequest(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey("purchase.id"), nullable=False)
    reason      = db.Column(db.Text, nullable=False)
    status      = db.Column(db.String(50), default="pending")  # pending, approved, rejected
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)


class AuthorizedUser(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey("purchase.id"), nullable=False)
    name        = db.Column(db.String(150), nullable=False)
    email       = db.Column(db.String(150), nullable=False)
    added_at    = db.Column(db.DateTime, default=datetime.utcnow)
