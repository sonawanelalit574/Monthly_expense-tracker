from __future__ import annotations

from datetime import date, datetime

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()

ACCOUNT_TYPES = ("personal", "business", "student")


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False, default="")
    account_type = db.Column(db.String(20), nullable=False, default="personal")
    base_currency = db.Column(db.String(8), nullable=False, default="INR")
    organization = db.Column(db.String(160), default="")
    city = db.Column(db.String(80), default="")
    vault_pin_hash = db.Column(db.String(256), default="")
    google_sub = db.Column(db.String(128), default="", index=True)
    auth_provider = db.Column(db.String(20), default="password")
    bank_name = db.Column(db.String(120), default="")
    salary_credit_day = db.Column(db.Integer, default=1)
    last_login_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    incomes = db.relationship("Income", backref="user", cascade="all, delete-orphan")
    transactions = db.relationship("Txn", backref="user", cascade="all, delete-orphan")
    sips = db.relationship("Sip", backref="user", cascade="all, delete-orphan")
    savings = db.relationship("SavingPlan", backref="user", cascade="all, delete-orphan")
    emis = db.relationship("Emi", backref="user", cascade="all, delete-orphan")
    vault_items = db.relationship("VaultItem", backref="user", cascade="all, delete-orphan")
    budgets = db.relationship("Budget", backref="user", cascade="all, delete-orphan")
    bills = db.relationship("Bill", backref="user", cascade="all, delete-orphan")
    notes = db.relationship("Memo", backref="user", cascade="all, delete-orphan")

    def set_password(self, raw: str) -> None:
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw: str) -> bool:
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, raw)

    def public(self) -> dict:
        return {
            "id": self.id,
            "full_name": self.full_name,
            "email": self.email,
            "account_type": self.account_type,
            "base_currency": self.base_currency,
            "organization": self.organization or "",
            "city": self.city or "",
            "has_vault_pin": bool(self.vault_pin_hash),
            "auth_provider": self.auth_provider or "password",
            "bank_name": self.bank_name or "",
            "salary_credit_day": self.salary_credit_day or 1,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else "",
        }

    def set_vault_pin(self, pin: str) -> None:
        self.vault_pin_hash = generate_password_hash(pin)

    def check_vault_pin(self, pin: str) -> bool:
        if not self.vault_pin_hash:
            return False
        return check_password_hash(self.vault_pin_hash, pin)


class Income(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    source = db.Column(db.String(80), default="salary")
    amount = db.Column(db.Float, nullable=False)
    month = db.Column(db.String(7), nullable=False)
    credit_day = db.Column(db.Integer, default=1)
    notes = db.Column(db.String(400), default="")
    credit_code = db.Column(db.String(80), default="")
    bank_name = db.Column(db.String(120), default="")
    credit_date = db.Column(db.Date)

    def public(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "source": self.source,
            "amount": self.amount,
            "month": self.month,
            "credit_day": self.credit_day,
            "notes": self.notes or "",
            "credit_code": self.credit_code or "",
            "bank_name": self.bank_name or "",
            "credit_date": self.credit_date.isoformat() if self.credit_date else "",
        }


class Txn(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    channel = db.Column(db.String(20), nullable=False)  # phone, cash, card, bank
    direction = db.Column(db.String(12), nullable=False, default="out")  # in/out
    amount = db.Column(db.Float, nullable=False)
    occurred_on = db.Column(db.Date, nullable=False, default=date.today)
    merchant = db.Column(db.String(160), default="")
    notes = db.Column(db.String(400), default="")

    def public(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "channel": self.channel,
            "direction": self.direction,
            "amount": self.amount,
            "occurred_on": self.occurred_on.isoformat(),
            "merchant": self.merchant or "",
            "notes": self.notes or "",
        }


class Sip(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    name = db.Column(db.String(160), nullable=False)
    monthly_amount = db.Column(db.Float, nullable=False)
    expected_return = db.Column(db.Float, default=12.0)
    start_month = db.Column(db.String(7), nullable=False)
    tenure_months = db.Column(db.Integer, default=120)
    folio = db.Column(db.String(80), default="")

    def public(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "monthly_amount": self.monthly_amount,
            "expected_return": self.expected_return,
            "start_month": self.start_month,
            "tenure_months": self.tenure_months,
            "folio": self.folio or "",
        }


class SavingPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    name = db.Column(db.String(160), nullable=False)
    kind = db.Column(db.String(40), default="emergency")  # emergency, fd, rd, goal
    target_amount = db.Column(db.Float, nullable=False)
    current_amount = db.Column(db.Float, default=0)
    monthly_contribution = db.Column(db.Float, default=0)
    notes = db.Column(db.String(400), default="")

    def public(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "target_amount": self.target_amount,
            "current_amount": self.current_amount,
            "monthly_contribution": self.monthly_contribution,
            "notes": self.notes or "",
        }


class Emi(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    name = db.Column(db.String(160), nullable=False)
    principal = db.Column(db.Float, nullable=False)
    annual_rate = db.Column(db.Float, nullable=False)
    tenure_months = db.Column(db.Integer, nullable=False)
    start_month = db.Column(db.String(7), nullable=False)
    paid_installments = db.Column(db.Integer, default=0)

    def public(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "principal": self.principal,
            "annual_rate": self.annual_rate,
            "tenure_months": self.tenure_months,
            "start_month": self.start_month,
            "paid_installments": self.paid_installments,
        }


class VaultItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    label = db.Column(db.String(160), nullable=False)
    login_id = db.Column(db.String(200), default="")
    secret_blob = db.Column(db.Text, nullable=False)
    website = db.Column(db.String(240), default="")
    category = db.Column(db.String(40), default="login")
    notes = db.Column(db.String(400), default="")

    def public(self, secret: str | None = None) -> dict:
        payload = {
            "id": self.id,
            "label": self.label,
            "login_id": self.login_id or "",
            "website": self.website or "",
            "category": self.category,
            "notes": self.notes or "",
        }
        if secret is not None:
            payload["password"] = secret
        return payload


class Budget(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    monthly_limit = db.Column(db.Float, nullable=False)

    def public(self) -> dict:
        return {"id": self.id, "category": self.category, "monthly_limit": self.monthly_limit}


class Bill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    name = db.Column(db.String(160), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    due_day = db.Column(db.Integer, default=5)
    category = db.Column(db.String(80), default="utility")
    auto_pay = db.Column(db.Boolean, default=False)

    def public(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "amount": self.amount,
            "due_day": self.due_day,
            "category": self.category,
            "auto_pay": self.auto_pay,
        }


class Memo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    body = db.Column(db.Text, default="")
    tag = db.Column(db.String(40), default="general")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def public(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "body": self.body or "",
            "tag": self.tag,
            "created_at": self.created_at.isoformat() if self.created_at else "",
        }
