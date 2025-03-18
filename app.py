import sqlite3
import pandas as pd
from datetime import datetime
import pickle
from flask import Flask, render_template, request, redirect, flash, url_for, g
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Required for flashing messages

# Load ML models
with open('model.pkl', 'rb') as model_file, open('vectorizer.pkl', 'rb') as vectorizer_file:
    model = pickle.load(model_file)
    vectorizer = pickle.load(vectorizer_file)


# Database connection handling
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect("expenses.db")
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db is not None:
        db.close()


# Database initialization
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


with app.app_context():
    init_db()

# Category mapping
category_mapping = {
    1: "Entertainment", 2: "Finance", 3: "Food_Drinks",
    4: "Health", 5: "Health", 6: "Housing", 7: "Insurance",
    8: "Lifestyle", 9: "Loans", 10: "Shopping",
    11: "Technology", 12: "Transportation", 13: "Travel", 14: "Utilities"
}



# Routes
@app.route('/')
def home():
    return render_template('index.html')


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
                cursor.execute("INSERT OR REPLACE INTO budgets (category, amount) VALUES (?, ?)", (category, amount))
                db.commit()
                flash("Budget updated successfully!", "success")
            except ValueError:
                flash("Invalid amount entered!", "danger")

    # **FIXED SQL QUERY TO ENSURE SPENT AMOUNT IS ALWAYS PRESENT**
    cursor.execute("""
        SELECT b.category, 
               b.amount, 
               COALESCE(SUM(e.price), 0) AS spent 
        FROM budgets b 
        LEFT JOIN expenses e ON b.category = e.category 
        GROUP BY b.category, b.amount
    """)

    # **Ensure correct data structure to avoid Jinja errors**
    budgets = []
    for row in cursor.fetchall():
        budgets.append({
            "category": row["category"],
            "amount": row["amount"],
            "spent": row["spent"]  # ✅ Ensures 'spent' is always present
        })

    return render_template('set_budget.html', budgets=budgets, category_mapping=category_mapping)

@app.route('/detailed_transactions')
def detailed_transactions():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM expenses ORDER BY timestamp DESC")
    transactions = cursor.fetchall()
    return render_template('detailed_transactions.html', transactions=transactions)


@app.route('/category_summary')
def category_summary():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT category, SUM(price) FROM expenses GROUP BY category")
    summary = cursor.fetchall()
    return render_template('category_summary.html', summary=summary)


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




# Detailed Transactions for a Specific Category
@app.route('/category/<category>')
def category_transactions(category):
    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    # Fetch transactions for the selected category
    cursor.execute("SELECT description, price, timestamp FROM expenses WHERE category = ? ORDER BY timestamp DESC",
                   (category,))
    transactions = cursor.fetchall()

    conn.close()
    return render_template("category_transactions.html", category=category, transactions=transactions)




if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
