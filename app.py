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
    "M001": {
        "name": "Alice Reyes",
        "email": "alice@mail.com",
        "status": "active",
        "id_verified": True,
        "fines": 0.0,
    },
    "M002": {
        "name": "Bob Santos",
        "email": "bob@mail.com",
        "status": "active",
        "id_verified": True,
        "fines": 0.0,
    },
}

BORROWS = []

# ===== LIBRARY POLICY =====
LOAN_DAYS = 14
MAX_BOOKS_PER_MEMBER = 3
DEFAULT_LOAN_DAYS = 7
FINE_PER_DAY = 5.00
ALLOW_BORROW_WITH_OVERDUE = False
ALLOW_BORROW_WITH_FINES = False

LOST_BOOK_FEE = 300.00
DAMAGED_BOOK_FEE = 100.00


# ===== HELPERS =====
def today_str():
    return datetime.now().strftime("%Y-%m-%d")


def compute_due(borrow_date_str, days=LOAN_DAYS):
    bd = datetime.strptime(borrow_date_str, "%Y-%m-%d")
    return (bd + timedelta(days=days)).strftime("%Y-%m-%d")


def member_borrow_state(member_id):
    active = 0
    overdue = 0
    for b in BORROWS:
        if b["member_id"] != member_id:
            continue
        if not b["returned"]:
            active += 1
            if b.get("due_date") and b["due_date"] < today_str():
                overdue += 1
    fines = MEMBERS.get(member_id, {}).get("fines", 0.0)
    return {
        "active_borrows": active,
        "overdue_count": overdue,
        "fines": fines,
    }


def check_borrow_eligibility(member_id, isbn, quantity=1):
    errors = []
    warnings = []

    if member_id not in MEMBERS:
        return False, ["Member not found."], []

    m = MEMBERS[member_id]

    if m.get("status") != "active":
        errors.append(f"Account is {m.get('status', 'inactive')}. Cannot borrow.")

    if not m.get("id_verified"):
        errors.append("Member's ID has not been verified.")

    if isbn not in BOOKS:
        return False, ["Book not found."], []

    book = BOOKS[isbn]

    if book["copies"] < quantity:
        errors.append(
            f"Only {book['copies']} copy/copies of '{book['title']}' available "
            f"(you requested {quantity})."
        )

    state = member_borrow_state(member_id)

    if state["active_borrows"] + quantity > MAX_BOOKS_PER_MEMBER:
        errors.append(
            f"Borrowing limit is {MAX_BOOKS_PER_MEMBER}. "
            f"Member already has {state['active_borrows']} and you requested {quantity}."
        )

    if state["overdue_count"] > 0 and not ALLOW_BORROW_WITH_OVERDUE:
        errors.append(
            f"Member has {state['overdue_count']} overdue book(s). Return them first."
        )

    if state["fines"] > 0 and not ALLOW_BORROW_WITH_FINES:
        errors.append(f"Member has P{state['fines']:.2f} in unpaid fines.")

    if state["active_borrows"] + quantity == MAX_BOOKS_PER_MEMBER:
        warnings.append("Member will reach their borrowing limit after this.")

    return (len(errors) == 0), errors, warnings


def calculate_fine(due_date_str, return_date_str=None):
    due = datetime.strptime(due_date_str, "%Y-%m-%d")
    end = datetime.strptime(return_date_str, "%Y-%m-%d") if return_date_str else datetime.now()
    days_late = (end - due).days
    return max(days_late, 0) * FINE_PER_DAY, max(days_late, 0)


