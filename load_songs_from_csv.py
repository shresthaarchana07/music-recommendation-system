import sqlite3
import pandas as pd
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database path
DB_PATH = os.path.join(os.path.dirname(__file__), 'music_recommendation.db')
CSV_PATH = os.path.join(os.path.dirname(__file__), 'Static', 'data', 'spotify_songs.csv')

def load_songs_from_csv():
    """Load all songs from CSV file into the database"""
    try:
        # Check if CSV file exists
        if not os.path.exists(CSV_PATH):
            logger.error(f"CSV file not found at: {CSV_PATH}")
            return
        
        # Read CSV file
        logger.info(f"Reading CSV file from: {CSV_PATH}")
        df = pd.read_csv(CSV_PATH, encoding='utf-8', on_bad_lines='skip')
        logger.info(f"Found {len(df)} songs in CSV file")
        
        # Connect to database
        connection = sqlite3.connect(DB_PATH)
        cursor = connection.cursor()
        
        # Clear existing music data
        cursor.execute("DELETE FROM music")
        connection.commit()
        logger.info("Cleared existing songs from database")
        
        # Insert songs from CSV
        inserted_count = 0
        skipped_count = 0
        
        for index, row in df.iterrows():
            try:
                # Extract data from CSV
                title = str(row.get('track_name', 'Unknown'))[:255]
                artist = str(row.get('track_artist', 'Unknown'))[:255]
                album = str(row.get('track_album_name', ''))[:255] if pd.notna(row.get('track_album_name')) else ''
                genre = str(row.get('playlist_genre', ''))[:100] if pd.notna(row.get('playlist_genre')) else ''
                
                # Extract year from release date
                year = None
                release_date = row.get('track_album_release_date')
                if pd.notna(release_date):
                    try:
                        year = int(str(release_date)[:4])
                    except:
                        year = None
                
                # Duration in seconds (convert from milliseconds)
                duration = None
                duration_ms = row.get('duration_ms')
                if pd.notna(duration_ms):
                    try:
                        duration = int(float(duration_ms) / 1000)
                    except:
                        duration = None
                
                # Audio URL (placeholder - you can add actual URLs if available)
                audio_url = ''
                
                # Create features string from audio features
                features_list = []
                if pd.notna(row.get('playlist_subgenre')):
                    features_list.append(str(row['playlist_subgenre']))
                if pd.notna(row.get('danceability')):
                    features_list.append(f"danceability:{row['danceability']}")
                if pd.notna(row.get('energy')):
                    features_list.append(f"energy:{row['energy']}")
                if pd.notna(row.get('valence')):
                    features_list.append(f"valence:{row['valence']}")
                if pd.notna(row.get('tempo')):
                    features_list.append(f"tempo:{row['tempo']}")
                
                features = ' '.join(features_list)[:500]
                
                # Insert into database
                cursor.execute(
                    """INSERT INTO music (title, artist, album, genre, year, duration, audio_url, features, popularity_score) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (title, artist, album, genre, year, duration, audio_url, features, 0)
                )
                inserted_count += 1
                
                # Log progress every 1000 songs
                if inserted_count % 1000 == 0:
                    logger.info(f"Inserted {inserted_count} songs...")
                    
            except Exception as e:
                skipped_count += 1
                if skipped_count <= 10:  # Only log first 10 errors
                    logger.warning(f"Skipped row {index}: {str(e)}")
                continue
        
        # Commit all changes
        connection.commit()
        connection.close()
        
        logger.info(f"✅ Successfully loaded {inserted_count} songs into database")
        if skipped_count > 0:
            logger.info(f"⚠️ Skipped {skipped_count} songs due to errors")
        
        return inserted_count
        
    except Exception as e:
        logger.error(f"Error loading songs from CSV: {e}")
        return 0

if __name__ == '__main__':
    print("=" * 60)
    print("Loading Songs from CSV to Database")
    print("=" * 60)
    count = load_songs_from_csv()
    print("=" * 60)
    print(f"Total songs loaded: {count}")
    print("=" * 60)
