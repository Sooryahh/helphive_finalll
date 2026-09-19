import os
import re
import sqlite3
from difflib import SequenceMatcher
from functools import wraps
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["DATABASE"] = os.path.join(os.path.dirname(__file__), "helphive.db")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    db = get_db()
    with open(
        os.path.join(os.path.dirname(__file__), "database", "schema.sql"),
        "r",
        encoding="utf-8",
    ) as f:
        db.executescript(f.read())
    db.commit()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def role_required(role):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in first.", "warning")
                return redirect(url_for("login"))
            if session.get("role") != role:
                flash("You do not have permission for this page.", "danger")
                return redirect(url_for("index"))
            return view(*args, **kwargs)

        return wrapped

    return decorator


@app.context_processor
def inject_user():
    return {"current_user": session}


def normalize_text(value):
    """Normalize text so small spelling/spacing/punctuation changes compare well."""
    value = (value or "").lower().strip()
    return re.sub(r"[^a-z0-9]+", "", value)


def similarity(left, right):
    return SequenceMatcher(
        None, normalize_text(left), normalize_text(right), autojunk=False
    ).ratio()


def find_duplicate_opportunities(
    title, event_date, location, category, exclude_id=None, limit=3
):
    """
    Find likely duplicate opportunities.

    The score combines:
    - title similarity: 55%
    - location similarity: 20%
    - same date: 15%
    - same category: 10%

    A warning is returned when the score is high enough, or when the
    event date/location match and the titles are reasonably similar.
    """
    db = get_db()
    query = """
        SELECT o.*, u.name AS organizer_name
        FROM opportunities o
        JOIN users u ON u.id=o.organizer_id
        WHERE o.event_date >= date('now')
    """
    params = []

    if exclude_id is not None:
        query += " AND o.id != ?"
        params.append(exclude_id)

    query += " ORDER BY o.event_date ASC"
    rows = db.execute(query, params).fetchall()

    matches = []

    for row in rows:
        title_score = similarity(title, row["title"])
        location_score = similarity(location, row["location"])
        same_date = event_date == row["event_date"]
        same_category = category == row["category"]

        score = (
            title_score * 0.55
            + location_score * 0.20
            + (0.15 if same_date else 0)
            + (0.10 if same_category else 0)
        )

        strong_match = (
            same_date
            and location_score >= 0.75
            and title_score >= 0.55
        )
        likely_match = score >= 0.72

        if strong_match or likely_match:
            matches.append(
                {
                    "id": row["id"],
                    "title": row["title"],
                    "description": row["description"],
                    "category": row["category"],
                    "location": row["location"],
                    "event_date": row["event_date"],
                    "capacity": row["capacity"],
                    "organizer_name": row["organizer_name"],
                    "similarity": round(score * 100),
                }
            )

    matches.sort(key=lambda item: item["similarity"], reverse=True)
    return matches[:limit]


