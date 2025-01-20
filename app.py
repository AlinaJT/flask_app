from flask import Flask, render_template, request, session, redirect, url_for, flash
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.security import check_password_hash, generate_password_hash
import sqlite3
from functools import wraps
import os
import re

# Initialize Flask application with a development secret key
app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev_key_please_change'

# Database connection helper function
def get_db():
    db = sqlite3.connect(
        'project.db',
        detect_types=sqlite3.PARSE_DECLTYPES
    )
    # Configure row_factory to allow dictionary-style access to rows
    db.row_factory = sqlite3.Row
    return db

# Decorator to require login for protected routes
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user_id exists in session
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function

# Custom template filter to format dates consistently
@app.template_filter('format_date')
def format_date(value):
    # Return empty string if value is None
    if value is None:
        return ""
    # Handle string date inputs by converting to datetime
    if isinstance(value, str):
        try:
            value = datetime.strptime(value, '%Y-%m-%d')
        except ValueError:
            return value
    return value.strftime('%Y-%m-%d')

# Root route - redirects to dashboard if logged in, otherwise to login page
@app.route("/")
def index():
    if session.get("user_id"):
        return redirect("/dashboard")
    return redirect("/login")

# User registration handling
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")
        email = request.form.get("email")

        # Validation checks
        if not username:
            flash("Must provide username", "error")
            return render_template("register.html")
        elif not password:
            flash("Must provide password", "error")
            return render_template("register.html")
        elif password != confirmation:
            flash("Passwords must match", "error")
            return render_template("register.html")

        # Additional password complexity validation
        # Requires: minimum length, uppercase, lowercase, number, special character
        if (len(password) < 8 or
            not re.search(r'[A-Z]', password) or
            not re.search(r'[a-z]', password) or
            not re.search(r'\d', password) or
            not re.search(r'[!@#$%^&*(),.?":{}|<>]', password)):
            flash("Password does not meet complexity requirements", "error")
            return render_template("register.html")

        db = get_db()
        try:
            # Check if username already exists
            existing_user = db.execute(
                "SELECT * FROM users WHERE username = ?",
                (username,)
            ).fetchone()

            if existing_user:
                flash("Username already exists", "error")
                return render_template("register.html")

            # Insert new user with hashed password
            db.execute(
                "INSERT INTO users (username, hash, email) VALUES (?, ?, ?)",
                (username, generate_password_hash(password), email),
            )
            db.commit()

            # Add success flash message and redirect
            flash("Registration successful!", "success")
            return redirect(url_for("login"))

        except sqlite3.Error as e:
             # Log database errors and show generic error to user
            print(f"Database error: {e}")
            flash("An error occurred during registration", "error")
            return render_template("register.html")

    return render_template("register.html")

# User login handling with session management
@app.route("/login", methods=["GET", "POST"])
def login():
    # Clear any existing session data
    session.clear()
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        # Validate required fields
        if not username or not password:
            flash("Must provide username and password", "error")
            return render_template("login.html")

        db = get_db()
        # Query user and verify password
        user = db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

        if user is None or not check_password_hash(user["hash"], password):
            flash("Invalid username and/or password", "error")
            return render_template("login.html")

         # Store user ID in session and redirect to dashboard
        session["user_id"] = user["id"]
        return redirect("/dashboard")

    return render_template("login.html")

# Clear session and logout user
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# Display user's project dashboard with task completion statistics
@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    # Query projects with task statistics using LEFT JOIN
    projects = db.execute(
        """
        SELECT p.*,
               COUNT(DISTINCT t.id) as total_tasks,
               COUNT(DISTINCT CASE WHEN t.completed = 1 THEN t.id END) as completed_tasks
        FROM projects p
        LEFT JOIN tasks t ON p.id = t.project_id
        WHERE p.user_id = ?
        GROUP BY p.id
        ORDER BY p.created_at DESC
        """,
        (session["user_id"],)
    ).fetchall()
    return render_template("dashboard.html", projects=projects)

