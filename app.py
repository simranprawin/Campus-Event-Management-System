import os
import sqlite3
from functools import wraps
from datetime import datetime
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    g,
    abort,
)
from werkzeug.security import generate_password_hash, check_password_hash


app = Flask(__name__)
app.config["SECRET_KEY"] = "change-this-secret-key"

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "campus_events.db")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)

    if db is not None:
        db.close()


def init_db():
    db = get_db()

    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            department TEXT,
            year TEXT,
            role TEXT NOT NULL DEFAULT 'student',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            venue TEXT NOT NULL,
            capacity INTEGER NOT NULL,
            organizer TEXT NOT NULL,
            description TEXT NOT NULL,
            created_by INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (created_by) REFERENCES users(id)
                ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS registrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            event_id INTEGER NOT NULL,
            registered_at TEXT NOT NULL,
            UNIQUE(user_id, event_id),
            FOREIGN KEY (user_id) REFERENCES users(id)
                ON DELETE CASCADE,
            FOREIGN KEY (event_id) REFERENCES events(id)
                ON DELETE CASCADE
        );
        """
    )

    admin = db.execute(
        "SELECT id FROM users WHERE email = ?",
        ("admin@example.com",),
    ).fetchone()

    if admin is None:
        db.execute(
            """
            INSERT INTO users
            (name, email, password, department, year, role, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "System Administrator",
                "admin@example.com",
                generate_password_hash("admin123"),
                "Administration",
                "Staff",
                "admin",
                datetime.now().isoformat(),
            ),
        )

    event_count = db.execute(
        "SELECT COUNT(*) AS count FROM events"
    ).fetchone()["count"]

    if event_count == 0:
        admin_id = db.execute(
            "SELECT id FROM users WHERE email = ?",
            ("admin@example.com",),
        ).fetchone()["id"]

        sample_events = [
            (
                "AI and Machine Learning Workshop",
                "Workshop",
                "2026-10-15",
                "10:00",
                "Computer Lab 302",
                100,
                "CSE Department",
                "Learn the fundamentals of artificial intelligence and machine learning through practical examples.",
                admin_id,
                datetime.now().isoformat(),
            ),
            (
                "Hackathon 2026",
                "Hackathon",
                "2026-10-20",
                "09:00",
                "Innovation Lab",
                150,
                "Coding Club",
                "Build an innovative software project with a team and compete with students from different departments.",
                admin_id,
                datetime.now().isoformat(),
            ),
            (
                "Annual Cultural Fest",
                "Cultural",
                "2026-10-25",
                "16:00",
                "College Main Ground",
                500,
                "Student Council",
                "Enjoy music, dance, art, drama, and cultural performances presented by talented students.",
                admin_id,
                datetime.now().isoformat(),
            ),
        ]

        db.executemany(
            """
            INSERT INTO events
            (
                name, category, date, time, venue, capacity,
                organizer, description, created_by, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            sample_events,
        )

    db.commit()


@app.before_request
def load_logged_in_user():
    user_id = session.get("user_id")

    if user_id is None:
        g.user = None
    else:
        g.user = get_db().execute(
            "SELECT * FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()


@app.context_processor
def inject_current_year():
    return {"current_year": datetime.now().year}


def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))

        return view(**kwargs)

    return wrapped_view


def admin_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))

        if g.user["role"] != "admin":
            flash("Administrator access is required.", "error")
            return redirect(url_for("index"))

        return view(**kwargs)

    return wrapped_view


def get_event_with_registration_count(event_id):
    event = get_db().execute(
        """
        SELECT
            e.*,
            COUNT(r.id) AS registration_count
        FROM events e
        LEFT JOIN registrations r ON e.id = r.event_id
        WHERE e.id = ?
        GROUP BY e.id
        """,
        (event_id,),
    ).fetchone()

    if event is None:
        abort(404)

    return event


def get_all_events(search="", category=""):
    query = """
        SELECT
            e.*,
            COUNT(r.id) AS registration_count
        FROM events e
        LEFT JOIN registrations r ON e.id = r.event_id
        WHERE 1 = 1
    """

    parameters = []

    if search:
        query += """
            AND (
                LOWER(e.name) LIKE ?
                OR LOWER(e.category) LIKE ?
                OR LOWER(e.venue) LIKE ?
                OR LOWER(e.organizer) LIKE ?
            )
        """

        search_value = f"%{search.lower()}%"
        parameters.extend(
            [
                search_value,
                search_value,
                search_value,
                search_value,
            ]
        )

    if category:
        query += " AND e.category = ?"
        parameters.append(category)

    query += """
        GROUP BY e.id
        ORDER BY e.date ASC, e.time ASC
    """

    return get_db().execute(query, parameters).fetchall()


@app.route("/")
def index():
    search = request.args.get("search", "").strip()
    category = request.args.get("category", "").strip()

    events = get_all_events(search, category)

    categories = get_db().execute(
        "SELECT DISTINCT category FROM events ORDER BY category"
    ).fetchall()

    return render_template(
        "index.html",
        events=events,
        categories=categories,
        search=search,
        selected_category=category,
    )


@app.route("/register", methods=("GET", "POST"))
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        department = request.form.get("department", "").strip()
        year = request.form.get("year", "")

        error = None

        if not name:
            error = "Name is required."
        elif not email:
            error = "Email is required."
        elif not password or len(password) < 6:
            error = "Password must contain at least 6 characters."
        elif not department:
            error = "Department is required."
        elif not year:
            error = "Please select your year."

        if error is None:
            db = get_db()

            existing_user = db.execute(
                "SELECT id FROM users WHERE email = ?",
                (email,),
            ).fetchone()

            if existing_user is not None:
                error = "An account with this email already exists."
            else:
                db.execute(
                    """
                    INSERT INTO users
                    (name, email, password, department, year, role, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        name,
                        email,
                        generate_password_hash(password),
                        department,
                        year,
                        "student",
                        datetime.now().isoformat(),
                    ),
                )

                db.commit()

                flash("Account created successfully. Please log in.", "success")
                return redirect(url_for("login"))

        if error:
            flash(error, "error")

    return render_template("register.html")