# ===== GLOBAL CONTEXT (notifications + counts) =====
@app.context_processor
def inject_notifications():
    if "librarian" not in session:
        return {"notifications": [], "notif_count": 0}

    notifs = []
    today = today_str()

    for b in BORROWS:
        if b["returned"] and b.get("return_date"):
            book = BOOKS.get(b["isbn"], {})
            member = MEMBERS.get(b["member_id"], {})
            notifs.append({
                "icon": "✅",
                "type": "return",
                "title": f"'{book.get('title', '—')}' returned",
                "meta": f"by {member.get('name', '—')} · {b['return_date']}",
                "date": b["return_date"],
            })

    for b in BORROWS:
        if not b["returned"]:
            book = BOOKS.get(b["isbn"], {})
            member = MEMBERS.get(b["member_id"], {})
            notifs.append({
                "icon": "📖",
                "type": "borrow",
                "title": f"'{book.get('title', '—')}' borrowed",
                "meta": f"by {member.get('name', '—')} · due {b.get('due_date', '—')}",
                "date": b["borrow_date"],
            })

    for b in BORROWS:
        if not b["returned"] and b.get("due_date") and b["due_date"] < today:
            book = BOOKS.get(b["isbn"], {})
            member = MEMBERS.get(b["member_id"], {})
            notifs.append({
                "icon": "⚠️",
                "type": "overdue",
                "title": f"'{book.get('title', '—')}' is overdue",
                "meta": f"{member.get('name', '—')} · was due {b['due_date']}",
                "date": b["due_date"],
            })

    notifs.sort(key=lambda x: x["date"], reverse=True)
    notifs = notifs[:8]

    return {"notifications": notifs, "notif_count": len(notifs)}


@app.context_processor
def inject_global_counts():
    if "librarian" not in session:
        return {}
    return {
        "total_members": len(MEMBERS),
        "active_borrows": sum(1 for b in BORROWS if not b["returned"]),
    }


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
        flash("Invalid credentials.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("librarian", None)
    flash("Logged out successfully.", "success")
    return redirect(url_for("login"))


# ===== DASHBOARD =====
@app.route("/dashboard")
def dashboard():
    if "librarian" not in session:
        return redirect(url_for("login"))

    total_copies = sum(b["copies"] for b in BOOKS.values())
    active_borrows = sum(1 for b in BORROWS if not b["returned"])

    category = request.args.get("category", "All")
    if category != "All":
        featured = [(isbn, b) for isbn, b in BOOKS.items() if b.get("category") == category and b.get("poster")]
    else:
        featured = [(isbn, b) for isbn, b in BOOKS.items() if b.get("poster")]
    featured = featured[:12]

    today = today_str()
    year = int(request.args.get("year", datetime.now().year))
    month = int(request.args.get("month", datetime.now().month))
    cal = calendar.Calendar(firstweekday=6)
    weeks = cal.monthdayscalendar(year, month)

    events = {}
    for b in BORROWS:
        events.setdefault(b["borrow_date"], []).append({
            "type": "borrowed",
            "title": BOOKS[b["isbn"]]["title"] if b["isbn"] in BOOKS else "—",
            "member": MEMBERS[b["member_id"]]["name"] if b["member_id"] in MEMBERS else "—",
        })
        if not b["returned"] and b.get("due_date"):
            events.setdefault(b["due_date"], []).append({
                "type": "due",
                "title": BOOKS[b["isbn"]]["title"] if b["isbn"] in BOOKS else "—",
                "member": MEMBERS[b["member_id"]]["name"] if b["member_id"] in MEMBERS else "—",
            })
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
                flash(f"Book '{BOOKS[isbn]['title']}' added.", "success")
            else:
                flash("ISBN exists or invalid.", "error")

        elif action == "edit":
            isbn = request.form.get("isbn")
            if isbn in BOOKS:
                BOOKS[isbn]["title"] = request.form.get("title", "").strip()
                BOOKS[isbn]["author"] = request.form.get("author", "").strip()
                BOOKS[isbn]["copies"] = int(request.form.get("copies", 1))
                BOOKS[isbn]["category"] = request.form.get("category", "Uncategorized")
                BOOKS[isbn]["poster"] = request.form.get("poster", "").strip()
                flash("Book updated.", "success")

        elif action == "delete":
            isbn = request.form.get("isbn")
            if isbn in BOOKS:
                del BOOKS[isbn]
                flash("Book deleted.", "success")

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
                    "status": request.form.get("status", "active"),
                    "id_verified": request.form.get("id_verified") == "on",
                    "fines": 0.0,
                }
                flash("Member added.", "success")
            else:
                flash("Member ID already exists.", "error")

        elif action == "edit":
            mid = request.form.get("member_id")
            if mid in MEMBERS:
                MEMBERS[mid]["name"] = request.form.get("name", "").strip()
                MEMBERS[mid]["email"] = request.form.get("email", "").strip()
                MEMBERS[mid]["status"] = request.form.get("status", "active")
                MEMBERS[mid]["id_verified"] = request.form.get("id_verified") == "on"
                flash("Member updated.", "success")

        elif action == "delete":
            mid = request.form.get("member_id")
            if mid in MEMBERS:
                del MEMBERS[mid]
                flash("Member deleted.", "success")

        return redirect(url_for("members"))

    return render_template(
        "members.html",
        members=MEMBERS,
        borrows=BORROWS,
        librarian=session["librarian"],
    )