# Create new project with title, description, and deadline
@app.route("/new_project", methods=["GET", "POST"])
@login_required
def new_project():
    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")
        deadline = request.form.get("deadline")

         # Validate required title
        if not title:
            flash("Must provide project title", "error")
            return render_template("new_project.html")

        db = get_db()
        # Insert new project linked to current user
        db.execute(
            "INSERT INTO projects (user_id, title, description, deadline) VALUES (?, ?, ?, ?)",
            (session["user_id"], title, description, deadline)
        )
        db.commit()
        flash("Project created successfully!", "success")
        return redirect("/dashboard")

    return render_template("new_project.html")

# Edit existing project details or delete project
@app.route("/project/<int:project_id>/edit", methods=["GET", "POST"])
@login_required
def edit_project(project_id):
    db = get_db()
    # Verify user owns the project
    project = db.execute(
        "SELECT * FROM projects WHERE id = ? AND user_id = ?",
        (project_id, session["user_id"])
    ).fetchone()

    if project is None:
        flash("Project not found", "error")
        return redirect("/dashboard")

    # Get possible status options from the DB or define them here
    status_options = ["In Progress", "On Hold", "Completed", "Cancelled"]

    if request.method == "POST":
        # Check if this is a delete request
        if request.form.get("action") == "delete":
            # First, delete all associated tasks
            db.execute("DELETE FROM tasks WHERE project_id = ?", (project_id,))
            # Then delete the project
            db.execute("DELETE FROM projects WHERE id = ? AND user_id = ?",
                       (project_id, session["user_id"]))
            db.commit()
            flash("Project deleted successfully!", "success")
            return redirect("/dashboard")

        # Regular edit logic
        title = request.form.get("title")
        description = request.form.get("description")
        deadline = request.form.get("deadline")
        status = request.form.get("status")

        if not title:
            flash("Must provide project title", "error")
            return render_template("edit_project.html", project=project, status_options=status_options)

         # Validate status is in allowed options
        if status not in status_options:
            status = project["status"]  # Default to existing status if invalid

        # Update project details
        db.execute(
            """
            UPDATE projects
            SET title = ?, description = ?, deadline = ?, status = ?
            WHERE id = ? AND user_id = ?
            """,
            (title, description, deadline, status, project_id, session["user_id"])
        )
        db.commit()

        flash("Project updated successfully!", "success")
        return redirect(url_for("project", project_id=project_id))

    return render_template("edit_project.html", project=project, status_options=status_options)

# Display individual project details and associated task
@app.route("/project/<int:project_id>")
@login_required
def project(project_id):
    db = get_db()
    # Get project details with task statistics
    project = db.execute(
        """
        SELECT p.*,
               COUNT(DISTINCT t.id) as total_tasks,
               COUNT(DISTINCT CASE WHEN t.completed = 1 THEN t.id END) as completed_tasks
        FROM projects p
        LEFT JOIN tasks t ON p.id = t.project_id
        WHERE p.id = ? AND p.user_id = ?
        GROUP BY p.id
        """,
        (project_id, session["user_id"])
    ).fetchone()

    if project is None:
        flash("Project not found", "error")
        return redirect("/dashboard")

    # Get all tasks for the project, ordered by due date
    tasks = db.execute(
        "SELECT * FROM tasks WHERE project_id = ? ORDER BY due_date ASC",
        (project_id,)
    ).fetchall()

    return render_template("project.html", project=project, tasks=tasks)

# Add new task to an existing project
@app.route("/project/<int:project_id>/add_task", methods=["POST"])
@login_required
def add_task(project_id):
    title = request.form.get("title")
    description = request.form.get("description")
    due_date = request.form.get("due_date")

    # Validate required title
    if not title:
        flash("Must provide task title", "error")
        return redirect(url_for("project", project_id=project_id))

    db = get_db()
    # Insert new task
    db.execute(
        "INSERT INTO tasks (project_id, title, description, due_date) VALUES (?, ?, ?, ?)",
        (project_id, title, description, due_date)
    )
    db.commit()
    flash("Task added successfully!", "success")
    return redirect(url_for("project", project_id=project_id))

