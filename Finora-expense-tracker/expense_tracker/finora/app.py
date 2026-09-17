from __future__ import annotations

import os
import secrets
from calendar import monthrange
from datetime import date, datetime, timedelta
from functools import wraps

import requests
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import text

from finora.credits import next_credit_date, salary_credit_code
from finora.csv_import import parse_csv_bytes
from finora.currency import COUNTRIES, convert as fx_convert, fetch_usd_rates
from finora.finance import emi_amount, in_month, month_key, months_elapsed, sip_future_value, suggested_daily_spend
from finora.models import ACCOUNT_TYPES, Bill, Budget, Emi, Income, Memo, SavingPlan, Sip, Txn, User, VaultItem, db
from finora.vault import decrypt_secret, encrypt_secret


CATEGORIES = {
    "personal": ["Housing", "Groceries", "Dining", "Transport", "Utilities", "Health", "Subscriptions", "Shopping", "Family", "Other"],
    "business": ["Payroll", "Vendors", "Tax", "Facilities", "Software", "Travel", "Marketing", "Inventory", "Insurance", "Other"],
    "student": ["Fees", "Hostel", "Food", "Supplies", "Transport", "Books", "Exam", "Personal", "Other"],
}


def _migrate(database) -> None:
    engine = database.engine
    with engine.begin() as conn:
        user_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(user)"))}
        user_add = {
            "google_sub": "VARCHAR(128) DEFAULT ''",
            "auth_provider": "VARCHAR(20) DEFAULT 'password'",
            "bank_name": "VARCHAR(120) DEFAULT ''",
            "salary_credit_day": "INTEGER DEFAULT 1",
            "last_login_at": "DATETIME",
        }
        for name, ddl in user_add.items():
            if name not in user_cols:
                conn.execute(text(f"ALTER TABLE user ADD COLUMN {name} {ddl}"))
        income_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(income)"))}
        income_add = {
            "credit_code": "VARCHAR(80) DEFAULT ''",
            "bank_name": "VARCHAR(120) DEFAULT ''",
            "credit_date": "DATE",
        }
        for name, ddl in income_add.items():
            if name not in income_cols:
                conn.execute(text(f"ALTER TABLE income ADD COLUMN {name} {ddl}"))