@app.route("/")
def index():
    db = get_db()
    opportunities = db.execute(
        """
        SELECT o.*, u.name AS organizer_name,
        (SELECT COUNT(*) FROM registrations r
         WHERE r.opportunity_id=o.id AND r.status='approved') AS volunteer_count
        FROM opportunities o
        JOIN users u ON u.id=o.organizer_id
        WHERE o.event_date >= date('now')
        ORDER BY o.event_date ASC
        LIMIT 6
        """
    ).fetchall()
    return render_template("index.html", opportunities=opportunities)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "student")

        if not name or not email or not password:
            flash("All fields are required.", "danger")
            return render_template("register.html")
        if len(password) < 6:
            flash("Password must contain at least 6 characters.", "danger")
            return render_template("register.html")
        if role not in ("student", "organizer"):
            role = "student"

        db = get_db()
        try:
            db.execute(
                "INSERT INTO users (name,email,password,role) VALUES (?,?,?,?)",
                (name, email, generate_password_hash(password), role),
            )
            db.commit()
            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("That email is already registered.", "danger")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT * FROM users WHERE email=?", (email,)
        ).fetchone()

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]
            flash("Welcome to HelpHive!", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    if session["role"] == "organizer":
        return redirect(url_for("organizer_dashboard"))

    db = get_db()
    registrations = db.execute(
        """
        SELECT r.*, o.title, o.location, o.event_date, o.category,
               f.id AS feedback_id, f.rating AS feedback_rating
        FROM registrations r
        JOIN opportunities o ON o.id=r.opportunity_id
        LEFT JOIN feedback f
          ON f.user_id=r.user_id AND f.opportunity_id=r.opportunity_id
        WHERE r.user_id=? ORDER BY o.event_date DESC
        """,
        (session["user_id"],),
    ).fetchall()

    experience = db.execute(
        """
        SELECT
            COUNT(*) AS attended_events,
            COUNT(DISTINCT o.category) AS categories_count,
            GROUP_CONCAT(DISTINCT o.category) AS categories
        FROM registrations r
        JOIN opportunities o ON o.id=r.opportunity_id
        WHERE r.user_id=? AND r.attendance=1
        """,
        (session["user_id"],),
    ).fetchone()

    attended = experience["attended_events"] or 0
    if attended == 0:
        experience_level = "New volunteer"
    elif attended <= 2:
        experience_level = "Getting started"
    elif attended <= 5:
        experience_level = "Active volunteer"
    else:
        experience_level = "Experienced volunteer"

    return render_template(
        "student_dashboard.html",
        registrations=registrations,
        experience=experience,
        experience_level=experience_level,
    )


@app.route("/opportunity/<int:opportunity_id>/feedback", methods=["GET", "POST"])
@login_required
@role_required("student")
def feedback(opportunity_id):
    db = get_db()
    opportunity = db.execute(
        "SELECT * FROM opportunities WHERE id=?", (opportunity_id,)
    ).fetchone()

    if not opportunity:
        flash("Opportunity not found.", "danger")
        return redirect(url_for("dashboard"))

    registration = db.execute(
        """
        SELECT * FROM registrations
        WHERE user_id=? AND opportunity_id=? AND attendance=1
        """,
        (session["user_id"], opportunity_id),
    ).fetchone()

    if not registration:
        flash("Feedback is available after your attendance is marked.", "warning")
        return redirect(url_for("dashboard"))

    existing = db.execute(
        "SELECT * FROM feedback WHERE user_id=? AND opportunity_id=?",
        (session["user_id"], opportunity_id),
    ).fetchone()

    if request.method == "POST":
        rating = request.form.get("rating", "").strip()
        comment = request.form.get("comment", "").strip()

        try:
            rating = int(rating)
            if rating < 1 or rating > 5:
                raise ValueError
        except ValueError:
            flash("Please select a rating from 1 to 5.", "danger")
            return render_template(
                "feedback.html", opportunity=opportunity, existing=existing
            )

        if not comment:
            flash("Please share a short comment about your experience.", "danger")
            return render_template(
                "feedback.html", opportunity=opportunity, existing=existing
            )

        if existing:
            db.execute(
                "UPDATE feedback SET rating=?, comment=?, created_at=CURRENT_TIMESTAMP WHERE id=?",
                (rating, comment, existing["id"]),
            )
            flash("Your feedback was updated. Thank you!", "success")
        else:
            db.execute(
                "INSERT INTO feedback(user_id, opportunity_id, rating, comment) VALUES(?,?,?,?)",
                (session["user_id"], opportunity_id, rating, comment),
            )
            flash("Thanks for sharing your volunteer experience!", "success")
        db.commit()
        return redirect(url_for("dashboard"))

    return render_template(
        "feedback.html", opportunity=opportunity, existing=existing
    )


@app.route("/opportunities")
def opportunities():
    category = request.args.get("category", "").strip()
    search = request.args.get("search", "").strip()

    query = """
        SELECT o.*, u.name AS organizer_name,
        (SELECT COUNT(*) FROM registrations r
         WHERE r.opportunity_id=o.id AND r.status='approved') AS volunteer_count
        FROM opportunities o JOIN users u ON u.id=o.organizer_id
        WHERE 1=1
    """
    params = []

    if category:
        query += " AND o.category=?"
        params.append(category)

    if search:
        query += " AND (o.title LIKE ? OR o.description LIKE ? OR o.location LIKE ?)"
        term = f"%{search}%"
        params += [term, term, term]

    query += " ORDER BY o.event_date ASC"

    rows = get_db().execute(query, params).fetchall()
    return render_template(
        "opportunities.html",
        opportunities=rows,
        search=search,
        category=category,
    )


@app.route("/opportunity/<int:opportunity_id>")
def opportunity_detail(opportunity_id):
    db = get_db()
    opportunity = db.execute(
        """
        SELECT o.*, u.name AS organizer_name,
        (SELECT COUNT(*) FROM registrations r
         WHERE r.opportunity_id=o.id AND r.status='approved') AS volunteer_count
        FROM opportunities o JOIN users u ON u.id=o.organizer_id
        WHERE o.id=?
        """,
        (opportunity_id,),
    ).fetchone()

    if not opportunity:
        flash("Opportunity not found.", "danger")
        return redirect(url_for("opportunities"))

    already = False

    if "user_id" in session:
        already = (
            db.execute(
                "SELECT 1 FROM registrations WHERE user_id=? AND opportunity_id=?",
                (session["user_id"], opportunity_id),
            ).fetchone()
            is not None
        )

    return render_template(
        "opportunity_detail.html",
        opportunity=opportunity,
        already=already,
    )


@app.route("/opportunity/<int:opportunity_id>/register", methods=["POST"])
@login_required
@role_required("student")
def register_opportunity(opportunity_id):
    db = get_db()

    opportunity = db.execute(
        "SELECT * FROM opportunities WHERE id=?", (opportunity_id,)
    ).fetchone()

    if not opportunity:
        flash("Opportunity not found.", "danger")
        return redirect(url_for("opportunities"))

    # Explicit duplicate-registration guard.
    existing = db.execute(
        "SELECT status FROM registrations WHERE user_id=? AND opportunity_id=?",
        (session["user_id"], opportunity_id),
    ).fetchone()

    if existing:
        flash(
            f"You have already applied. Current status: {existing['status']}.",
            "warning",
        )
        return redirect(
            url_for("opportunity_detail", opportunity_id=opportunity_id)
        )

    count = db.execute(
        """
        SELECT COUNT(*) AS c FROM registrations
        WHERE opportunity_id=? AND status='approved'
        """,
        (opportunity_id,),
    ).fetchone()["c"]

    if count >= opportunity["capacity"]:
        flash("This opportunity is full.", "warning")
        return redirect(
            url_for("opportunity_detail", opportunity_id=opportunity_id)
        )

    try:
        db.execute(
            "INSERT INTO registrations(user_id,opportunity_id) VALUES(?,?)",
            (session["user_id"], opportunity_id),
        )
        db.commit()
        flash(
            "Registration submitted. Wait for organizer approval.",
            "success",
        )
    except sqlite3.IntegrityError:
        flash(
            "Duplicate application blocked. You are already registered.",
            "warning",
        )

    return redirect(
        url_for("opportunity_detail", opportunity_id=opportunity_id)
    )


@app.route("/organizer")
@login_required
@role_required("organizer")
def organizer_dashboard():
    db = get_db()
    own = db.execute(
        """
        SELECT o.*,
        (SELECT COUNT(*) FROM registrations r
         WHERE r.opportunity_id=o.id) AS registration_count,
        (SELECT ROUND(AVG(f.rating), 1) FROM feedback f
         WHERE f.opportunity_id=o.id) AS average_rating,
        (SELECT COUNT(*) FROM feedback f
         WHERE f.opportunity_id=o.id) AS feedback_count
        FROM opportunities o
        WHERE o.organizer_id=?
        ORDER BY o.event_date
        """,
        (session["user_id"],),
    ).fetchall()

    return render_template("organizer_dashboard.html", opportunities=own)


@app.route("/organizer/opportunity/create", methods=["GET", "POST"])
@login_required
@role_required("organizer")
def create_opportunity():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "").strip()
        location = request.form.get("location", "").strip()
        event_date = request.form.get("event_date", "").strip()
        capacity = request.form.get("capacity", "").strip()
        force_create = request.form.get("force_create") == "1"

        form_data = {
            "title": title,
            "description": description,
            "category": category,
            "location": location,
            "event_date": event_date,
            "capacity": capacity,
        }

        if not all(
            [title, description, category, location, event_date, capacity]
        ):
            flash("All fields are required.", "danger")
            return render_template(
                "opportunity_form.html",
                opportunity=None,
                form_data=form_data,
                duplicates=[],
            )

        try:
            capacity = int(capacity)
            if capacity < 1:
                raise ValueError
            datetime.strptime(event_date, "%Y-%m-%d")
        except ValueError:
            flash("Enter a valid date and positive capacity.", "danger")
            return render_template(
                "opportunity_form.html",
                opportunity=None,
                form_data=form_data,
                duplicates=[],
            )

        duplicates = find_duplicate_opportunities(
            title, event_date, location, category
        )

        if duplicates and not force_create:
            return render_template(
                "opportunity_form.html",
                opportunity=None,
                form_data=form_data,
                duplicates=duplicates,
            )

        db = get_db()
        db.execute(
            """
            INSERT INTO opportunities
            (title,description,category,location,event_date,capacity,organizer_id)
            VALUES(?,?,?,?,?,?,?)
            """,
            (
                title,
                description,
                category,
                location,
                event_date,
                capacity,
                session["user_id"],
            ),
        )
        db.commit()

        if duplicates:
            flash(
                "Opportunity created after you confirmed it was not a duplicate.",
                "info",
            )
        else:
            flash("Opportunity created.", "success")

        return redirect(url_for("organizer_dashboard"))

    return render_template(
        "opportunity_form.html",
        opportunity=None,
        form_data={},
        duplicates=[],
    )