@app.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = get_db().execute(
            "SELECT * FROM users WHERE email = ?",
            (email,),
        ).fetchone()

        if user is None or not check_password_hash(
            user["password"],
            password,
        ):
            flash("Invalid email or password.", "error")
        else:
            session.clear()
            session["user_id"] = user["id"]

            flash("Logged in successfully.", "success")

            if user["role"] == "admin":
                return redirect(url_for("admin_dashboard"))

            return redirect(url_for("student_dashboard"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    db = get_db()

    events = db.execute(
        """
        SELECT
            e.*,
            COUNT(r.id) AS registration_count
        FROM events e
        LEFT JOIN registrations r ON e.id = r.event_id
        GROUP BY e.id
        ORDER BY e.date ASC, e.time ASC
        """
    ).fetchall()

    registrations = db.execute(
        """
        SELECT
            r.id,
            r.registered_at,
            u.name AS student_name,
            u.email AS student_email,
            u.department,
            u.year,
            e.name AS event_name,
            e.date AS event_date
        FROM registrations r
        JOIN users u ON r.user_id = u.id
        JOIN events e ON r.event_id = e.id
        ORDER BY r.registered_at DESC
        """
    ).fetchall()

    stats = {
        "events": db.execute(
            "SELECT COUNT(*) AS count FROM events"
        ).fetchone()["count"],
        "students": db.execute(
            "SELECT COUNT(*) AS count FROM users WHERE role = 'student'"
        ).fetchone()["count"],
        "registrations": db.execute(
            "SELECT COUNT(*) AS count FROM registrations"
        ).fetchone()["count"],
    }

    return render_template(
        "admin_dashboard.html",
        events=events,
        registrations=registrations,
        stats=stats,
    )


@app.route("/admin/event/add", methods=("GET", "POST"))
@admin_required
def add_event():
    if request.method == "POST":
        form_data = get_event_form_data()
        error = validate_event_data(form_data)

        if error:
            flash(error, "error")
        else:
            db = get_db()

            db.execute(
                """
                INSERT INTO events
                (
                    name, category, date, time, venue, capacity,
                    organizer, description, created_by, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    form_data["name"],
                    form_data["category"],
                    form_data["date"],
                    form_data["time"],
                    form_data["venue"],
                    form_data["capacity"],
                    form_data["organizer"],
                    form_data["description"],
                    g.user["id"],
                    datetime.now().isoformat(),
                ),
            )

            db.commit()

            flash("Event created successfully.", "success")
            return redirect(url_for("admin_dashboard"))

        return render_template(
            "event_form.html",
            event=form_data,
            page_title="Add Event",
        )

    return render_template(
        "event_form.html",
        event=None,
        page_title="Add Event",
    )


@app.route("/admin/event/<int:event_id>/edit", methods=("GET", "POST"))
@admin_required
def edit_event(event_id):
    event = get_event_with_registration_count(event_id)

    if request.method == "POST":
        form_data = get_event_form_data()
        error = validate_event_data(form_data)

        if error:
            flash(error, "error")
            return render_template(
                "event_form.html",
                event=form_data,
                page_title="Edit Event",
            )

        if form_data["capacity"] < event["registration_count"]:
            flash(
                "Capacity cannot be lower than existing registrations.",
                "error",
            )
            return render_template(
                "event_form.html",
                event=form_data,
                page_title="Edit Event",
            )

        db = get_db()

        db.execute(
            """
            UPDATE events
            SET
                name = ?,
                category = ?,
                date = ?,
                time = ?,
                venue = ?,
                capacity = ?,
                organizer = ?,
                description = ?
            WHERE id = ?
            """,
            (
                form_data["name"],
                form_data["category"],
                form_data["date"],
                form_data["time"],
                form_data["venue"],
                form_data["capacity"],
                form_data["organizer"],
                form_data["description"],
                event_id,
            ),
        )

        db.commit()

        flash("Event updated successfully.", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template(
        "event_form.html",
        event=event,
        page_title="Edit Event",
    )


@app.post("/admin/event/<int:event_id>/delete")
@admin_required
def delete_event(event_id):
    event = get_event_with_registration_count(event_id)

    get_db().execute(
        "DELETE FROM events WHERE id = ?",
        (event_id,),
    )

    get_db().commit()

    flash(f"Event '{event['name']}' deleted successfully.", "success")
    return redirect(url_for("admin_dashboard"))


@app.post("/event/<int:event_id>/register")
@login_required
def register_for_event(event_id):
    if g.user["role"] != "student":
        flash("Only students can register for events.", "error")
        return redirect(url_for("index"))

    event = get_event_with_registration_count(event_id)

    if event["registration_count"] >= event["capacity"]:
        flash("This event is already full.", "error")
        return redirect(url_for("index"))

    existing_registration = get_db().execute(
        """
        SELECT id
        FROM registrations
        WHERE user_id = ? AND event_id = ?
        """,
        (g.user["id"], event_id),
    ).fetchone()

    if existing_registration:
        flash("You are already registered for this event.", "error")
        return redirect(url_for("student_dashboard"))

    get_db().execute(
        """
        INSERT INTO registrations
        (user_id, event_id, registered_at)
        VALUES (?, ?, ?)
        """,
        (
            g.user["id"],
            event_id,
            datetime.now().isoformat(),
        ),
    )

    get_db().commit()

    flash("Registration completed successfully.", "success")
    return redirect(url_for("student_dashboard"))


@app.post("/event/<int:event_id>/cancel")
@login_required
def cancel_registration(event_id):
    if g.user["role"] != "student":
        flash("Only students can cancel registrations.", "error")
        return redirect(url_for("index"))

    get_db().execute(
        """
        DELETE FROM registrations
        WHERE user_id = ? AND event_id = ?
        """,
        (g.user["id"], event_id),
    )

    get_db().commit()

    flash("Registration cancelled successfully.", "success")
    return redirect(url_for("student_dashboard"))


@app.route("/student")
@login_required
def student_dashboard():
    registrations = get_db().execute(
        """
        SELECT
            r.id,
            r.registered_at,
            e.id AS event_id,
            e.name,
            e.category,
            e.date,
            e.time,
            e.venue,
            e.organizer
        FROM registrations r
        JOIN events e ON r.event_id = e.id
        WHERE r.user_id = ?
        ORDER BY e.date ASC, e.time ASC
        """,
        (g.user["id"],),
    ).fetchall()

    return render_template(
        "student_dashboard.html",
        registrations=registrations,
    )


@app.post("/admin/registration/<int:registration_id>/delete")
@admin_required
def delete_registration(registration_id):
    registration = get_db().execute(
        """
        SELECT id
        FROM registrations
        WHERE id = ?
        """,
        (registration_id,),
    ).fetchone()

    if registration is None:
        abort(404)

    get_db().execute(
        "DELETE FROM registrations WHERE id = ?",
        (registration_id,),
    )

    get_db().commit()

    flash("Registration removed successfully.", "success")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/registrations/clear")
@admin_required
def clear_registrations():
    get_db().execute("DELETE FROM registrations")
    get_db().commit()

    flash("All registrations have been removed.", "success")
    return redirect(url_for("admin_dashboard"))


def get_event_form_data():
    capacity_value = request.form.get("capacity", "").strip()

    try:
        capacity = int(capacity_value)
    except ValueError:
        capacity = 0

    return {
        "name": request.form.get("name", "").strip(),
        "category": request.form.get("category", "").strip(),
        "date": request.form.get("date", "").strip(),
        "time": request.form.get("time", "").strip(),
        "venue": request.form.get("venue", "").strip(),
        "capacity": capacity,
        "organizer": request.form.get("organizer", "").strip(),
        "description": request.form.get("description", "").strip(),
    }


def validate_event_data(data):
    required_fields = [
        "name",
        "category",
        "date",
        "time",
        "venue",
        "organizer",
        "description",
    ]

    for field in required_fields:
        if not data[field]:
            return f"{field.capitalize()} is required."

    if data["capacity"] < 1:
        return "Capacity must be at least 1."

    return None


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(debug=True)