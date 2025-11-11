"""Test script to verify admin songs route works correctly"""
import sqlite3

DB_PATH = 'music_recommendation.db'

def test_admin_songs_query():
    """Test the query used in admin_songs route"""
    try:
        connection = sqlite3.connect(DB_PATH)
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        
        # This is the exact query from admin_songs route
        cursor.execute("SELECT * FROM music ORDER BY created_at DESC")
        all_songs = cursor.fetchall()
        
        print(f"[OK] Query executed successfully")
        print(f"[OK] Found {len(all_songs)} songs")
        
        if len(all_songs) > 0:
            print(f"\nFirst song:")
            song = all_songs[0]
            print(f"  ID: {song['id']}")
            print(f"  Title: {song['title']}")
            print(f"  Artist: {song['artist']}")
            print(f"  Genre: {song['genre']}")
            print(f"  Year: {song['year']}")
            
        print("\n[OK] Admin songs route query works correctly!")
        return True
        
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        return False
    finally:
        if connection:
            connection.close()

if __name__ == '__main__':
    print("=" * 60)
    print("Testing Admin Songs Route Query")
    print("=" * 60)
    test_admin_songs_query()
    print("=" * 60)