# Update task completion status and project progress
@app.route("/project/<int:project_id>/update_task/<int:task_id>", methods=["POST"])
@login_required
def update_task(project_id, task_id):
    completed = request.form.get("completed") == "true"

    db = get_db()
     # Update task completion status

    db.execute(
        "UPDATE tasks SET completed = ? WHERE id = ? AND project_id = ?",
        (completed, task_id, project_id)
    )

    # Calculate project progress
    # Get total number of tasks
    total = db.execute(
        "SELECT COUNT(*) as total FROM tasks WHERE project_id = ?",
        (project_id,)
    ).fetchone()["total"]

    # Get number of completed tasks
    completed_count = db.execute(
        "SELECT COUNT(*) as completed FROM tasks WHERE project_id = ? AND completed = 1",
        (project_id,)
    ).fetchone()["completed"]

    # Calculate progress percentage
    progress = (completed_count / total * 100) if total > 0 else 0

    # Update project progress
    db.execute(
        "UPDATE projects SET progress = ? WHERE id = ?",
        (progress, project_id)
    )
    db.commit()

    return {"status": "success", "progress": progress}

# Delete task and update project progress
@app.route("/project/<int:project_id>/delete_task/<int:task_id>", methods=["POST"])
@login_required
def delete_task(project_id, task_id):
    db = get_db()
    try:
        # Verify user owns the project
        project = db.execute(
            "SELECT * FROM projects WHERE id = ? AND user_id = ?",
            (project_id, session["user_id"])
        ).fetchone()

        if not project:
            return {"error": "Access denied"}, 403

        # Delete the task
        db.execute("DELETE FROM tasks WHERE id = ? AND project_id = ?",
                  (task_id, project_id))

        # Update project progress
        # Get new total task count
        total = db.execute(
            "SELECT COUNT(*) as total FROM tasks WHERE project_id = ?",
            (project_id,)
        ).fetchone()["total"]

        # Get new completed task count
        completed = db.execute(
            "SELECT COUNT(*) as completed FROM tasks WHERE project_id = ? AND completed = 1",
            (project_id,)
        ).fetchone()["completed"]

        # Calculate new progress percentage
        progress = (completed / total * 100) if total > 0 else 0

        # Update project progress
        db.execute(
            "UPDATE projects SET progress = ? WHERE id = ?",
            (progress, project_id)
        )
        db.commit()

        return {"status": "success", "progress": progress}
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return {"error": "Database error"}, 500

# Edit task details (title, description, due date)
@app.route("/project/<int:project_id>/edit_task/<int:task_id>", methods=["POST"])
@login_required
def edit_task(project_id, task_id):
    title = request.form.get("title")
    description = request.form.get("description")
    due_date = request.form.get("due_date")

    # Print debugging information
    print(f"Editing task {task_id} in project {project_id}")
    print(f"Form data: title={title}, description={description}, due_date={due_date}")

    # Validate required title
    if not title:
        return {"error": "Title is required"}, 400

    # Handle empty due date
    if due_date == "":
        due_date = None

    db = get_db()
    try:
        # Verify user owns the project
        project = db.execute(
            "SELECT * FROM projects WHERE id = ? AND user_id = ?",
            (project_id, session["user_id"])
        ).fetchone()

        if not project:
            return {"error": "Access denied"}, 403

        # Update the task
        db.execute(
            """
            UPDATE tasks
            SET title = ?, description = ?, due_date = ?
            WHERE id = ? AND project_id = ?
            """,
            (title, description, due_date, task_id, project_id)
        )
        db.commit()

        # Get updated task data
        task = db.execute(
            "SELECT * FROM tasks WHERE id = ?",
            (task_id,)
        ).fetchone()

        return {
            "status": "success",
            "task": {
                "id": task["id"],
                "title": task["title"],
                "description": task["description"],
                "due_date": task["due_date"]
            }
        }
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return {"error": f"Database error: {str(e)}"}, 500

# Delete entire project and its associated task
@app.route("/project/<int:project_id>/delete", methods=["POST"])
@login_required
def delete_project(project_id):
    db = get_db()
    db.execute("DELETE FROM tasks WHERE project_id = ?", (project_id,))
    db.execute("DELETE FROM projects WHERE id = ? AND user_id = ?",
               (project_id, session["user_id"]))
    db.commit()
    flash("Project deleted successfully!", "success")
    return redirect("/dashboard")

# Run the application in debug mode when executed directly
if __name__ == "__main__":
    app.run(debug=True)
