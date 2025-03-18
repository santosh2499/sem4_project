import sqlite3
import pandas as pd
from datetime import datetime
import pickle
from flask import Flask, render_template, request, redirect, flash, url_for
import joblib

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Required for flashing messages

# Load ML models
with open('model.pkl', 'rb') as model_file, open('vectorizer.pkl', 'rb') as vectorizer_file:
    model = pickle.load(model_file)
    vectorizer = pickle.load(vectorizer_file)



# Database initialization
def init_db():
    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

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
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT UNIQUE NOT NULL,
        amount REAL NOT NULL
    )""")

    conn.commit()
    conn.close()


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
    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    # Get total expenses
    cursor.execute("SELECT SUM(price) FROM expenses")
    total_expense = cursor.fetchone()[0] or 0

    # Get latest transactions
    cursor.execute("SELECT * FROM expenses ORDER BY timestamp DESC LIMIT 5")
    recent_transactions = cursor.fetchall()

    # Get category totals
    cursor.execute("SELECT category, SUM(price) FROM expenses GROUP BY category")
    category_totals = cursor.fetchall()

    conn.close()

    return render_template('dashboard.html',
                           total_expense=total_expense,
                           recent_transactions=recent_transactions,
                           category_totals=category_totals)


@app.route('/add_expense', methods=['GET', 'POST'])
def add_expense():
    if request.method == 'POST':
        description = request.form['description']
        price = float(request.form['price'])

        # Predict category
        vectorized_text = vectorizer.transform([description])
        predicted_category = category_mapping.get(model.predict(vectorized_text)[0], "Uncategorized")

        conn = sqlite3.connect("expenses.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO expenses (description, category, price) VALUES (?, ?, ?)",
                       (description, predicted_category, price))
        conn.commit()
        conn.close()

        flash('Expense added successfully!', 'success')
        return redirect(url_for('add_expense'))

    return render_template('add_expense.html')


@app.route('/set_budget', methods=['GET', 'POST'])
def set_budget():
    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

    if request.method == 'POST':
        category = request.form['category']
        amount = float(request.form['amount'])

        cursor.execute("INSERT OR REPLACE INTO budgets (category, amount) VALUES (?, ?)",
                       (category, amount))
        conn.commit()
        flash('Budget updated successfully!', 'success')

    cursor.execute("SELECT category, amount FROM budgets")
    budgets = cursor.fetchall()

    conn.close()

    return render_template('set_budget.html', budgets=budgets)


@app.route('/detailed_transactions')
def detailed_transactions():
    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM expenses ORDER BY timestamp DESC")
    transactions = cursor.fetchall()
    conn.close()
    return render_template('detailed_transactions.html', transactions=transactions)


@app.route('/category_summary')
def category_summary():
    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()
    cursor.execute("SELECT category, SUM(price) FROM expenses GROUP BY category")
    summary = cursor.fetchall()
    conn.close()
    return render_template('category_summary.html', summary=summary)


@app.route('/category/<category>')
def category_transactions(category):
    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM expenses WHERE category = ? ORDER BY timestamp DESC", (category,))
    transactions = cursor.fetchall()
    conn.close()
    return render_template('category_transactions.html', category=category, transactions=transactions)


@app.route('/alerts')
def check_alerts():
    conn = sqlite3.connect("expenses.db")
    cursor = conn.cursor()

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

    conn.close()
    return render_template('alerts.html', alerts=alerts)


if __name__ == '__main__':
    app.run(debug=True)