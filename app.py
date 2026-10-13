from flask import Flask, render_template, request, redirect, url_for, session, flash
from datetime import datetime, timedelta
import calendar

app = Flask(__name__)
app.secret_key = "library123"

# ===== STORAGE =====
LIBRARIAN = {"username": "admin", "password": "1234"}

BOOKS = {
    "978-0": {
        "title": "Python Crash Course",
        "author": "Eric Matthes",
        "copies": 3,
        "category": "Programming",
        "poster": "https://covers.openlibrary.org/b/isbn/9781593279288-L.jpg"
    },
    "978-1": {
        "title": "Clean Code",
        "author": "Robert C. Martin",
        "copies": 2,
        "category": "Programming",
        "poster": "https://covers.openlibrary.org/b/isbn/9780132350884-L.jpg"
    },
    "978-2": {
        "title": "The Pragmatic Programmer",
        "author": "Hunt & Thomas",
        "copies": 1,
        "category": "Programming",
        "poster": "https://covers.openlibrary.org/b/isbn/9780201616224-L.jpg"
    },
    "978-3": {
        "title": "Atomic Habits",
        "author": "James Clear",
        "copies": 4,
        "category": "Self-Help",
        "poster": "https://covers.openlibrary.org/b/isbn/9780735211292-L.jpg"
    },
    "978-4": {
        "title": "Sapiens",
        "author": "Yuval Noah Harari",
        "copies": 2,
        "category": "History",
        "poster": "https://covers.openlibrary.org/b/isbn/9780062316097-L.jpg"
    },
}

CATEGORIES = ["Programming", "Self-Help", "History", "Fiction", "Science", "Business"]

MEMBERS = {
    "M001": {"name": "Alice Reyes", "email": "alice@mail.com"},
    "M002": {"name": "Bob Santos", "email": "bob@mail.com"},
}

BORROWS = []

LOAN_DAYS = 14  # default loan period


def today_str():
    return datetime.now().strftime("%Y-%m-%d")


def compute_due(borrow_date_str, days=LOAN_DAYS):
    bd = datetime.strptime(borrow_date_str, "%Y-%m-%d")
    return (bd + timedelta(days=days)).strftime("%Y-%m-%d")


