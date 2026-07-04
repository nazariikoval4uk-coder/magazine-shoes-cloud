"""Локальний Flask-дашборд. Запуск: python dashboard/app.py (порт 5000)."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
from flask import Flask, render_template, request, redirect, url_for, session  # noqa: E402
from werkzeug.utils import secure_filename  # noqa: E402
from werkzeug.security import check_password_hash  # noqa: E402

from scripts.analysis.data_io import (  # noqa: E402
    load_orders, load_expenses, load_plan, append_expense, delete_expense,
    load_wishlist, append_wishlist, mark_wishlist_fulfilled,
    load_client_notes, set_client_note, set_refusal_reason, set_plan,
)
from scripts.analysis.shop_summary import shop_monthly_summary, overall_monthly_trend  # noqa: E402
from scripts.analysis.product_ranking import product_ranking  # noqa: E402
from scripts.analysis.client_segmentation import client_segmentation  # noqa: E402
from scripts.analysis.plan_vs_fact import plan_vs_fact, monthly_totals  # noqa: E402
from scripts.analysis.supplier_summary import supplier_summary, warehouse_by_shop  # noqa: E402
from scripts.analysis.seasonality import seasonality_summary, top_products_by_month  # noqa: E402
from scripts.analysis.cohort_analysis import cohort_analysis, MAX_OFFSET  # noqa: E402
from scripts.analysis.refusal_analysis import (  # noqa: E402
    refused_orders_with_reasons, reason_distribution, REASON_OPTIONS, REASON_COLORS,
)
from scripts.etl.import_orders import import_file, MASTER_PATH  # noqa: E402
from scripts.analysis.dashboard_summary import (  # noqa: E402
    ALL_SHOPS, SHOP_COLORS, KPI_COLORS, resolve_period, filter_orders,
    kpi_summary, shop_breakdown, monthly_chart_data, generate_insights,
)
from scripts.analysis import hosting_status  # noqa: E402

DATA_RAW = MASTER_PATH.resolve().parents[1] / "raw"

SEGMENT_COLORS = {
    "новий": "#6c63ff", "активний": "#22d3a0", "заснувший": "#fbbf24",
    "холодний": "#60a5fa", "втрачений": "#ff5c5c", "без покупок": "#7c7e9a",
}

AUTH_CONFIG_PATH = Path(__file__).resolve().parent / "instance" / "auth.json"
with open(AUTH_CONFIG_PATH, encoding="utf-8") as f:
    _auth_config = json.load(f)

app = Flask(__name__)
app.secret_key = _auth_config["secret_key"]
app.permanent_session_lifetime = timedelta(days=90)


@app.before_request
def require_login():
    if request.endpoint in ("login_view", "static"):
        return None
    if not session.get("logged_in"):
        return redirect(url_for("login_view"))
    return None


@app.route("/login", methods=["GET", "POST"])
def login_view():
    error = None
    if request.method == "POST":
        if check_password_hash(_auth_config["password_hash"], request.form.get("password", "")):
            session.permanent = True
            session["logged_in"] = True
            return redirect(url_for("index"))
        error = "Невірний пароль"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout_view():
    session.clear()
    return redirect(url_for("login_view"))


@app.context_processor
def inject_hosting_status():
    return {"hosting": hosting_status.load_status()}


@app.route("/hosting", methods=["GET", "POST"])
def hosting_view():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "renew":
            hosting_status.renew()
        elif action == "set_date":
            hosting_status.set_expiry(request.form["expires_at"])
        return redirect(url_for("hosting_view"))
    return render_template("hosting.html", status=hosting_status.load_status())

PAGE_SIZE = 100


def _current_month(orders):
    if orders.empty:
        return None
    return orders["month"].max()


@app.route("/")
def index():
    orders = load_orders()

    period = request.args.get("period", "all")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    selected_shops = request.args.getlist("shop") or ALL_SHOPS

    start, end = resolve_period(period, date_from, date_to, orders)
    filtered = filter_orders(orders, start, end, selected_shops)

    kpi = kpi_summary(filtered)
    breakdown = shop_breakdown(filtered)
    chart = monthly_chart_data(filtered, selected_shops)
    insights = generate_insights(breakdown)

    max_margin = breakdown["total_margin"].abs().max() if len(breakdown) else 0
    max_lost = breakdown["lost_margin_refused"].abs().max() if len(breakdown) else 0
    breakdown["margin_width_pct"] = (
        (breakdown["total_margin"].abs() / max_margin * 100).round(1) if max_margin else 0
    )
    breakdown["lost_width_pct"] = (
        (breakdown["lost_margin_refused"].abs() / max_lost * 100).round(1) if max_lost else 0
    )

    return render_template(
        "index.html",
        total_orders=len(orders),
        period=period,
        date_from=start.strftime("%Y-%m-%d"),
        date_to=end.strftime("%Y-%m-%d"),
        all_shops=ALL_SHOPS,
        selected_shops=selected_shops,
        shop_colors=SHOP_COLORS,
        kpi_colors=KPI_COLORS,
        kpi=kpi,
        breakdown=breakdown.to_dict("records"),
        chart=chart,
        insights=insights,
    )


@app.route("/stores")
def stores_view():
    orders = load_orders()

    period = request.args.get("period", "all")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    selected_shops = request.args.getlist("shop") or ALL_SHOPS

    start, end = resolve_period(period, date_from, date_to, orders)
    filtered = filter_orders(orders, start, end, selected_shops)
    breakdown = shop_breakdown(filtered)
    warehouse = warehouse_by_shop(filtered)
    warehouse_by_name = {row["shop"]: row for row in warehouse.to_dict("records")}

    return render_template(
        "stores.html",
        period=period,
        date_from=start.strftime("%Y-%m-%d"),
        date_to=end.strftime("%Y-%m-%d"),
        all_shops=ALL_SHOPS,
        selected_shops=selected_shops,
        shop_colors=SHOP_COLORS,
        stores=breakdown.to_dict("records"),
        warehouse=warehouse_by_name,
    )


@app.route("/trends")
def trends_view():
    orders = load_orders()
    trend = overall_monthly_trend(orders)
    latest_month = _current_month(orders)

    complete = trend
    if len(trend) > 1 and trend.iloc[0]["month"] == latest_month:
        complete = trend.iloc[1:]
    headline = complete.iloc[0].to_dict() if len(complete) else None

    return render_template(
        "trends.html",
        trend=trend.to_dict("records"),
        latest_month=latest_month,
        headline=headline,
    )


@app.route("/seasonality")
def seasonality_view():
    orders = load_orders()
    summary = seasonality_summary(orders)
    top_products = top_products_by_month(orders)

    best_month = summary.sort_values("avg_profit_per_year", ascending=False).iloc[0].to_dict()
    worst_month = summary.sort_values("avg_profit_per_year", ascending=True).iloc[0].to_dict()

    return render_template(
        "seasonality.html",
        summary=summary.to_dict("records"),
        top_products=top_products.to_dict("records"),
        best_month=best_month,
        worst_month=worst_month,
    )


@app.route("/cohorts")
def cohorts_view():
    orders = load_orders()
    cohorts = cohort_analysis(orders)
    offset_cols = [f"m{i}" for i in range(MAX_OFFSET + 1)]

    avg_m1 = cohorts["m1"].dropna().mean() if "m1" in cohorts else None
    avg_m3 = cohorts["m3"].dropna().mean() if "m3" in cohorts else None
    total_clients = int(cohorts["cohort_size"].sum()) if len(cohorts) else 0

    return render_template(
        "cohorts.html",
        cohorts=cohorts.to_dict("records"),
        offset_cols=offset_cols,
        avg_m1=avg_m1, avg_m3=avg_m3, total_clients=total_clients,
    )


@app.route("/shop/<name>")
def shop_detail(name):
    orders = load_orders()

    period = request.args.get("period", "all")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    start, end = resolve_period(period, date_from, date_to, orders)
    filtered = filter_orders(orders, start, end, [name])

    summary = shop_monthly_summary(filtered)
    shop_summary = summary[summary["shop"] == name].sort_values("month", ascending=False)

    products = product_ranking(filtered).head(15)

    return render_template(
        "shop.html",
        shop=name,
        shop_color=SHOP_COLORS.get(name, "#7c7e9a"),
        summary=shop_summary.to_dict("records"),
        products=products.to_dict("records"),
        period=period,
        date_from=start.strftime("%Y-%m-%d"),
        date_to=end.strftime("%Y-%m-%d"),
    )


@app.route("/orders")
def orders_view():
    orders = load_orders()

    shop = request.args.get("shop", "")
    outcome = request.args.get("outcome", "")
    month = request.args.get("month", "")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    q = request.args.get("q", "").strip().lower()
    page = max(int(request.args.get("page", 1)), 1)

    filtered = orders.copy()
    if shop:
        filtered = filtered[filtered["shop"] == shop]
    if outcome:
        filtered = filtered[filtered["outcome"] == outcome]
    if month:
        filtered = filtered[filtered["month"] == month]
    if date_from:
        filtered = filtered[filtered["date"] >= pd.Timestamp(date_from)]
    if date_to:
        filtered = filtered[filtered["date"] < pd.Timestamp(date_to) + pd.Timedelta(days=1)]
    if q:
        haystack = (
            filtered["last_name"].fillna("") + " " + filtered["first_name"].fillna("")
            + " " + filtered["phone"].astype(str) + " " + filtered["model"].fillna("")
            + " " + filtered["client_nickname"].fillna("")
        ).str.lower()
        filtered = filtered[haystack.str.contains(q, na=False)]

    filtered = filtered.sort_values("date", ascending=False)
    total = len(filtered)
    kpi = kpi_summary(filtered)
    start = (page - 1) * PAGE_SIZE
    page_rows = filtered.iloc[start:start + PAGE_SIZE]

    return render_template(
        "orders.html",
        orders=page_rows.to_dict("records"),
        shops=sorted(orders["shop"].dropna().unique()),
        months=sorted(orders["month"].dropna().unique(), reverse=True),
        shop=shop, outcome=outcome, month=month, q=q,
        date_from=date_from, date_to=date_to,
        page=page, total=total, page_size=PAGE_SIZE,
        has_next=start + PAGE_SIZE < total,
        kpi=kpi,
    )


def _bar_list(df, value_col, top_n, ascending=False, min_decided=0):
    d = df.copy()
    if min_decided:
        d = d[(d["orders_success"] + d["orders_refused"]) >= min_decided]
    d = d.sort_values(value_col, ascending=ascending).head(top_n)
    max_val = d[value_col].abs().max() if len(d) else 0
    d["width_pct"] = (d[value_col].abs() / max_val * 100).round(1) if max_val else 0
    return d


@app.route("/products")
def products_view():
    orders = load_orders()
    ranking = product_ranking(orders)

    top_profit = _bar_list(ranking, "total_profit", 5)
    top_buyout = _bar_list(ranking, "buyout_rate", 5, min_decided=10)
    worst_profit = _bar_list(ranking[ranking["total_profit"] < 0], "total_profit", 5, ascending=True)

    sort = request.args.get("sort", "total_profit")
    order = request.args.get("order", "desc")
    if sort not in ranking.columns:
        sort = "total_profit"
    ranking = ranking.sort_values(sort, ascending=(order == "asc"))

    return render_template(
        "products.html",
        products=ranking.to_dict("records"),
        top_profit=top_profit.to_dict("records"),
        top_buyout=top_buyout.to_dict("records"),
        worst_profit=worst_profit.to_dict("records"),
        sort=sort, order=order,
    )


@app.route("/suppliers")
def suppliers_view():
    orders = load_orders()
    summary = supplier_summary(orders)

    top_profit = _bar_list(summary, "total_profit", 5)
    worst_buyout = _bar_list(summary, "buyout_rate", 5, ascending=True, min_decided=10)

    sort = request.args.get("sort", "total_profit")
    order = request.args.get("order", "desc")
    if sort not in summary.columns:
        sort = "total_profit"
    summary = summary.sort_values(sort, ascending=(order == "asc"))

    return render_template(
        "suppliers.html",
        suppliers=summary.to_dict("records"),
        top_profit=top_profit.to_dict("records"),
        worst_buyout=worst_buyout.to_dict("records"),
        sort=sort, order=order,
    )


def _client_filters_from_request():
    return {
        "segment": request.args.get("segment", ""),
        "heat_min": request.args.get("heat_min", ""),
        "heat_max": request.args.get("heat_max", ""),
        "min_orders": request.args.get("min_orders", ""),
        "min_ltv": request.args.get("min_ltv", ""),
        "brand": request.args.get("brand", ""),
        "vip_only": request.args.get("vip_only", ""),
        "not_bought_since": request.args.get("not_bought_since", ""),
        "contact_status": request.args.get("contact_status", ""),
    }


def _apply_client_filters(clients, filters):
    if filters["segment"]:
        clients = clients[clients["segment"] == filters["segment"]]
    if filters["heat_min"]:
        clients = clients[clients["heat_score"] >= int(filters["heat_min"])]
    if filters["heat_max"]:
        clients = clients[clients["heat_score"] <= int(filters["heat_max"])]
    if filters["min_orders"]:
        clients = clients[clients["orders_success"] >= int(filters["min_orders"])]
    if filters["min_ltv"]:
        clients = clients[clients["ltv"] >= float(filters["min_ltv"])]
    if filters["brand"]:
        clients = clients[clients["favorite_brand"] == filters["brand"]]
    if filters["vip_only"]:
        clients = clients[clients["is_vip"]]
    if filters["not_bought_since"]:
        cutoff = pd.Timestamp(filters["not_bought_since"])
        clients = clients[
            clients["last_purchase"].isna() | (clients["last_purchase"] < cutoff)
        ]
    if filters["contact_status"]:
        clients = clients[clients["contact_status"] == filters["contact_status"]]
    return clients


NEXT_ACTION_OPTIONS = [
    "написати через 7 днів",
    "запропонувати новинки",
    "попросити відгук",
    "не турбувати",
    "чекає конкретну модель",
    "VIP - повідомляти першим",
]

CONTACT_STATUS_OPTIONS = ["не писали", "написали", "ігнорує", "відновили"]
CONTACT_STATUS_COLORS = {
    "не писали": "#7c7e9a", "написали": "#60a5fa",
    "ігнорує": "#ff5c5c", "відновили": "#22d3a0",
}


def _clients_with_notes(orders):
    clients = client_segmentation(orders)
    notes = load_client_notes()[["phone", "next_action", "comment", "contact_status"]]
    notes = notes.rename(columns={"comment": "note_comment"})
    clients = clients.merge(notes, on="phone", how="left")
    clients["contact_status"] = clients["contact_status"].fillna("не писали")
    return clients


@app.route("/clients")
def clients_view():
    orders = load_orders()
    all_clients = _clients_with_notes(orders)
    filters = _client_filters_from_request()
    clients = _apply_client_filters(all_clients, filters).sort_values("ltv", ascending=False)

    brands = sorted(b for b in all_clients["favorite_brand"].unique() if b != "—")

    return render_template(
        "clients.html",
        clients=clients.head(300).to_dict("records"),
        filtered_count=len(clients),
        brands=brands,
        next_action_options=NEXT_ACTION_OPTIONS,
        contact_status_options=CONTACT_STATUS_OPTIONS,
        contact_status_colors=CONTACT_STATUS_COLORS,
        segment_colors=SEGMENT_COLORS,
        **filters,
        segment_counts=all_clients["segment"].value_counts().to_dict(),
        contact_status_counts=all_clients["contact_status"].value_counts().to_dict(),
        risk_count=int(all_clients["risk"].sum()),
        vip_count=int(all_clients["is_vip"].sum()),
    )


@app.route("/clients/note", methods=["POST"])
def clients_set_note():
    set_client_note(
        phone=request.form["phone"],
        next_action=request.form["next_action"],
        comment=request.form.get("comment", ""),
        contact_status=request.form.get("contact_status", "не писали"),
    )
    return redirect(url_for("clients_view"))


@app.route("/clients/export.csv")
def clients_export():
    orders = load_orders()
    all_clients = _clients_with_notes(orders)
    filters = _client_filters_from_request()
    clients = _apply_client_filters(all_clients, filters).sort_values("ltv", ascending=False)

    export_cols = [
        "phone", "client_name", "segment", "heat_score", "is_vip",
        "orders_success", "ltv", "favorite_brand", "last_purchase", "contact_status", "next_action",
    ]
    csv_data = clients[export_cols].to_csv(index=False, encoding="utf-8-sig")
    return app.response_class(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=clients_segment.csv"},
    )


@app.route("/plan", methods=["GET", "POST"])
def plan_view():
    if request.method == "POST":
        set_plan(
            month=request.form["month"],
            shop=request.form["shop"],
            planned_profit=request.form["planned_profit"],
        )
        return redirect(url_for("plan_view", month=request.form["month"]))

    orders = load_orders()
    plan = load_plan()
    result = plan_vs_fact(orders, plan)
    totals = monthly_totals(result)

    months = sorted(result["month"].dropna().unique(), reverse=True)
    latest_month = months[0] if months else None

    month = request.args.get("month", "")
    rows = result[result["month"] == month] if month else result
    rows = rows.sort_values(["month", "shop"], ascending=[False, True])

    latest_total_rows = totals[totals["month"] == latest_month]
    latest_total = latest_total_rows.to_dict("records")[0] if len(latest_total_rows) else None

    current_month = pd.Timestamp.now().strftime("%Y-%m")

    return render_template(
        "plan.html",
        rows=rows.to_dict("records"),
        totals=totals.to_dict("records"),
        latest_total=latest_total,
        latest_month=latest_month,
        months=months,
        month=month,
        all_shops=ALL_SHOPS[:-1],
        shop_colors=SHOP_COLORS,
        current_month=current_month,
    )


@app.route("/expenses", methods=["GET", "POST"])
def expenses_view():
    if request.method == "POST":
        append_expense(
            date=request.form["date"],
            shop=request.form["shop"],
            category=request.form["category"],
            amount=request.form["amount"],
            comment=request.form.get("comment", ""),
        )
        return redirect(url_for("expenses_view"))

    expenses = load_expenses().sort_values("date", ascending=False)
    orders = load_orders()

    by_shop = expenses.groupby("shop")["amount"].sum().sort_values(ascending=False)
    max_shop_amount = by_shop.max() if len(by_shop) else 0
    by_shop_list = [
        {"shop": shop, "amount": amount, "width_pct": round(amount / max_shop_amount * 100, 1) if max_shop_amount else 0}
        for shop, amount in by_shop.items()
    ]

    return render_template(
        "expenses.html",
        expenses=expenses.to_dict("records"),
        shops=sorted(orders["shop"].dropna().unique()),
        total=expenses["amount"].sum(),
        entries_count=len(expenses),
        by_shop=by_shop_list,
        shop_colors=SHOP_COLORS,
    )


@app.route("/expenses/<int:row_id>/delete", methods=["POST"])
def expenses_delete(row_id):
    delete_expense(row_id)
    return redirect(url_for("expenses_view"))


@app.route("/wishlist", methods=["GET", "POST"])
def wishlist_view():
    if request.method == "POST":
        append_wishlist(
            date=request.form["date"],
            phone=request.form["phone"],
            client_name=request.form.get("client_name", ""),
            item=request.form["item"],
            comment=request.form.get("comment", ""),
        )
        return redirect(url_for("wishlist_view"))

    wishlist = load_wishlist().sort_values("date", ascending=False)

    q = request.args.get("q", "").strip().lower()
    if q:
        wishlist = wishlist[wishlist["item"].str.lower().str.contains(q, na=False)]

    active_only = request.args.get("active_only", "1") == "1"
    if active_only:
        wishlist = wishlist[wishlist["status"] == "очікує"]

    all_wishlist = load_wishlist()
    return render_template(
        "wishlist.html",
        items=wishlist.to_dict("records"),
        q=q,
        active_only=active_only,
        active_count=int((all_wishlist["status"] == "очікує").sum()),
        fulfilled_count=int((all_wishlist["status"] == "виконано").sum()),
        total_count=len(all_wishlist),
    )


@app.route("/wishlist/<int:row_id>/fulfill", methods=["POST"])
def wishlist_fulfill(row_id):
    mark_wishlist_fulfilled(row_id)
    return redirect(url_for("wishlist_view"))


@app.route("/refusals", methods=["GET", "POST"])
def refusals_view():
    if request.method == "POST":
        set_refusal_reason(
            order_key=request.form["order_key"],
            reason=request.form["reason"],
            comment=request.form.get("comment", ""),
        )
        return redirect(url_for("refusals_view", **{
            k: v for k, v in request.args.items()
        }))

    orders = load_orders()
    refused = refused_orders_with_reasons(orders)
    dist = reason_distribution(refused)
    max_count = dist["count"].max() if len(dist) else 0
    dist["width_pct"] = (dist["count"] / max_count * 100).round(1) if max_count else 0

    month = request.args.get("month", "")
    if month:
        refused = refused[refused["month"] == month]

    unset_only = request.args.get("unset_only", "1") == "1"
    if unset_only:
        refused = refused[refused["reason"].isna()]

    refused = refused.sort_values("date", ascending=False)
    total = len(refused)
    page = max(int(request.args.get("page", 1)), 1)
    start = (page - 1) * PAGE_SIZE
    page_rows = refused.iloc[start:start + PAGE_SIZE]

    return render_template(
        "refusals.html",
        refusals=page_rows.to_dict("records"),
        distribution=dist.to_dict("records"),
        reason_colors=REASON_COLORS,
        reason_options=REASON_OPTIONS,
        months=sorted(orders["month"].dropna().unique(), reverse=True),
        month=month,
        unset_only=unset_only,
        page=page, total=total,
        has_next=start + PAGE_SIZE < total,
    )


@app.route("/upload", methods=["GET", "POST"])
def upload_view():
    if request.method == "POST":
        uploaded = request.files.get("xls_file")
        if not uploaded or not uploaded.filename:
            return render_template("upload.html", error="Оберіть файл .xls")
        if not uploaded.filename.lower().endswith(".xls"):
            return render_template("upload.html", error="Потрібен файл .xls (як вивантаження з CRM)")

        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        safe_name = secure_filename(uploaded.filename)
        dest_name = f"{timestamp}_{safe_name}"
        DATA_RAW.mkdir(parents=True, exist_ok=True)
        dest_path = DATA_RAW / dest_name
        uploaded.save(dest_path)

        result = import_file(dest_path)
        return render_template("upload.html", result=result)

    return render_template("upload.html")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
