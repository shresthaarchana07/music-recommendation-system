import mysql.connector
from mysql.connector import Error

def test_connection():
    try:
        # Try to connect without database first
        connection = mysql.connector.connect(
            host='localhost',
            user='root',
            password=''
        )
        
        if connection.is_connected():
            print("Successfully connected to MySQL server!")
            
            # Check if database exists
            cursor = connection.cursor()
            cursor.execute("SHOW DATABASES LIKE 'music_recommendation_db'")
            result = cursor.fetchone()
            
            if result:
                print("Database 'music_recommendation_db' exists!")
            else:
                print("Database 'music_recommendation_db' does not exist yet.")
                
    except Error as e:
        print(f"Error: {e}")
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()
            print("MySQL connection is closed")

if __name__ == "__main__":
    test_connection()