# ===== AUTH =====
@app.route("/")
def home():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username")
        p = request.form.get("password")
        if u == LIBRARIAN["username"] and p == LIBRARIAN["password"]:
            session["librarian"] = u
            return redirect(url_for("dashboard"))
        flash("Invalid credentials.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("librarian", None)
    flash("Logged out successfully.")
    return redirect(url_for("login"))


@app.route("/dashboard")
def dashboard():
    if "librarian" not in session:
        return redirect(url_for("login"))

    total_copies = sum(b["copies"] for b in BOOKS.values())
    active_borrows = sum(1 for b in BORROWS if not b["returned"])

    # Books for the popular grid
    category = request.args.get("category", "All")
    if category != "All":
        featured = [(isbn, b) for isbn, b in BOOKS.items() if b.get("category") == category and b.get("poster")]
    else:
        featured = [(isbn, b) for isbn, b in BOOKS.items() if b.get("poster")]
    featured = featured[:12]

    # ===== CALENDAR (month view) =====
    today = today_str()
    year = int(request.args.get("year", datetime.now().year))
    month = int(request.args.get("month", datetime.now().month))
    cal = calendar.Calendar(firstweekday=6)
    weeks = cal.monthdayscalendar(year, month)

    events = {}
    for i, b in enumerate(BORROWS):
        # Borrowed
        events.setdefault(b["borrow_date"], []).append({
            "type": "borrowed",
            "title": BOOKS[b["isbn"]]["title"] if b["isbn"] in BOOKS else "—",
            "member": MEMBERS[b["member_id"]]["name"] if b["member_id"] in MEMBERS else "—",
        })
        # Due (only if not returned)
        if not b["returned"] and b.get("due_date"):
            events.setdefault(b["due_date"], []).append({
                "type": "due",
                "title": BOOKS[b["isbn"]]["title"] if b["isbn"] in BOOKS else "—",
                "member": MEMBERS[b["member_id"]]["name"] if b["member_id"] in MEMBERS else "—",
            })
        # Returned
        if b.get("return_date"):
            events.setdefault(b["return_date"], []).append({
                "type": "returned",
                "title": BOOKS[b["isbn"]]["title"] if b["isbn"] in BOOKS else "—",
                "member": MEMBERS[b["member_id"]]["name"] if b["member_id"] in MEMBERS else "—",
            })

    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    month_name = calendar.month_name[month]

    # ===== UPCOMING DUE =====
    upcoming = []
    today_dt = datetime.now()
    for b in BORROWS:
        if b["returned"] or not b.get("due_date"):
            continue
        due_dt = datetime.strptime(b["due_date"], "%Y-%m-%d")
        days_left = (due_dt - today_dt).days
        upcoming.append({
            "title": BOOKS[b["isbn"]]["title"] if b["isbn"] in BOOKS else "—",
            "member": MEMBERS[b["member_id"]]["name"] if b["member_id"] in MEMBERS else "—",
            "due": b["due_date"],
            "days": max(days_left, 0),
        })
    upcoming.sort(key=lambda x: x["due"])
    upcoming = upcoming[:5]

    return render_template(
        "dashboard.html",
        librarian=session["librarian"],
        total_books=len(BOOKS),
        total_copies=total_copies,
        total_members=len(MEMBERS),
        active_borrows=active_borrows,
        recent_borrows=BORROWS[-5:][::-1],
        featured=featured,
        categories=CATEGORIES,
        current_category=category,
        books=BOOKS,
        members=MEMBERS,
        # Calendar
        year=year,
        month=month,
        month_name=month_name,
        weeks=weeks,
        events=events,
        prev_month=prev_month,
        prev_year=prev_year,
        next_month=next_month,
        next_year=next_year,
        today=today,
        # Upcoming
        upcoming=upcoming,
    )


# ===== BOOKS =====
@app.route("/books", methods=["GET", "POST"])
def books():
    if "librarian" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        action = request.form.get("action")

        if action == "add":
            isbn = request.form.get("isbn", "").strip()
            if isbn and isbn not in BOOKS:
                BOOKS[isbn] = {
                    "title": request.form.get("title", "").strip(),
                    "author": request.form.get("author", "").strip(),
                    "copies": int(request.form.get("copies", 1)),
                    "category": request.form.get("category", "Uncategorized"),
                    "poster": request.form.get("poster", "").strip(),
                }
                flash(f"✅ Book '{BOOKS[isbn]['title']}' added.")
            else:
                flash("⚠️ ISBN exists or invalid.")

        elif action == "edit":
            isbn = request.form.get("isbn")
            if isbn in BOOKS:
                BOOKS[isbn]["title"] = request.form.get("title", "").strip()
                BOOKS[isbn]["author"] = request.form.get("author", "").strip()
                BOOKS[isbn]["copies"] = int(request.form.get("copies", 1))
                BOOKS[isbn]["category"] = request.form.get("category", "Uncategorized")
                BOOKS[isbn]["poster"] = request.form.get("poster", "").strip()
                flash("✅ Book updated.")

        elif action == "delete":
            isbn = request.form.get("isbn")
            if isbn in BOOKS:
                del BOOKS[isbn]
                flash("🗑️ Book deleted.")

        return redirect(url_for("books"))

    category = request.args.get("category", "All")
    if category != "All":
        filtered = {k: v for k, v in BOOKS.items() if v.get("category") == category}
    else:
        filtered = BOOKS

    return render_template(
        "books.html",
        books=filtered,
        categories=CATEGORIES,
        current_category=category,
        librarian=session["librarian"],
    )


# ===== MEMBERS =====
@app.route("/members", methods=["GET", "POST"])
def members():
    if "librarian" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        action = request.form.get("action")

        if action == "add":
            mid = request.form.get("member_id", "").strip()
            if mid and mid not in MEMBERS:
                MEMBERS[mid] = {
                    "name": request.form.get("name", "").strip(),
                    "email": request.form.get("email", "").strip(),
                }
                flash("✅ Member added.")
            else:
                flash("⚠️ Member ID exists.")

        elif action == "edit":
            mid = request.form.get("member_id")
            if mid in MEMBERS:
                MEMBERS[mid]["name"] = request.form.get("name", "").strip()
                MEMBERS[mid]["email"] = request.form.get("email", "").strip()
                flash("✅ Member updated.")

        elif action == "delete":
            mid = request.form.get("member_id")
            if mid in MEMBERS:
                del MEMBERS[mid]
                flash("🗑️ Member deleted.")

        return redirect(url_for("members"))

    return render_template(
        "members.html",
        members=MEMBERS,
        librarian=session["librarian"],
    )


# ===== BORROW =====
@app.route("/borrow", methods=["GET", "POST"])
def borrow():
    if "librarian" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        action = request.form.get("action")

        if action == "borrow":
            isbn = request.form.get("isbn")
            mid = request.form.get("member_id")
            days = int(request.form.get("days", LOAN_DAYS))
            if isbn in BOOKS and mid in MEMBERS and BOOKS[isbn]["copies"] > 0:
                BOOKS[isbn]["copies"] -= 1
                bdate = today_str()
                BORROWS.append({
                    "isbn": isbn,
                    "member_id": mid,
                    "borrow_date": bdate,
                    "due_date": compute_due(bdate, days),
                    "return_date": None,
                    "returned": False,
                })
                flash("✅ Book issued.")
            else:
                flash("⚠️ Cannot borrow.")

        elif action == "return":
            idx = int(request.form.get("index"))
            if 0 <= idx < len(BORROWS) and not BORROWS[idx]["returned"]:
                BORROWS[idx]["returned"] = True
                BORROWS[idx]["return_date"] = today_str()
                BOOKS[BORROWS[idx]["isbn"]]["copies"] += 1
                flash("✅ Book returned.")

        return redirect(url_for("borrow"))

    return render_template(
        "borrow.html",
        books=BOOKS,
        members=MEMBERS,
        borrows=BORROWS,
        librarian=session["librarian"],
        today=today_str(),
    )


# ===== BORROWERS (per-member view) =====
@app.route("/borrowers")
def borrowers():
    if "librarian" not in session:
        return redirect(url_for("login"))

    # Group borrows by member
    grouped = {}
    for i, b in enumerate(BORROWS):
        grouped.setdefault(b["member_id"], []).append({**b, "index": i})

    return render_template(
        "borrowers.html",
        members=MEMBERS,
        grouped=grouped,
        books=BOOKS,
        librarian=session["librarian"],
        today=today_str(),
    )


# ===== CALENDAR =====
@app.route("/calendar")
def calendar_view():
    if "librarian" not in session:
        return redirect(url_for("login"))

    # Current month (or from query)
    year = int(request.args.get("year", datetime.now().year))
    month = int(request.args.get("month", datetime.now().month))

    # Build a month calendar grid
    cal = calendar.Calendar(firstweekday=6)  # Sunday start
    weeks = cal.monthdayscalendar(year, month)

    # Map due dates -> list of borrows
    events = {}
    for i, b in enumerate(BORROWS):
        if not b["returned"]:
            events.setdefault(b["due_date"], []).append({
                "type": "due",
                "title": BOOKS[b["isbn"]]["title"] if b["isbn"] in BOOKS else "—",
                "member": MEMBERS[b["member_id"]]["name"] if b["member_id"] in MEMBERS else "—",
                "index": i,
            })
        if b.get("return_date"):
            events.setdefault(b["return_date"], []).append({
                "type": "returned",
                "title": BOOKS[b["isbn"]]["title"] if b["isbn"] in BOOKS else "—",
                "member": MEMBERS[b["member_id"]]["name"] if b["member_id"] in MEMBERS else "—",
                "index": i,
            })
        events.setdefault(b["borrow_date"], []).append({
            "type": "borrowed",
            "title": BOOKS[b["isbn"]]["title"] if b["isbn"] in BOOKS else "—",
            "member": MEMBERS[b["member_id"]]["name"] if b["member_id"] in MEMBERS else "—",
            "index": i,
        })

    # Prev/next month
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    month_name = calendar.month_name[month]

    return render_template(
        "calendar.html",
        weeks=weeks,
        year=year,
        month=month,
        month_name=month_name,
        prev_month=prev_month,
        prev_year=prev_year,
        next_month=next_month,
        next_year=next_year,
        events=events,
        librarian=session["librarian"],
        today=today_str(),
    )


if __name__ == "__main__":
    app.run(debug=True)