# ===== MEMBER DETAIL =====
@app.route("/members/<member_id>")
def member_detail(member_id):
    if "librarian" not in session:
        return redirect(url_for("login"))

    if member_id not in MEMBERS:
        flash("Member not found.", "error")
        return redirect(url_for("members"))

    member = MEMBERS[member_id]

    records = []
    active = 0
    returned = 0
    overdue = 0
    today = today_str()

    for b in BORROWS:
        if b["member_id"] != member_id:
            continue

        book = BOOKS.get(b["isbn"], {})
        records.append({
            "isbn": b["isbn"],
            "title": book.get("title", "—"),
            "author": book.get("author", "—"),
            "poster": book.get("poster", ""),
            "borrow_date": b["borrow_date"],
            "due_date": b.get("due_date", "—"),
            "return_date": b.get("return_date"),
            "returned": b["returned"],
        })

        if b["returned"]:
            returned += 1
        else:
            active += 1
            if b.get("due_date") and b["due_date"] < today:
                overdue += 1

    records.sort(key=lambda x: x["borrow_date"], reverse=True)

    return render_template(
        "member_detail.html",
        librarian=session["librarian"],
        member=member,
        member_id=member_id,
        records=records,
        total_borrows=len(records),
        active_borrows=active,
        returned_count=returned,
        overdue_count=overdue,
        today=today,
    )