@app.route(
    "/organizer/opportunity/<int:opportunity_id>/edit",
    methods=["GET", "POST"],
)
@login_required
@role_required("organizer")
def edit_opportunity(opportunity_id):
    db = get_db()

    opportunity = db.execute(
        "SELECT * FROM opportunities WHERE id=? AND organizer_id=?",
        (opportunity_id, session["user_id"]),
    ).fetchone()

    if not opportunity:
        flash("Opportunity not found or not owned by you.", "danger")
        return redirect(url_for("organizer_dashboard"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "").strip()
        location = request.form.get("location", "").strip()
        event_date = request.form.get("event_date", "").strip()
        capacity = request.form.get("capacity", "").strip()
        force_create = request.form.get("force_create") == "1"

        form_data = {
            "title": title,
            "description": description,
            "category": category,
            "location": location,
            "event_date": event_date,
            "capacity": capacity,
        }

        try:
            capacity = int(capacity)
            datetime.strptime(event_date, "%Y-%m-%d")
            if capacity < 1 or not all(
                [title, description, category, location]
            ):
                raise ValueError
        except ValueError:
            flash("Please enter valid values.", "danger")
            return render_template(
                "opportunity_form.html",
                opportunity=opportunity,
                form_data=form_data,
                duplicates=[],
            )

        duplicates = find_duplicate_opportunities(
            title,
            event_date,
            location,
            category,
            exclude_id=opportunity_id,
        )

        if duplicates and not force_create:
            return render_template(
                "opportunity_form.html",
                opportunity=opportunity,
                form_data=form_data,
                duplicates=duplicates,
            )

        db.execute(
            """
            UPDATE opportunities
            SET title=?,description=?,category=?,location=?,event_date=?,capacity=?
            WHERE id=? AND organizer_id=?
            """,
            (
                title,
                description,
                category,
                location,
                event_date,
                capacity,
                opportunity_id,
                session["user_id"],
            ),
        )
        db.commit()

        if duplicates:
            flash(
                "Opportunity updated after duplicate warning was acknowledged.",
                "info",
            )
        else:
            flash("Opportunity updated.", "success")

        return redirect(url_for("organizer_dashboard"))

    return render_template(
        "opportunity_form.html",
        opportunity=opportunity,
        form_data={},
        duplicates=[],
    )


@app.route(
    "/organizer/opportunity/<int:opportunity_id>/delete",
    methods=["POST"],
)
@login_required
@role_required("organizer")
def delete_opportunity(opportunity_id):
    db = get_db()
    db.execute(
        "DELETE FROM opportunities WHERE id=? AND organizer_id=?",
        (opportunity_id, session["user_id"]),
    )
    db.commit()
    flash("Opportunity deleted.", "info")
    return redirect(url_for("organizer_dashboard"))


@app.route("/organizer/opportunity/<int:opportunity_id>/registrations")
@login_required
@role_required("organizer")
def registrations(opportunity_id):
    db = get_db()

    opportunity = db.execute(
        "SELECT * FROM opportunities WHERE id=? AND organizer_id=?",
        (opportunity_id, session["user_id"]),
    ).fetchone()

    if not opportunity:
        flash("Opportunity not found.", "danger")
        return redirect(url_for("organizer_dashboard"))

    rows = db.execute(
        """
        SELECT r.*,u.name,u.email, f.rating AS feedback_rating, f.comment AS feedback_comment
        FROM registrations r
        JOIN users u ON u.id=r.user_id
        LEFT JOIN feedback f ON f.user_id=r.user_id AND f.opportunity_id=r.opportunity_id
        WHERE r.opportunity_id=?
        ORDER BY r.created_at
        """,
        (opportunity_id,),
    ).fetchall()

    return render_template(
        "registrations.html",
        opportunity=opportunity,
        registrations=rows,
    )


@app.route(
    "/organizer/registration/<int:registration_id>/<action>",
    methods=["POST"],
)
@login_required
@role_required("organizer")
def update_registration(registration_id, action):
    if action not in ("approved", "rejected", "attended"):
        flash("Invalid action.", "danger")
        return redirect(url_for("organizer_dashboard"))

    db = get_db()

    row = db.execute(
        """
        SELECT r.id
        FROM registrations r
        JOIN opportunities o ON o.id=r.opportunity_id
        WHERE r.id=? AND o.organizer_id=?
        """,
        (registration_id, session["user_id"]),
    ).fetchone()

    if not row:
        flash("Registration not found.", "danger")
        return redirect(url_for("organizer_dashboard"))

    if action == "attended":
        db.execute(
            "UPDATE registrations SET attendance=1,status='approved' WHERE id=?",
            (registration_id,),
        )
    else:
        db.execute(
            "UPDATE registrations SET status=? WHERE id=?",
            (action, registration_id),
        )

    db.commit()
    flash("Registration updated.", "success")
    return redirect(request.referrer or url_for("organizer_dashboard"))


@app.route("/organizer/opportunity/<int:opportunity_id>/feedback")
@login_required
@role_required("organizer")
def opportunity_feedback(opportunity_id):
    db = get_db()
    opportunity = db.execute(
        "SELECT * FROM opportunities WHERE id=? AND organizer_id=?",
        (opportunity_id, session["user_id"]),
    ).fetchone()

    if not opportunity:
        flash("Opportunity not found.", "danger")
        return redirect(url_for("organizer_dashboard"))

    feedback_rows = db.execute(
        """
        SELECT f.*, u.name, u.email
        FROM feedback f
        JOIN users u ON u.id=f.user_id
        WHERE f.opportunity_id=?
        ORDER BY f.created_at DESC
        """,
        (opportunity_id,),
    ).fetchall()

    average = db.execute(
        "SELECT ROUND(AVG(rating), 1) AS average_rating, COUNT(*) AS feedback_count FROM feedback WHERE opportunity_id=?",
        (opportunity_id,),
    ).fetchone()

    return render_template(
        "feedback_list.html",
        opportunity=opportunity,
        feedback_rows=feedback_rows,
        average=average,
    )


@app.cli.command("init-db")
def init_db_command():
    init_db()
    print("Database initialized.")


with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
