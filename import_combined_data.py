import pandas as pd
import mysql.connector
from mysql.connector import Error

# Database config
DB_CONFIG = {
    'host': 'localhost',
    'database': 'music_recommendation_db',
    'user': 'root',
    'password': ''
}

def insert_combined_data():
    try:
        df = pd.read_csv("static/data/combined_dataset.csv")
        df.fillna('', inplace=True)  # Avoid NaNs

        # Clean and convert date
        df['year'] = pd.to_datetime(df['track_album_release_date'], errors='coerce').dt.year.fillna(0).astype(int)

        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor()

        for index, row in df.iterrows():
            insert_query = """
                INSERT INTO music (title, artist, album, genre, year, duration, audio_url, features)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(insert_query, (
                row.get('track_name', ''),
                row.get('track_artist', ''),
                row.get('track_album_name', ''),
                row.get('playlist_name', ''),  # ✅ Corrected genre
                int(row.get('year', 0)),
                int(row.get('duration_ms', 0)) // 1000,
                '',  # Placeholder for audio_url
                f"{row.get('playlist_name', '')} {row.get('track_artist', '')} {row.get('text', '')}"
            ))

        connection.commit()
        print("✅ Combined dataset inserted into database successfully.")

    except Error as e:
        print("❌ MySQL error:", e)

insert_combined_data()