# ===== BORROW =====
@app.route("/borrow", methods=["GET", "POST"])
def borrow():
    if "librarian" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        action = request.form.get("action")

        # ---------- BORROW ----------
        if action == "borrow":
            isbn = request.form.get("isbn")
            mid = request.form.get("member_id")
            days_raw = request.form.get("days", str(DEFAULT_LOAN_DAYS))
            custom_due = request.form.get("custom_due_date", "").strip()

            bdate = today_str()

            # If librarian picked a custom date, use it (must be >= today)
            if days_raw == "custom" and custom_due:
                try:
                    due_dt = datetime.strptime(custom_due, "%Y-%m-%d")
                    today_dt = datetime.strptime(bdate, "%Y-%m-%d")
                    if due_dt < today_dt:
                        flash("Return date cannot be before today.", "error")
                        return redirect(url_for("borrow"))
                    days = (due_dt - today_dt).days
                    custom_due_str = custom_due
                except ValueError:
                    flash("Invalid return date.", "error")
                    return redirect(url_for("borrow"))
            else:
                try:
                    days = int(days_raw or DEFAULT_LOAN_DAYS)
                except ValueError:
                    days = DEFAULT_LOAN_DAYS
                custom_due_str = None

            try:
                quantity = int(request.form.get("quantity", 1))
            except (ValueError, TypeError):
                quantity = 1
            quantity = max(1, quantity)

            ok, errors, warnings = check_borrow_eligibility(mid, isbn, quantity)

            if not ok:
                for err in errors:
                    flash(err, "error")
                return redirect(url_for("borrow"))

            final_due = custom_due_str if custom_due_str else compute_due(bdate, days)

            for _ in range(quantity):
                BOOKS[isbn]["copies"] -= 1
                BORROWS.append({
                    "isbn": isbn,
                    "member_id": mid,
                    "borrow_date": bdate,
                    "due_date": final_due,
                    "return_date": None,
                    "returned": False,
                    "fine": 0.0,
                    "condition": "good",
                    "condition_fee": 0.0,
                })

            flash(
                f"{quantity} copy/copies of '{BOOKS[isbn]['title']}' "
                f"issued to {MEMBERS[mid]['name']} (due {final_due}).",
                "success"
            )
            for w in warnings:
                flash(w, "info")

        # ---------- RETURN ----------
        elif action == "return":
            try:
                idx = int(request.form.get("index", -1))
            except ValueError:
                idx = -1

            if 0 <= idx < len(BORROWS) and not BORROWS[idx]["returned"]:
                rec = BORROWS[idx]
                rec["returned"] = True
                rec["return_date"] = today_str()

                fine, days_late = calculate_fine(rec["due_date"], rec["return_date"])
                rec["fine"] = fine
                if fine > 0:
                    MEMBERS[rec["member_id"]]["fines"] = (
                        MEMBERS[rec["member_id"]].get("fines", 0.0) + fine
                    )
                    flash(
                        f"Book returned {days_late} day(s) late. "
                        f"P{fine:.2f} added to member's fines.",
                        "error"
                    )
                else:
                    flash("Book returned on time.", "success")

                BOOKS[rec["isbn"]]["copies"] += 1

        # ---------- SET CONDITION ----------
        elif action == "set_condition":
            try:
                idx = int(request.form.get("index", -1))
            except ValueError:
                idx = -1

            if 0 <= idx < len(BORROWS):
                condition = request.form.get("condition", "good")
                try:
                    fee = float(request.form.get("condition_fee", 0) or 0)
                except ValueError:
                    fee = 0.0

                rec = BORROWS[idx]
                rec["condition"] = condition
                rec["condition_fee"] = fee

                mid = rec["member_id"]
                if fee > 0:
                    MEMBERS[mid]["fines"] = MEMBERS[mid].get("fines", 0.0) + fee
                    label = "Lost" if condition == "lost" else "Damaged"
                    flash(
                        f"{label} book recorded. P{fee:.2f} added to "
                        f"{MEMBERS[mid]['name']}'s fines.",
                        "error"
                    )
                else:
                    flash("Book condition updated.", "success")

        # ---------- PAY FINES ----------
        elif action == "pay_fines":
            mid = request.form.get("member_id")
            if mid in MEMBERS:
                amount = MEMBERS[mid].get("fines", 0.0)
                MEMBERS[mid]["fines"] = 0.0
                flash(
                    f"P{amount:.2f} in fines cleared for {MEMBERS[mid]['name']}.",
                    "success"
                )

        return redirect(url_for("borrow"))

    indexed_borrows = [{**b, "index": i} for i, b in enumerate(BORROWS)]
    member_states = {mid: member_borrow_state(mid) for mid in MEMBERS}

    return render_template(
        "borrow.html",
        books=BOOKS,
        members=MEMBERS,
        borrows=indexed_borrows,
        member_states=member_states,
        librarian=session["librarian"],
        today=today_str(),
        max_books=MAX_BOOKS_PER_MEMBER,
        default_days=DEFAULT_LOAN_DAYS,
        fine_per_day=FINE_PER_DAY,
        lost_fee=LOST_BOOK_FEE,
        damaged_fee=DAMAGED_BOOK_FEE,
    )

# ===== BORROWERS =====
@app.route("/borrowers")
def borrowers():
    if "librarian" not in session:
        return redirect(url_for("login"))

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

    year = int(request.args.get("year", datetime.now().year))
    month = int(request.args.get("month", datetime.now().month))
    cal = calendar.Calendar(firstweekday=6)
    weeks = cal.monthdayscalendar(year, month)

    events = {}
    for b in BORROWS:
        events.setdefault(b["borrow_date"], []).append({
            "type": "borrowed",
            "title": BOOKS[b["isbn"]]["title"] if b["isbn"] in BOOKS else "—",
            "member": MEMBERS[b["member_id"]]["name"] if b["member_id"] in MEMBERS else "—",
        })
        if not b["returned"] and b.get("due_date"):
            events.setdefault(b["due_date"], []).append({
                "type": "due",
                "title": BOOKS[b["isbn"]]["title"] if b["isbn"] in BOOKS else "—",
                "member": MEMBERS[b["member_id"]]["name"] if b["member_id"] in MEMBERS else "—",
            })
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

    return render_template(
        "calendar.html",
        librarian=session["librarian"],
        year=year,
        month=month,
        month_name=calendar.month_name[month],
        weeks=weeks,
        events=events,
        prev_month=prev_month,
        prev_year=prev_year,
        next_month=next_month,
        next_year=next_year,
        today=today_str(),
    )