def create_app() -> Flask:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    app = Flask(
        __name__,
        template_folder=os.path.join(root, "templates"),
        static_folder=os.path.join(root, "static"),
    )
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "finora-dev-key-change-in-production")
    app.permanent_session_lifetime = timedelta(days=30)
    app.config["GOOGLE_CLIENT_ID"] = os.environ.get("GOOGLE_CLIENT_ID", "")
    app.config["GOOGLE_CLIENT_SECRET"] = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    db_path = os.path.join(root, "finora.db").replace("\\", "/")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + db_path
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.create_all()
        _migrate(db)

    def current_user() -> User | None:
        uid = session.get("uid")
        if not uid:
            return None
        return db.session.get(User, uid)

    def login_required(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                if request.path.startswith("/api/"):
                    return jsonify({"ok": False, "error": "Please sign in."}), 401
                return redirect("/login")
            return fn(user, *args, **kwargs)

        return wrapped

    def json_error(message: str, status: int = 400):
        return jsonify({"ok": False, "error": message}), status

    def _sign_in(user: User, remember: bool = False) -> None:
        session["uid"] = user.id
        session.permanent = bool(remember)
        user.last_login_at = datetime.utcnow()
        db.session.commit()

    @app.get("/")
    def landing():
        if current_user():
            return redirect("/app")
        return render_template("landing.html")

    @app.get("/login")
    def login_page():
        if current_user():
            return redirect("/app")
        return render_template(
            "auth.html",
            mode="login",
            google_client_id=app.config["GOOGLE_CLIENT_ID"],
        )

    @app.get("/register")
    def register_page():
        if current_user():
            return redirect("/app")
        return render_template(
            "auth.html",
            mode="register",
            google_client_id=app.config["GOOGLE_CLIENT_ID"],
        )

    @app.get("/app")
    @login_required
    def workspace(user: User):
        return render_template("workspace.html", user=user)

    @app.post("/api/auth/register")
    def api_register():
        payload = request.get_json(silent=True) or {}
        name = (payload.get("full_name") or "").strip()
        email = (payload.get("email") or "").strip().lower()
        password = payload.get("password") or ""
        account_type = (payload.get("account_type") or "personal").strip()
        organization = (payload.get("organization") or "").strip()
        city = (payload.get("city") or "").strip()
        currency = (payload.get("base_currency") or "INR").upper()
        if account_type not in ACCOUNT_TYPES:
            return json_error("Choose personal, business, or student.")
        if len(name) < 2 or "@" not in email or len(password) < 6:
            return json_error("Name, a valid email, and a password of 6+ characters are required.")
        if User.query.filter_by(email=email).first():
            return json_error("An account already exists with that email.")
        user = User(
            full_name=name,
            email=email,
            account_type=account_type,
            base_currency=currency,
            organization=organization,
            city=city,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        _sign_in(user, remember=bool(payload.get("remember")))
        return jsonify({"ok": True, "user": user.public()})

    @app.post("/api/auth/login")
    def api_login():
        payload = request.get_json(silent=True) or {}
        email = (payload.get("email") or "").strip().lower()
        password = payload.get("password") or ""
        wanted = (payload.get("account_type") or "").strip()
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            return json_error("Email or password is incorrect.", 401)
        if wanted and wanted != user.account_type:
            return json_error(f"This login is a {user.account_type} workspace, not {wanted}.", 403)
        _sign_in(user, remember=bool(payload.get("remember")))
        return jsonify({"ok": True, "user": user.public()})

    @app.post("/api/auth/logout")
    def api_logout():
        session.clear()
        return jsonify({"ok": True})

    @app.post("/api/auth/google")
    def api_google():
        payload = request.get_json(silent=True) or {}
        credential = payload.get("credential") or ""
        account_type = (payload.get("account_type") or "personal").strip()
        if account_type not in ACCOUNT_TYPES:
            account_type = "personal"
        if not credential:
            return json_error("Google did not return a credential.")
        try:
            info = requests.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": credential},
                timeout=12,
            )
            info.raise_for_status()
            data = info.json()
        except requests.RequestException:
            return json_error("Google could not verify this sign-in.", 401)
        client_id = app.config["GOOGLE_CLIENT_ID"]
        if client_id and data.get("aud") != client_id:
            return json_error("Google client id does not match this app.", 401)
        if data.get("email_verified") not in {True, "true"}:
            return json_error("Google email is not verified.", 401)
        email = (data.get("email") or "").lower()
        if not email:
            return json_error("Google account has no email.")
        user = User.query.filter_by(email=email).first()
        if not user:
            user = User(
                full_name=(data.get("name") or email.split("@")[0]).strip(),
                email=email,
                account_type=account_type,
                google_sub=data.get("sub") or "",
                auth_provider="google",
            )
            user.set_password(secrets.token_urlsafe(24))
            db.session.add(user)
        else:
            user.google_sub = data.get("sub") or user.google_sub
            user.auth_provider = "google" if not user.password_hash else user.auth_provider
        db.session.commit()
        _sign_in(user, remember=True)
        return jsonify({"ok": True, "user": user.public()})

    @app.get("/auth/google")
    def google_start():
        client_id = app.config["GOOGLE_CLIENT_ID"]
        secret = app.config["GOOGLE_CLIENT_SECRET"]
        if not client_id or not secret:
            return redirect("/login?google=setup")
        from urllib.parse import urlencode

        session["google_state"] = secrets.token_urlsafe(16)
        session["google_type"] = request.args.get("type") or "personal"
        params = urlencode(
            {
                "client_id": client_id,
                "redirect_uri": url_for("google_callback", _external=True),
                "response_type": "code",
                "scope": "openid email profile",
                "state": session["google_state"],
                "access_type": "online",
                "prompt": "select_account",
            }
        )
        return redirect("https://accounts.google.com/o/oauth2/v2/auth?" + params)

    @app.get("/auth/google/callback")
    def google_callback():
        if request.args.get("state") != session.get("google_state"):
            return redirect("/login?google=state")
        code = request.args.get("code")
        if not code:
            return redirect("/login?google=denied")
        token_res = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": app.config["GOOGLE_CLIENT_ID"],
                "client_secret": app.config["GOOGLE_CLIENT_SECRET"],
                "redirect_uri": url_for("google_callback", _external=True),
                "grant_type": "authorization_code",
            },
            timeout=12,
        )
        if token_res.status_code >= 400:
            return redirect("/login?google=token")
        id_token = token_res.json().get("id_token")
        try:
            info = requests.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": id_token},
                timeout=12,
            ).json()
        except requests.RequestException:
            return redirect("/login?google=token")
        email = (info.get("email") or "").lower()
        if not email:
            return redirect("/login?google=email")
        account_type = session.get("google_type") or "personal"
        if account_type not in ACCOUNT_TYPES:
            account_type = "personal"
        user = User.query.filter_by(email=email).first()
        if not user:
            user = User(
                full_name=(info.get("name") or email.split("@")[0]).strip(),
                email=email,
                account_type=account_type,
                google_sub=info.get("sub") or "",
                auth_provider="google",
            )
            user.set_password(secrets.token_urlsafe(24))
            db.session.add(user)
        db.session.commit()
        _sign_in(user, remember=True)
        return redirect("/app")

    @app.get("/api/me")
    @login_required
    def api_me(user: User):
        return jsonify({"ok": True, "user": user.public(), "categories": CATEGORIES[user.account_type]})

    @app.post("/api/me")
    @login_required
    def api_me_update(user: User):
        payload = request.get_json(silent=True) or {}
        if "full_name" in payload:
            user.full_name = (payload.get("full_name") or user.full_name).strip()
        if "organization" in payload:
            user.organization = (payload.get("organization") or "").strip()
        if "city" in payload:
            user.city = (payload.get("city") or "").strip()
        if "base_currency" in payload:
            user.base_currency = (payload.get("base_currency") or "INR").upper()
        if "bank_name" in payload:
            user.bank_name = (payload.get("bank_name") or "").strip()
        if "salary_credit_day" in payload:
            try:
                user.salary_credit_day = max(1, min(28, int(payload.get("salary_credit_day") or 1)))
            except (TypeError, ValueError):
                pass
        db.session.commit()
        return jsonify({"ok": True, "user": user.public()})

    @app.get("/api/overview")
    @login_required
    def api_overview(user: User):
        month = (request.args.get("month") or month_key()).strip()
        incomes = [row for row in user.incomes if row.month == month]
        txns = [row for row in user.transactions if in_month(row.occurred_on, month)]
        salary = sum(row.amount for row in incomes)
        spent = sum(row.amount for row in txns if row.direction == "out")
        extra_in = sum(row.amount for row in txns if row.direction == "in")
        income_total = salary + extra_in
        sip_out = sum(row.monthly_amount for row in user.sips)
        save_out = sum(row.monthly_contribution for row in user.savings)
        emi_out = 0.0
        emi_rows = []
        for row in user.emis:
            installment = emi_amount(row.principal, row.annual_rate, row.tenure_months)
            emi_out += installment
            remaining = max(0, row.tenure_months - row.paid_installments)
            emi_rows.append({**row.public(), "installment": round(installment, 2), "remaining": remaining})
        committed = sip_out + save_out + emi_out
        leftover = income_total - spent - committed
        phone = sum(row.amount for row in txns if row.channel == "phone" and row.direction == "out")
        cash = sum(row.amount for row in txns if row.channel == "cash" and row.direction == "out")
        other_ch = spent - phone - cash
        by_cat: dict[str, float] = {}
        for row in txns:
            if row.direction == "out":
                by_cat[row.category] = by_cat.get(row.category, 0) + row.amount
        sip_rows = []
        for row in user.sips:
            elapsed = months_elapsed(row.start_month, month)
            projected = sip_future_value(row.monthly_amount, row.expected_return, row.tenure_months)
            invested = row.monthly_amount * min(elapsed, row.tenure_months)
            sip_rows.append({**row.public(), "elapsed": elapsed, "invested": round(invested, 2), "projected": round(projected, 2)})
        save_rows = []
        for row in user.savings:
            pct = (row.current_amount / row.target_amount * 100) if row.target_amount else 0
            save_rows.append({**row.public(), "progress": round(pct, 1)})
        budget_rows = []
        for row in user.budgets:
            used = by_cat.get(row.category, 0)
            budget_rows.append({**row.public(), "used": used, "left": row.monthly_limit - used})
        year_map: dict[int, dict] = {}
        for row in user.incomes:
            try:
                year = int(row.month[:4])
            except (TypeError, ValueError):
                continue
            bucket = year_map.setdefault(year, {"income": 0.0, "spent": 0.0, "months": set()})
            bucket["income"] += row.amount
            bucket["months"].add(row.month)
        for row in user.transactions:
            year = row.occurred_on.year
            bucket = year_map.setdefault(year, {"income": 0.0, "spent": 0.0, "months": set()})
            if row.direction == "out":
                bucket["spent"] += row.amount
            else:
                bucket["income"] += row.amount
            bucket["months"].add(row.occurred_on.strftime("%Y-%m"))
        if not year_map:
            year_map[date.today().year] = {"income": 0.0, "spent": 0.0, "months": set()}
        years = []
        for year in sorted(year_map, reverse=True):
            bucket = year_map[year]
            years.append(
                {
                    "year": year,
                    "income": round(bucket["income"], 2),
                    "spent": round(bucket["spent"], 2),
                    "saved": round(bucket["income"] - bucket["spent"], 2),
                    "months": len(bucket["months"]),
                }
            )
        credit_on = next_credit_date(user.salary_credit_day or 1)
        next_bills = sorted(user.bills, key=lambda b: b.due_day)[:5]
        return jsonify(
            {
                "ok": True,
                "month": month,
                "kpis": {
                    "income": round(income_total, 2),
                    "spent": round(spent, 2),
                    "committed": round(committed, 2),
                    "saving": round(max(leftover, 0), 2),
                    "gap": round(leftover, 2),
                    "phone": round(phone, 2),
                    "cash": round(cash, 2),
                    "other_channels": round(max(other_ch, 0), 2),
                    "sip": round(sip_out, 2),
                    "plans": round(save_out, 2),
                    "emi": round(emi_out, 2),
                    "daily": round(suggested_daily_spend(max(leftover, 0)), 2),
                    "save_rate": round((max(leftover, 0) / income_total * 100) if income_total else 0, 1),
                },
                "donut": {
                    "spent": round(spent, 2),
                    "sip": round(sip_out, 2),
                    "plans": round(save_out, 2),
                    "emi": round(emi_out, 2),
                    "free": round(max(leftover, 0), 2),
                },
                "categories": [{"name": k, "value": round(v, 2)} for k, v in sorted(by_cat.items(), key=lambda x: -x[1])],
                "incomes": [row.public() for row in incomes],
                "transactions": [row.public() for row in sorted(txns, key=lambda r: r.occurred_on, reverse=True)],
                "sips": sip_rows,
                "savings": save_rows,
                "emis": emi_rows,
                "budgets": budget_rows,
                "bills": [row.public() for row in user.bills],
                "memos": [row.public() for row in user.notes],
                "years": years,
                "next": {
                    "salary_on": credit_on.isoformat(),
                    "salary_day": user.salary_credit_day or 1,
                    "bank": user.bank_name or "",
                    "suggested_sip": round(max(leftover, 0) * 0.4, 2),
                    "suggested_emergency": round(max(leftover, 0) * 0.3, 2),
                    "suggested_emi_buffer": round(max(leftover, 0) * 0.3, 2),
                    "bills": [row.public() for row in next_bills],
                },
            }
        )

    def _parse_date(value: str | None) -> date:
        if not value:
            return date.today()
        return datetime.strptime(value, "%Y-%m-%d").date()

    @app.post("/api/incomes")
    @login_required
    def create_income(user: User):
        payload = request.get_json(silent=True) or {}
        try:
            amount = float(payload.get("amount") or 0)
        except (TypeError, ValueError):
            return json_error("Amount must be a number.")
        if amount <= 0:
            return json_error("Amount must be greater than zero.")
        month = (payload.get("month") or month_key()).strip()
        credit_day = int(payload.get("credit_day") or user.salary_credit_day or 1)
        try:
            year, mon = [int(x) for x in month.split("-")]
            last = monthrange(year, mon)[1]
            credit_on = date(year, mon, min(max(credit_day, 1), last))
        except ValueError:
            credit_on = date.today()
        bank = (payload.get("bank_name") or user.bank_name or "").strip()
        code = salary_credit_code(credit_on, amount)
        row = Income(
            user=user,
            title=(payload.get("title") or "Income").strip(),
            source=(payload.get("source") or "salary").strip(),
            amount=amount,
            month=month,
            credit_day=credit_day,
            notes=(payload.get("notes") or "").strip(),
            credit_code=code,
            bank_name=bank,
            credit_date=credit_on,
        )
        if payload.get("source") == "salary" or (payload.get("source") or "salary") == "salary":
            user.salary_credit_day = credit_day
            if bank:
                user.bank_name = bank
        db.session.add(row)
        db.session.commit()
        return jsonify({"ok": True, "item": row.public()})

    @app.delete("/api/incomes/<int:item_id>")
    @login_required
    def delete_income(user: User, item_id: int):
        row = Income.query.filter_by(id=item_id, user_id=user.id).first()
        if not row:
            return json_error("Not found.", 404)
        db.session.delete(row)
        db.session.commit()
        return jsonify({"ok": True})

    @app.post("/api/transactions")
    @login_required
    def create_txn(user: User):
        payload = request.get_json(silent=True) or {}
        try:
            amount = float(payload.get("amount") or 0)
        except (TypeError, ValueError):
            return json_error("Amount must be a number.")
        if amount <= 0:
            return json_error("Amount must be greater than zero.")
        channel = (payload.get("channel") or "phone").strip()
        if channel not in {"phone", "cash", "card", "bank"}:
            return json_error("Channel must be phone, cash, card, or bank.")
        row = Txn(
            user=user,
            title=(payload.get("title") or "Expense").strip(),
            category=(payload.get("category") or "Other").strip(),
            channel=channel,
            direction=(payload.get("direction") or "out").strip(),
            amount=amount,
            occurred_on=_parse_date(payload.get("occurred_on")),
            merchant=(payload.get("merchant") or "").strip(),
            notes=(payload.get("notes") or "").strip(),
        )
        db.session.add(row)
        db.session.commit()
        return jsonify({"ok": True, "item": row.public()})

    @app.delete("/api/transactions/<int:item_id>")
    @login_required
    def delete_txn(user: User, item_id: int):
        row = Txn.query.filter_by(id=item_id, user_id=user.id).first()
        if not row:
            return json_error("Not found.", 404)
        db.session.delete(row)
        db.session.commit()
        return jsonify({"ok": True})

    @app.post("/api/sips")
    @login_required
    def create_sip(user: User):
        payload = request.get_json(silent=True) or {}
        row = Sip(
            user=user,
            name=(payload.get("name") or "SIP").strip(),
            monthly_amount=float(payload.get("monthly_amount") or 0),
            expected_return=float(payload.get("expected_return") or 12),
            start_month=(payload.get("start_month") or month_key()).strip(),
            tenure_months=int(payload.get("tenure_months") or 12),
            folio=(payload.get("folio") or "").strip(),
        )
        if row.monthly_amount <= 0:
            return json_error("SIP amount must be greater than zero.")
        db.session.add(row)
        db.session.commit()
        return jsonify({"ok": True, "item": row.public()})

    @app.delete("/api/sips/<int:item_id>")
    @login_required
    def delete_sip(user: User, item_id: int):
        row = Sip.query.filter_by(id=item_id, user_id=user.id).first()
        if not row:
            return json_error("Not found.", 404)
        db.session.delete(row)
        db.session.commit()
        return jsonify({"ok": True})

    @app.post("/api/savings")
    @login_required
    def create_saving(user: User):
        payload = request.get_json(silent=True) or {}
        row = SavingPlan(
            user=user,
            name=(payload.get("name") or "Plan").strip(),
            kind=(payload.get("kind") or "goal").strip(),
            target_amount=float(payload.get("target_amount") or 0),
            current_amount=float(payload.get("current_amount") or 0),
            monthly_contribution=float(payload.get("monthly_contribution") or 0),
            notes=(payload.get("notes") or "").strip(),
        )
        db.session.add(row)
        db.session.commit()
        return jsonify({"ok": True, "item": row.public()})

    @app.delete("/api/savings/<int:item_id>")
    @login_required
    def delete_saving(user: User, item_id: int):
        row = SavingPlan.query.filter_by(id=item_id, user_id=user.id).first()
        if not row:
            return json_error("Not found.", 404)
        db.session.delete(row)
        db.session.commit()
        return jsonify({"ok": True})

    @app.post("/api/emis")
    @login_required
    def create_emi(user: User):
        payload = request.get_json(silent=True) or {}
        principal = float(payload.get("principal") or 0)
        rate = float(payload.get("annual_rate") or 0)
        tenure = int(payload.get("tenure_months") or 0)
        if principal <= 0 or tenure <= 0:
            return json_error("Principal and tenure are required.")
        row = Emi(
            user=user,
            name=(payload.get("name") or "EMI").strip(),
            principal=principal,
            annual_rate=rate,
            tenure_months=tenure,
            start_month=(payload.get("start_month") or month_key()).strip(),
            paid_installments=int(payload.get("paid_installments") or 0),
        )
        db.session.add(row)
        db.session.commit()
        data = row.public()
        data["installment"] = round(emi_amount(principal, rate, tenure), 2)
        return jsonify({"ok": True, "item": data})

    @app.delete("/api/emis/<int:item_id>")
    @login_required
    def delete_emi(user: User, item_id: int):
        row = Emi.query.filter_by(id=item_id, user_id=user.id).first()
        if not row:
            return json_error("Not found.", 404)
        db.session.delete(row)
        db.session.commit()
        return jsonify({"ok": True})

    @app.post("/api/budgets")
    @login_required
    def create_budget(user: User):
        payload = request.get_json(silent=True) or {}
        row = Budget(
            user=user,
            category=(payload.get("category") or "Other").strip(),
            monthly_limit=float(payload.get("monthly_limit") or 0),
        )
        db.session.add(row)
        db.session.commit()
        return jsonify({"ok": True, "item": row.public()})

    @app.delete("/api/budgets/<int:item_id>")
    @login_required
    def delete_budget(user: User, item_id: int):
        row = Budget.query.filter_by(id=item_id, user_id=user.id).first()
        if not row:
            return json_error("Not found.", 404)
        db.session.delete(row)
        db.session.commit()
        return jsonify({"ok": True})

    @app.post("/api/bills")
    @login_required
    def create_bill(user: User):
        payload = request.get_json(silent=True) or {}
        row = Bill(
            user=user,
            name=(payload.get("name") or "Bill").strip(),
            amount=float(payload.get("amount") or 0),
            due_day=int(payload.get("due_day") or 1),
            category=(payload.get("category") or "utility").strip(),
            auto_pay=bool(payload.get("auto_pay")),
        )
        db.session.add(row)
        db.session.commit()
        return jsonify({"ok": True, "item": row.public()})

    @app.delete("/api/bills/<int:item_id>")
    @login_required
    def delete_bill(user: User, item_id: int):
        row = Bill.query.filter_by(id=item_id, user_id=user.id).first()
        if not row:
            return json_error("Not found.", 404)
        db.session.delete(row)
        db.session.commit()
        return jsonify({"ok": True})

    @app.post("/api/memos")
    @login_required
    def create_memo(user: User):
        payload = request.get_json(silent=True) or {}
        row = Memo(
            user=user,
            title=(payload.get("title") or "Note").strip(),
            body=(payload.get("body") or "").strip(),
            tag=(payload.get("tag") or "general").strip(),
        )
        db.session.add(row)
        db.session.commit()
        return jsonify({"ok": True, "item": row.public()})

    @app.delete("/api/memos/<int:item_id>")
    @login_required
    def delete_memo(user: User, item_id: int):
        row = Memo.query.filter_by(id=item_id, user_id=user.id).first()
        if not row:
            return json_error("Not found.", 404)
        db.session.delete(row)
        db.session.commit()
        return jsonify({"ok": True})

    @app.post("/api/vault/pin")
    @login_required
    def set_pin(user: User):
        payload = request.get_json(silent=True) or {}
        pin = str(payload.get("pin") or "")
        if len(pin) < 4:
            return json_error("Use a PIN of at least 4 digits.")
        user.set_vault_pin(pin)
        db.session.commit()
        session["vault_ok"] = True
        session["vault_pin"] = pin
        return jsonify({"ok": True})

    @app.post("/api/vault/unlock")
    @login_required
    def unlock_vault(user: User):
        payload = request.get_json(silent=True) or {}
        pin = str(payload.get("pin") or "")
        if not user.vault_pin_hash:
            return json_error("Set a vault PIN first.")
        if not user.check_vault_pin(pin):
            return json_error("Incorrect PIN.", 403)
        session["vault_ok"] = True
        session["vault_pin"] = pin
        return jsonify({"ok": True})

    @app.get("/api/vault")
    @login_required
    def list_vault(user: User):
        if not session.get("vault_ok"):
            return json_error("Unlock the vault first.", 403)
        pin = session.get("vault_pin") or ""
        items = []
        for row in user.vault_items:
            secret = decrypt_secret(app.config["SECRET_KEY"], user.id, pin, row.secret_blob)
            items.append(row.public(secret))
        return jsonify({"ok": True, "items": items})

    @app.post("/api/vault")
    @login_required
    def create_vault(user: User):
        if not session.get("vault_ok"):
            return json_error("Unlock the vault first.", 403)
        payload = request.get_json(silent=True) or {}
        pin = session.get("vault_pin") or ""
        password = str(payload.get("password") or "")
        if not password:
            return json_error("Password is required.")
        row = VaultItem(
            user=user,
            label=(payload.get("label") or "Login").strip(),
            login_id=(payload.get("login_id") or "").strip(),
            secret_blob=encrypt_secret(app.config["SECRET_KEY"], user.id, pin, password),
            website=(payload.get("website") or "").strip(),
            category=(payload.get("category") or "login").strip(),
            notes=(payload.get("notes") or "").strip(),
        )
        db.session.add(row)
        db.session.commit()
        return jsonify({"ok": True, "item": row.public(password)})

    @app.delete("/api/vault/<int:item_id>")
    @login_required
    def delete_vault(user: User, item_id: int):
        if not session.get("vault_ok"):
            return json_error("Unlock the vault first.", 403)
        row = VaultItem.query.filter_by(id=item_id, user_id=user.id).first()
        if not row:
            return json_error("Not found.", 404)
        db.session.delete(row)
        db.session.commit()
        return jsonify({"ok": True})

    @app.get("/api/currency")
    @login_required
    def api_currency(_user: User):
        rates, stamp, live = fetch_usd_rates()
        return jsonify({"ok": True, "countries": COUNTRIES, "rates": rates, "as_of": stamp, "live": live})

    @app.get("/api/currency/convert")
    @login_required
    def api_convert(_user: User):
        try:
            amount = float(request.args.get("amount") or 1)
        except (TypeError, ValueError):
            return json_error("Amount must be a number.")
        try:
            result = fx_convert(amount, request.args.get("from") or "INR", request.args.get("to") or "USD")
        except ValueError as exc:
            return json_error(str(exc))
        return jsonify({"ok": True, **result})

    @app.get("/api/export.csv")
    @login_required
    def export_csv(user: User):
        month = (request.args.get("month") or month_key()).strip()
        lines = ["date,title,category,channel,direction,amount"]
        for row in user.transactions:
            if in_month(row.occurred_on, month):
                lines.append(
                    f"{row.occurred_on.isoformat()},{row.title},{row.category},{row.channel},{row.direction},{row.amount}"
                )
        body = "\n".join(lines)
        return app.response_class(body, mimetype="text/csv")

    @app.post("/api/import/csv")
    @login_required
    def import_csv(user: User):
        upload = request.files.get("file")
        if not upload or not upload.filename:
            return json_error("Choose a CSV file.")
        rows = parse_csv_bytes(upload.read())
        if not rows:
            return json_error("No usable rows. Use date, title/description, amount or debit/credit columns.")
        created = []
        for item in rows:
            row = Txn(
                user=user,
                title=item["title"],
                category=item["category"],
                channel=item["channel"],
                direction=item["direction"],
                amount=item["amount"],
                occurred_on=datetime.strptime(item["occurred_on"], "%Y-%m-%d").date(),
                merchant=item["merchant"],
                notes=item["notes"],
            )
            db.session.add(row)
            created.append(row)
        db.session.commit()
        return jsonify({"ok": True, "count": len(created), "items": [row.public() for row in created[:50]]})

    return app
