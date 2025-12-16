from fastmcp import FastMCP
import os
import aiosqlite  # Changed: sqlite3 → aiosqlite
import tempfile
from datetime import date as date_class
# Use temporary directory which should be writable

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(BASE_DIR, "expenses.db")
CATEGORIES_PATH = os.path.join(os.path.dirname(__file__), "categories.json")

print(f"Database path: {DB_PATH}")

mcp = FastMCP("ExpenseTracker")

def init_db():  # Keep as sync for initialization
    try:
        # Use synchronous sqlite3 just for initialization
        import sqlite3
        with sqlite3.connect(DB_PATH) as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("""
                CREATE TABLE IF NOT EXISTS expenses(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    amount REAL NOT NULL,
                    category TEXT NOT NULL,
                    subcategory TEXT DEFAULT '',
                    note TEXT DEFAULT ''
                )
            """)
            # Test write access
            c.execute("INSERT OR IGNORE INTO expenses(date, amount, category) VALUES ('2000-01-01', 0, 'test')")
            c.execute("DELETE FROM expenses WHERE category = 'test'")
            print("Database initialized successfully with write access")
    except Exception as e:
        print(f"Database initialization error: {e}")
        raise

# Initialize database synchronously at module load
init_db()

@mcp.tool()
async def add_expense(amount, category, subcategory="", note="", date=None):  # Changed: added async, made date optional
    '''Add a new expense entry to the database. If date is not provided, it defaults to today's date.'''
    if date is None:
        date = str(date_class.today())
    try:
        async with aiosqlite.connect(DB_PATH) as c:  # Changed: added async
            cur = await c.execute(  # Changed: added await
                "INSERT INTO expenses(date, amount, category, subcategory, note) VALUES (?,?,?,?,?)",
                (date, amount, category, subcategory, note)
            )
            expense_id = cur.lastrowid
            await c.commit()  # Changed: added await
            return {"status": "success", "id": expense_id, "message": "Expense added successfully"}
    except Exception as e:  # Changed: simplified exception handling
        if "readonly" in str(e).lower():
            return {"status": "error", "message": "Database is in read-only mode. Check file permissions."}
        return {"status": "error", "message": f"Database error: {str(e)}"}
    
@mcp.tool()
async def list_expenses(start_date=None, end_date=None):  # Changed: made both dates optional
    '''List expense entries. You can provide start_date, end_date, both, or neither. If both are provided, it uses a date range. If only one is provided, it filters from/to that date. If neither is provided, it lists all expenses.'''
    try:
        async with aiosqlite.connect(DB_PATH) as c:  # Changed: added async
            if start_date and end_date:
                query = """
                    SELECT id, date, amount, category, subcategory, note
                    FROM expenses
                    WHERE date BETWEEN ? AND ?
                    ORDER BY date DESC, id DESC
                """
                params = (start_date, end_date)
            elif start_date:
                query = """
                    SELECT id, date, amount, category, subcategory, note
                    FROM expenses
                    WHERE date >= ?
                    ORDER BY date DESC, id DESC
                """
                params = (start_date,)
            elif end_date:
                query = """
                    SELECT id, date, amount, category, subcategory, note
                    FROM expenses
                    WHERE date <= ?
                    ORDER BY date DESC, id DESC
                """
                params = (end_date,)
            else:
                query = """
                    SELECT id, date, amount, category, subcategory, note
                    FROM expenses
                    ORDER BY date DESC, id DESC
                """
                params = ()
            
            cur = await c.execute(query, params)  # Changed: added await
            cols = [d[0] for d in cur.description]
            print(f"Columns: {cols}")
            print(f"Fetching expenses...")
            expenses = await cur.fetchall()
            print(f"Expenses: {expenses}")
            return [dict(zip(cols, r)) for r in expenses]  # Fixed: use the already fetched expenses
    
    except Exception as e:
        return {"status": "error", "message": f"Error listing expenses: {str(e)}"}

@mcp.tool()
async def summarize(start_date=None, end_date=None, category=None):  # Changed: made both dates optional
    '''Summarize expenses by category. You can provide start_date, end_date, both, or neither. If both are provided, it uses a date range. If only one is provided, it filters from/to that date. If neither is provided, it includes all expenses.'''
    try:
        async with aiosqlite.connect(DB_PATH) as c:  # Changed: added async
            query = """
                SELECT category, SUM(amount) AS total_amount, COUNT(*) as count
                FROM expenses
                WHERE 1=1
            """
            params = []

            if start_date and end_date:
                query += " AND date BETWEEN ? AND ?"
                params.extend([start_date, end_date])
            elif start_date:
                query += " AND date >= ?"
                params.append(start_date)
            elif end_date:
                query += " AND date <= ?"
                params.append(end_date)

            if category:
                query += " AND category = ?"
                params.append(category)

            query += " GROUP BY category ORDER BY total_amount DESC"

            cur = await c.execute(query, params)  # Changed: added await
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in await cur.fetchall()]  # Changed: added await
    except Exception as e:
        return {"status": "error", "message": f"Error summarizing expenses: {str(e)}"}

@mcp.resource("expense:///categories", mime_type="application/json")  # Changed: expense:// → expense:///
def categories():
    try:
        # Provide default categories if file doesn't exist
        default_categories = {
            "categories": [
                "Food & Dining",
                "Transportation",
                "Shopping",
                "Entertainment",
                "Bills & Utilities",
                "Healthcare",
                "Travel",
                "Education",
                "Business",
                "Other"
            ]
        }
        
        try:
            with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            import json
            return json.dumps(default_categories, indent=2)
    except Exception as e:
        return f'{{"error": "Could not load categories: {str(e)}"}}'

# Start the server
if __name__ == "__main__":
    # Use port 8080 for cloud deployment (Lambda Web Adapter default), or 8000 for local
    port = int(os.environ.get("PORT", "8080"))
    mcp.run(transport="http", host="0.0.0.0", port=port)