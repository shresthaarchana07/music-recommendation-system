import mysql.connector
from mysql.connector import Error
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'database': 'music_recommendation_db',
    'user': 'root',
    'password': ''
}

def create_tables():
    try:
        # Connect to MySQL server
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor()
        
        logger.info("Connected to MySQL database")
        
        # Create users table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        # Create music table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS music (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            artist VARCHAR(255) NOT NULL,
            album VARCHAR(255),
            genre VARCHAR(100),
            year INT,
            duration INT,
            audio_url VARCHAR(500),
            features TEXT,
            popularity_score INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        # Create user_preferences table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id VARCHAR(100),
            music_id INT,
            preference_score FLOAT DEFAULT 1.0,
            interaction_type VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (music_id) REFERENCES music(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        # Create listening_history table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS listening_history (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id VARCHAR(100),
            music_id INT,
            play_duration INT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (music_id) REFERENCES music(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        # Create admin user if not exists
        cursor.execute("SELECT * FROM users WHERE email = 'admin@gmail.com'")
        admin = cursor.fetchone()
        
        if not admin:
            from werkzeug.security import generate_password_hash
            hashed_password = generate_password_hash('password')
            cursor.execute(
                "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
                ('Admin', 'admin@gmail.com', hashed_password)
            )
            logger.info("Created admin user")
        
        connection.commit()
        logger.info("Database tables created/verified successfully")
        
    except Error as e:
        logger.error(f"Error: {e}")
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()
            logger.info("MySQL connection is closed")

if __name__ == "__main__":
    create_tables()
