import os
import sqlite3
import pickle
import requests
from datetime import datetime
from flask import Flask, render_template, request, redirect, flash, url_for, g

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Load ML models
with open('model.pkl', 'rb') as model_file, open('vectorizer.pkl', 'rb') as vectorizer_file:
    model = pickle.load(model_file)
    vectorizer = pickle.load(vectorizer_file)

# Category mapping
category_mapping = {
    1: "Entertainment", 2: "Finance", 3: "Food_Drinks",
    4: "Health", 5: "Health", 6: "Housing", 7: "Insurance",
    8: "Lifestyle", 9: "Loans", 10: "Shopping",
    11: "Technology", 12: "Transportation", 13: "Travel", 14: "Utilities"
}

# Database connection
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect('expenses.db')
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db:
        db.close()

# DB Initialization
def init_db():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            category TEXT PRIMARY KEY NOT NULL,
            amount REAL NOT NULL
        )""")
    db.commit()

# Fetch budget
def get_total_budget_from_db():
    conn = sqlite3.connect('expenses.db')
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(amount) FROM budgets WHERE category != 'monthly'")
    result = cursor.fetchone()
    total = result[0] if result and result[0] else 0

    # Update 'monthly' budget for display consistency
    cursor.execute("INSERT OR REPLACE INTO budgets (category, amount) VALUES ('monthly', ?)", (total,))
    conn.commit()
    conn.close()
    return total

# Update per-category budget
def update_budget_in_db(category, amount):
    conn = sqlite3.connect('expenses.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO budgets (category, amount) VALUES (?, ?)", (category, amount))
    conn.commit()
    conn.close()

# Fetch and store transactions from mock API
def fetch_data_on_startup():
    try:
        api_url = "http://127.0.0.1:5000/api/transactions"
        response = requests.get(api_url)
        response.raise_for_status()
        transactions = response.json()

        db = get_db()
        cursor = db.cursor()

        inserted_count = 0
        for txn in transactions:
            description = txn.get("description", "")
            amount = float(txn.get("amount", 0))
            timestamp = txn.get("date", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            vectorized_text = vectorizer.transform([description])
            predicted_category = category_mapping.get(model.predict(vectorized_text)[0], "Uncategorized")

            cursor.execute("""
                INSERT INTO expenses (description, category, price, timestamp)
                VALUES (?, ?, ?, ?)
            """, (description, predicted_category, amount, timestamp))
            inserted_count += 1

        db.commit()
        print(f"✅ {inserted_count} transactions fetched and stored on startup.")

    except Exception as e:
        print(f"❌ Error fetching transactions on startup: {e}")

# Home page showing total budget progress
@app.route("/")
def home():
    budget_amount = get_total_budget_from_db()
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT SUM(price) FROM expenses")
    total_expense = cursor.fetchone()[0] or 0
    spent_percentage = (total_expense / budget_amount) * 100 if budget_amount > 0 else 0

    return render_template("index.html", 
                           budget_amount=budget_amount,
                           spent_percentage=round(spent_percentage, 2))

# Add new expense manually
@app.route('/add_expense', methods=['GET', 'POST'])
def add_expense():
    if request.method == 'POST':
        description = request.form['description']
        price = float(request.form['price'])

        vectorized_text = vectorizer.transform([description])
        predicted_category = category_mapping.get(model.predict(vectorized_text)[0], "Uncategorized")

        db = get_db()
        cursor = db.cursor()
        cursor.execute("INSERT INTO expenses (description, category, price) VALUES (?, ?, ?)",
                       (description, predicted_category, price))
        db.commit()

        flash('Expense added successfully!', 'success')
        return redirect(url_for('add_expense'))

    return render_template('add_expense.html')

# Set or view budget for categories
@app.route('/set_budget', methods=['GET', 'POST'])
def set_budget():
    db = get_db()
    cursor = db.cursor()

    if request.method == 'POST':
        category = request.form['category']
        amount = request.form['amount']

        if not category or not amount:
            flash("Both category and amount are required!", "danger")
        else:
            try:
                amount = float(amount)
                update_budget_in_db(category, amount)
                flash("Budget updated successfully!", "success")
            except ValueError:
                flash("Invalid amount entered!", "danger")

    # Recalculate monthly budget from category budgets
    get_total_budget_from_db()

    cursor.execute("""
        SELECT b.category, 
               b.amount, 
               COALESCE(SUM(e.price), 0) AS spent 
        FROM budgets b 
        LEFT JOIN expenses e ON b.category = e.category 
        GROUP BY b.category, b.amount
    """)
    budgets = [{"category": row["category"], "amount": row["amount"], "spent": row["spent"]} for row in cursor.fetchall()]
    return render_template('set_budget.html', budgets=budgets, category_mapping=category_mapping)

# Dashboard with summary
@app.route('/dashboard')
def dashboard():
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT SUM(price) FROM expenses")
    total_expense = cursor.fetchone()[0] or 0

    cursor.execute("SELECT * FROM expenses ORDER BY timestamp DESC LIMIT 5")
    recent_transactions = cursor.fetchall()

    cursor.execute("SELECT category, SUM(price) FROM expenses GROUP BY category")
    category_totals = cursor.fetchall()

    return render_template('dashboard.html',
                           total_expense=total_expense,
                           recent_transactions=recent_transactions,
                           category_totals=category_totals)

# Full transaction history
@app.route('/detailed_transactions')
def detailed_transactions():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT timestamp, description, category, price FROM expenses ORDER BY timestamp DESC")
    transactions = cursor.fetchall()
    return render_template('detailed_transactions.html', transactions=transactions)

# Manually trigger external transaction fetch
@app.route('/fetch_external_transactions')
def fetch_external_transactions():
    try:
        api_url = "http://127.0.0.1:5000/api/transactions"
        response = requests.get(api_url)
        response.raise_for_status()
        transactions = response.json()

        db = get_db()
        cursor = db.cursor()
        inserted_count = 0

        for txn in transactions:
            description = txn.get("description", "")
            amount = float(txn.get("amount", 0))
            timestamp = txn.get("date", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            vectorized_text = vectorizer.transform([description])
            predicted_category = category_mapping.get(model.predict(vectorized_text)[0], "Uncategorized")

            cursor.execute("""
                INSERT INTO expenses (description, category, price, timestamp)
                VALUES (?, ?, ?, ?)
            """, (description, predicted_category, amount, timestamp))
            inserted_count += 1

        db.commit()
        flash(f"✅ Successfully fetched and stored {inserted_count} transactions from API.", "success")

    except Exception as e:
        flash(f"❌ Error fetching transactions: {str(e)}", "danger")

    return redirect(url_for('dashboard'))




@app.route('/alerts')
def check_alerts():
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT category, amount FROM budgets")
    budgets = dict(cursor.fetchall())

    cursor.execute("SELECT category, SUM(price) FROM expenses GROUP BY category")
    expenses = dict(cursor.fetchall())

    alerts = []
    for category, budget in budgets.items():
        spent = expenses.get(category, 0)
        if spent >= budget:
            alerts.append(f"🚨 {category} budget exceeded by ₹{spent - budget:.2f}!")
        elif spent >= 0.9 * budget:
            alerts.append(f"⚠️ {category} budget reaching limit ({spent / budget * 100:.1f}% used)")

    return render_template('alerts.html', alerts=alerts)





@app.route('/category_summary')
def category_summary():
    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()
    cursor.execute("SELECT category, SUM(price) FROM expenses GROUP BY category ORDER BY SUM(price) DESC")
    summary_data = cursor.fetchall()
    conn.close()

    category_names = [row[0] for row in summary_data] if summary_data else []
    category_totals = [row[1] for row in summary_data] if summary_data else []

    return render_template("category_summary.html",
                           summary_data=summary_data,
                           category_names=category_names,
                           category_totals=category_totals)

@app.route('/category/<category>')
def category_transactions(category):
    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()
    cursor.execute("SELECT description, price, timestamp FROM expenses WHERE category = ? ORDER BY timestamp DESC", (category,))
    transactions = cursor.fetchall()
    cursor.execute("SELECT SUM(price) FROM expenses WHERE category = ?", (category,))
    total_spent = cursor.fetchone()[0] or 0
    conn.close()

    return render_template("category_transactions.html",
                           category=category,
                           transactions=transactions,
                           total_spent=total_spent)




# Main
if __name__ == "__main__":
    with app.app_context():
        init_db()
        fetch_data_on_startup()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

