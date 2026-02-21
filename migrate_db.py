"""Database migration script to add is_admin column"""
import sqlite3

DATABASE = 'neural_log.db'

def migrate():
    """Add is_admin column to users table if it doesn't exist"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Check if column exists
    cursor.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'is_admin' not in columns:
        print("Adding is_admin column to users table...")
        cursor.execute('ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0')
        conn.commit()
        print("Migration complete!")
        
        # Make first user an admin if exists
        cursor.execute('SELECT id FROM users ORDER BY id LIMIT 1')
        first_user = cursor.fetchone()
        if first_user:
            cursor.execute('UPDATE users SET is_admin = 1 WHERE id = ?', (first_user[0],))
            conn.commit()
            print(f"Set user ID {first_user[0]} as admin")
    else:
        print("Column is_admin already exists. No migration needed.")
    
    conn.close()

if __name__ == '__main__':
    migrate()