# ===== BOOK DETAIL =====
@app.route("/books/<isbn>")
def book_detail(isbn):
    if "librarian" not in session:
        return redirect(url_for("login"))

    if isbn not in BOOKS:
        flash("Book not found.", "error")
        return redirect(url_for("books"))

    book = BOOKS[isbn]

    active = []
    history = []
    today = today_str()

    for i, b in enumerate(BORROWS):
        if b["isbn"] != isbn:
            continue
        rec = {
            "index": i,
            "member_id": b["member_id"],
            "member_name": MEMBERS[b["member_id"]]["name"] if b["member_id"] in MEMBERS else "—",
            "borrow_date": b["borrow_date"],
            "due_date": b.get("due_date", "—"),
            "return_date": b.get("return_date"),
            "returned": b["returned"],
            "condition": b.get("condition", "good"),
            "fine": b.get("fine", 0.0),
            "overdue": (not b["returned"] and b.get("due_date") and b["due_date"] < today),
        }
        if b["returned"]:
            history.append(rec)
        else:
            active.append(rec)

    history.sort(key=lambda x: x["borrow_date"], reverse=True)

    return render_template(
        "book_detail.html",
        librarian=session["librarian"],
        isbn=isbn,
        book=book,
        active=active,
        history=history,
        total_borrows=len(active) + len(history),
        active_count=len(active),
        today=today,
    )


# ===== FETCH BOOK DESCRIPTION =====
@app.route("/api/fetch-description")
def fetch_description():
    if "librarian" not in session:
        return {"description": ""}

    import urllib.request
    import urllib.parse
    import json

    title = request.args.get("title", "").strip()
    author = request.args.get("author", "").strip()
    isbn = request.args.get("isbn", "").strip().replace("-", "").replace(" ", "")

    if not title and not isbn:
        return {"description": ""}

    if isbn:
        url = f"https://openlibrary.org/isbn/{isbn}.json"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SmartLibrary/1.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            desc = data.get("description")
            if isinstance(desc, dict):
                desc = desc.get("value", "")
            if desc:
                return {"description": desc, "source": "isbn"}
        except Exception:
            pass

    if title:
        params = {"title": title, "limit": 5}
        if author:
            params["author"] = author
        search_url = "https://openlibrary.org/search.json?" + urllib.parse.urlencode(params)

        try:
            req = urllib.request.Request(search_url, headers={"User-Agent": "SmartLibrary/1.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return {"description": ""}

        for doc in data.get("docs", []):
            key = doc.get("key")
            if not key:
                continue
            work_url = f"https://openlibrary.org{key}.json"
            try:
                req = urllib.request.Request(work_url, headers={"User-Agent": "SmartLibrary/1.0"})
                with urllib.request.urlopen(req, timeout=6) as resp:
                    work = json.loads(resp.read().decode("utf-8"))
                desc = work.get("description")
                if isinstance(desc, dict):
                    desc = desc.get("value", "")
                if desc:
                    return {"description": desc, "source": "search"}
            except Exception:
                continue

    return {"description": ""}


# ===== FETCH BOOK POSTER =====
@app.route("/api/fetch-poster")
def fetch_poster():
    if "librarian" not in session:
        return {"poster": ""}

    import urllib.request
    import urllib.parse
    import json

    title = request.args.get("title", "").strip()
    author = request.args.get("author", "").strip()
    isbn = request.args.get("isbn", "").strip().replace("-", "").replace(" ", "")

    if isbn:
        cover_url = f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"
        try:
            req = urllib.request.Request(cover_url, headers={"User-Agent": "SmartLibrary/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = resp.read()
                if len(body) > 5000:
                    return {"poster": cover_url, "source": "isbn"}
        except Exception:
            pass

    if not title:
        return {"poster": ""}

    params = {"title": title, "limit": 10}
    if author:
        params["author"] = author

    url = "https://openlibrary.org/search.json?" + urllib.parse.urlencode(params)

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SmartLibrary/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {"poster": ""}

    for doc in data.get("docs", []):
        cover_id = doc.get("cover_i")
        if cover_id:
            poster = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
            return {
                "poster": poster,
                "title": doc.get("title", ""),
                "author": ", ".join(doc.get("author_name", [])[:2]),
                "source": "search",
            }

    return {"poster": ""}


if __name__ == "__main__":
    app.run(debug=True)