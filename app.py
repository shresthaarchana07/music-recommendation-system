from flask import Flask,flash, request, jsonify, render_template, redirect, url_for, session, make_response
from flask_cors import CORS
import sqlite3
import os
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import logging
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = "mysecret123"
CORS(app)

# Database configuration - SQLite
DB_PATH = os.path.join(os.path.dirname(__file__), 'music_recommendation.db')

class MusicRecommendationSystem:
    def __init__(self):
        self.connection = None
        self.vectorizer = TfidfVectorizer(stop_words='english')
        self.feature_matrix = None
        self.music_data = None
        self.initialize_database()
        
    def get_database_connection(self):
        try:
            if self.connection is None:
                self.connection = sqlite3.connect(DB_PATH, check_same_thread=False)
                self.connection.row_factory = sqlite3.Row
                self.connection.execute('PRAGMA foreign_keys = ON;')
            return self.connection
        except sqlite3.Error as e:
            logger.error(f"Connection error: {e}")
        return None

    def initialize_database(self):
        """Initialize database tables"""
        try:
            connection = self.get_database_connection()
            if connection:
                cursor = connection.cursor()
                
                # Create users table
                create_users_table = """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'User',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
                
                # Create music table
                create_music_table = """
                CREATE TABLE IF NOT EXISTS music (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    artist TEXT NOT NULL,
                    album TEXT,
                    genre TEXT,
                    year INTEGER,
                    duration INTEGER,
                    audio_url TEXT,
                    features TEXT,
                    popularity_score INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
                
                # Create user preferences table (with unique pair)
                create_preferences_table = """
                CREATE TABLE IF NOT EXISTS user_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    music_id INTEGER,
                    preference_score REAL DEFAULT 1.0,
                    interaction_type TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, music_id),
                    FOREIGN KEY (music_id) REFERENCES music(id)
                )
                """
                
                # Create user listening history table
                create_history_table = """
                CREATE TABLE IF NOT EXISTS listening_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    music_id INTEGER,
                    play_duration INTEGER,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (music_id) REFERENCES music(id)
                )
                """

                # Create liked songs table
                create_liked_songs_table = """
                CREATE TABLE IF NOT EXISTS liked_songs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    music_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, music_id),
                    FOREIGN KEY (music_id) REFERENCES music(id)
                )
                """

                # Create playlists table
                create_playlists_table = """
                CREATE TABLE IF NOT EXISTS playlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, name)
                )
                """

                # Create playlist songs join table
                create_playlist_songs_table = """
                CREATE TABLE IF NOT EXISTS playlist_songs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    playlist_id INTEGER NOT NULL,
                    music_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(playlist_id, music_id),
                    FOREIGN KEY (playlist_id) REFERENCES playlists(id),
                    FOREIGN KEY (music_id) REFERENCES music(id)
                )
                """
                
                cursor.execute(create_users_table)
                cursor.execute(create_music_table)
                cursor.execute(create_preferences_table)
                cursor.execute(create_history_table)
                cursor.execute(create_liked_songs_table)
                cursor.execute(create_playlists_table)
                cursor.execute(create_playlist_songs_table)

                # Migration: add role column if missing (older DBs)
                cursor.execute("PRAGMA table_info(users)")
                columns = [row[1] for row in cursor.fetchall()]
                if 'role' not in columns:
                    cursor.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'User'")
                
                connection.commit()
                logger.info("Database initialized successfully")
                
        except sqlite3.Error as e:
            logger.error(f"Database initialization error: {e}")
    
    def insert_sample_data(self):
        """Reload music data from SQL file (force reload)."""
        try:
            connection = self.get_database_connection()
            cursor = connection.cursor()

            # Ensure table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='music'")
            if not cursor.fetchone():
                logger.warning("Music table does not exist yet. initialize_database() should create it.")
                return

            # Clear existing rows
            cursor.execute("DELETE FROM music")
            connection.commit()
            logger.info("Cleared existing songs from music table.")

            sql_file_path = os.path.join(os.path.dirname(__file__), 'music_recommendation_db.sql')
            if not os.path.exists(sql_file_path):
                logger.warning(f"SQL file not found at {sql_file_path}")
                return

            with open(sql_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                sql_content = f.read()

            import re
            # Try to capture both `INSERT INTO \`music\`` and INSERT INTO music (no backticks)
            pattern = r"INSERT\s+INTO\s+(`?music`?).*?VALUES\s*(.+?)(?=;|INSERT\s+INTO|\Z)"
            matches = re.findall(pattern, sql_content, re.IGNORECASE | re.DOTALL)

            if not matches:
                logger.warning("No INSERT INTO music statements found in SQL file (pattern mismatch).")
                logger.debug("SQL file excerpt (first 800 chars):\n" + sql_content[:800])
                return

            inserted_count = 0
            for _, values_text in matches:
                records = re.findall(r'\((.*?)\)(?:,|;|$)', values_text, re.DOTALL)
                for record in records:
                    try:
                        parts = []
                        current = ''
                        in_quote = False
                        escape_next = False
                        for char in record:
                            if escape_next:
                                current += char
                                escape_next = False
                            elif char == '\\':
                                escape_next = True
                            elif char == "'" and not in_quote:
                                in_quote = True
                            elif char == "'" and in_quote:
                                in_quote = False
                                parts.append(current)
                                current = ''
                            elif char == ',' and not in_quote:
                                if current.strip() and current.strip() != 'NULL':
                                    parts.append(current.strip())
                                elif current.strip() == 'NULL':
                                    parts.append(None)
                                current = ''
                            elif in_quote:
                                current += char
                            elif not in_quote and char not in (' ', '\t', '\n', '\r'):
                                current += char
                        if current.strip():
                            if current.strip() == 'NULL':
                                parts.append(None)
                            else:
                                parts.append(current.strip())
                        # Expect MySQL order: id, title, artist, album, genre, year, duration, audio_url, features, ...
                        if len(parts) >= 8:
                            title = parts[1] if len(parts) > 1 and parts[1] is not None else ''
                            artist = parts[2] if len(parts) > 2 and parts[2] is not None else ''
                            album = parts[3] if len(parts) > 3 and parts[3] is not None else ''
                            genre = parts[4] if len(parts) > 4 and parts[4] is not None else ''
                            year = int(parts[5]) if len(parts) > 5 and parts[5] and parts[5] != 'NULL' else None
                            duration = int(parts[6]) if len(parts) > 6 and parts[6] and parts[6] != 'NULL' else None
                            audio_url = parts[7] if len(parts) > 7 and parts[7] is not None else ''
                            features = parts[8] if len(parts) > 8 and parts[8] is not None else ''
                            cursor.execute(
                                "INSERT INTO music (title, artist, album, genre, year, duration, audio_url, features) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                (title, artist, album, genre, year, duration, audio_url, features)
                            )
                            inserted_count += 1
                    except Exception as e:
                        logger.warning(f"Skipped one record due to parsing error: {e}")
                        continue

            connection.commit()
            logger.info(f"✅ Reloaded {inserted_count} songs from SQL file.")
        except Exception as e:
            logger.error(f"Error loading music data: {e}")

    
    def get_all_music(self, query=None, genre=None, year=None):
        """Retrieve music from database with optional filters"""
        try:
            connection = self.get_database_connection()
            cursor = connection.cursor()
            
            sql = "SELECT * FROM music WHERE 1=1"
            params = []
            
            if query:
                sql += " AND (title LIKE ? OR artist LIKE ? OR album LIKE ?)"
                query_param = f"%{query}%"
                params.extend([query_param, query_param, query_param])
            
            if genre:
                sql += " AND genre LIKE ?"
                params.append(f"%{genre}%")
            
            if year:
                if year.endswith('s'):
                    if year == '90s':
                        sql += " AND year BETWEEN 1990 AND 1999"
                    elif year == '2000s':
                        sql += " AND year BETWEEN 2000 AND 2009"
                    elif year == '2010s':
                        sql += " AND year BETWEEN 2010 AND 2019"
                else:
                    sql += " AND year = ?"
                    params.append(int(year))
            
            sql += " ORDER BY popularity_score DESC, created_at DESC"
            
            cursor.execute(sql, params)
            music_list = cursor.fetchall()
            
            return music_list
            
        except sqlite3.Error as e:
            logger.error(f"Database query error: {e}")
            return []
    
    def build_feature_matrix(self):
        """Build TF-IDF feature matrix for cosine similarity"""
        try:
            music_data = self.get_all_music()
            if not music_data:
                return None
            
            feature_texts = []
            for music in music_data:
                features = music['features'] if music['features'] else ''
                genre = music['genre'].lower() if music['genre'] else ''
                artist = music['artist'].lower() if music['artist'] else ''
                combined_features = f"{features} {genre} {artist}"
                feature_texts.append(combined_features)
            
            self.feature_matrix = self.vectorizer.fit_transform(feature_texts)
            self.music_data = music_data
            logger.info(f"Built feature matrix with {len(music_data)} songs")
            return True
            
        except Exception as e:
            logger.error(f"Feature matrix building error: {e}")
            return False
    
    def calculate_similarities(self, user_preferences):
        """Calculate cosine similarities based on user preferences"""
        try:
            if self.feature_matrix is None or self.music_data is None:
                if not self.build_feature_matrix():
                    return []
            
            # Map music_id to indices
            music_id_to_index = {music['id']: idx for idx, music in enumerate(self.music_data)}
            preference_indices = [music_id_to_index.get(pref) for pref in user_preferences if pref in music_id_to_index]
            
            if not preference_indices:
                return []
            
            preference_vectors = self.feature_matrix[preference_indices]
            avg_preference = np.mean(preference_vectors.toarray(), axis=0)
            avg_preference = avg_preference.reshape(1, -1)
            
            similarities = cosine_similarity(avg_preference, self.feature_matrix)[0]
            
            recommendations = []
            music_similarities = list(enumerate(similarities))
            music_similarities.sort(key=lambda x: x[1], reverse=True)
            
            for idx, similarity in music_similarities:
                if idx not in preference_indices and similarity > 0.1:
                    # Convert sqlite3.Row to dict
                    music = dict(self.music_data[idx])
                    music['similarity_score'] = float(similarity)
                    recommendations.append(music)
                    if len(recommendations) >= 10:
                        break
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Similarity calculation error: {e}")
            return []
    
    def record_user_interaction(self, user_id, music_id, interaction_type='play'):
        """Record user interaction for improving recommendations"""
        try:
            connection = self.get_database_connection()
            cursor = connection.cursor()
            
            insert_pref = """
            INSERT INTO user_preferences (user_id, music_id, preference_score, interaction_type)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, music_id) DO UPDATE SET 
            preference_score = preference_score + excluded.preference_score,
            created_at = CURRENT_TIMESTAMP
            """
            
            score = 1.0 if interaction_type == 'play' else 0.5
            cursor.execute(insert_pref, (user_id, music_id, score, interaction_type))
            
            update_popularity = """
            UPDATE music SET popularity_score = popularity_score + 0.1 WHERE id = ?
            """
            cursor.execute(update_popularity, (music_id,))
            
            connection.commit()
            
        except sqlite3.Error as e:
            logger.error(f"User interaction recording error: {e}")

# Initialize the recommendation system
music_system = MusicRecommendationSystem()
music_system.build_feature_matrix()

def ensure_admin_account():
    """Bootstrap admin account with secure password and Admin role"""
    try:
        connection = music_system.get_database_connection()
        cursor = connection.cursor()
        admin_name = 'admin'
        admin_email = 'admin@gmail.com'
        admin_password_hash = generate_password_hash('admin123')
        admin_role = 'Admin'
        # Insert if missing
        cursor.execute(
            "INSERT OR IGNORE INTO users (name, email, password, role) VALUES (?, ?, ?, ?)",
            (admin_name, admin_email, admin_password_hash, admin_role)
        )
        # Ensure role/password are correct
        cursor.execute(
            "UPDATE users SET name = ?, password = ?, role = ? WHERE email = ?",
            (admin_name, admin_password_hash, admin_role, admin_email)
        )
        connection.commit()
        logger.info(f"Admin account ensured: username={admin_name}, email={admin_email}, role={admin_role}")
    except Exception as e:
        logger.error(f"Failed to ensure admin account: {e}")

@app.route('/api/music', methods=['GET'])
def get_music():
    """API endpoint to get music with optional filters"""
    try:
        query = request.args.get('query', '')
        genre = request.args.get('genre', '')
        year = request.args.get('year', '')
        
        music_list = music_system.get_all_music(query, genre, year)
        
        return jsonify({
            'success': True,
            'music': music_list,
            'count': len(music_list)
        })
        
    except Exception as e:
        logger.error(f"Get music API error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/recommend', methods=['POST'])
def get_recommendations():
    """API endpoint to get music recommendations based on user preferences"""
    try:
        data = request.get_json()
        preferences = data.get('preferences', [])
        user_id = data.get('user_id', 'anonymous')
        
        if not preferences:
            return jsonify({
                'success': False,
                'error': 'No preferences provided'
            }), 400
        
        recommendations = music_system.calculate_similarities(preferences)
        
        for pref in preferences:
            if isinstance(pref, int):
                music_system.record_user_interaction(user_id, pref, 'preference')
        
        return jsonify({
            'success': True,
            'recommendations': recommendations,
            'count': len(recommendations)
        })
        
    except Exception as e:
        logger.error(f"Recommendations API error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/play', methods=['POST'])
def record_play():
    """API endpoint to record music play events"""
    try:
        data = request.get_json()
        music_id = data.get('music_id')
        user_id = data.get('user_id', 'anonymous')
        duration = data.get('duration', 0)
        
        if not music_id:
            return jsonify({
                'success': False,
                'error': 'Music ID required'
            }), 400
        
        connection = music_system.get_database_connection()
        cursor = connection.cursor()
        
        insert_history = """
        INSERT INTO listening_history (user_id, music_id, play_duration)
        VALUES (?, ?, ?)
        """
        cursor.execute(insert_history, (user_id, music_id, duration))
        
        music_system.record_user_interaction(user_id, music_id, 'play')
        
        connection.commit()
        
        return jsonify({
            'success': True,
            'message': 'Play event recorded'
        })
        
    except Exception as e:
        logger.error(f"Record play API error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """API endpoint to get system statistics"""
    try:
        connection = music_system.get_database_connection()
        cursor = connection.cursor()
        
        cursor.execute("SELECT COUNT(*) as total_songs FROM music")
        total_songs = cursor.fetchone()['total_songs']
        
        cursor.execute("""
            SELECT genre, COUNT(*) as count 
            FROM music 
            GROUP BY genre 
            ORDER BY count DESC
        """)
        genre_stats = cursor.fetchall()
        
        cursor.execute("""
            SELECT title, artist, popularity_score 
            FROM music 
            ORDER BY popularity_score DESC 
            LIMIT 5
        """)
        popular_songs = cursor.fetchall()
        
        return jsonify({
            'success': True,
            'stats': {
                'total_songs': total_songs,
                'genres': genre_stats,
                'popular_songs': popular_songs
            }
        })
        
    except Exception as e:
        logger.error(f"Stats API error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    try:
        connection = music_system.get_database_connection()
        if connection and connection:
            return jsonify({
                'success': True,
                'status': 'healthy',
                'database': 'connected'
            })
        else:
            return jsonify({
                'success': False,
                'status': 'unhealthy',
                'database': 'disconnected'
            }), 503
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return jsonify({
            'success': False,
            'status': 'error',
            'error': str(e)
        }), 500

@app.route('/search', methods=['POST'])
def search():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    query = request.form['search_query']
    results = music_system.get_all_music(query=query)
    
    return render_template('dashboard.html',
                         songs=results,
                         history=[],
                         name=session.get('user_name', 'User'),
                         music_list=bool(results))

@app.route('/dashboard')
@app.route('/dashboard/<int:song_id>')
def dashboard(song_id=None):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        user_id = session['user_id']
        name = session.get('user_name', 'User')
        connection = music_system.get_database_connection()
        cursor = connection.cursor()

        current_song = None

        # If user clicked a specific song
        if song_id:
            cursor.execute("SELECT * FROM music WHERE id = ?", (song_id,))
            current_song = cursor.fetchone()

            # Record to recently played
            cursor.execute("""
                INSERT INTO listening_history (user_id, music_id, timestamp)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """, (user_id, song_id))
            connection.commit()

        # Fetch recently played songs
        cursor.execute("""
            SELECT DISTINCT m.*
            FROM music m
            JOIN listening_history h ON m.id = h.music_id
            WHERE h.user_id = ?
            ORDER BY h.timestamp DESC
            LIMIT 10
        """, (user_id,))
        recently_played = cursor.fetchall()

        # Recommend songs
        if song_id:
            # Recommend songs excluding current one
            cursor.execute("""
                SELECT * FROM music
                WHERE id != ?
                ORDER BY RANDOM()
                LIMIT 8
            """, (song_id,))
        else:
            # If no song selected, just random songs
            cursor.execute("""
                SELECT * FROM music
                ORDER BY RANDOM()
                LIMIT 8
            """)
        recommended_songs = cursor.fetchall()

        return render_template(
            'dashboard.html',
            name=name,
            current_song=current_song,
            history=recently_played,
            recommendations=recommended_songs
        )

    except Exception as e:
        logger.error(f"Error in dashboard: {e}")
        return render_template(
            'dashboard.html',
            name='User',
            message=str(e),
            current_song=None,
            history=[],
            recommendations=[]
        )
@app.route('/like_song/<int:song_id>', methods=['POST'])
def like_song(song_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})

    user_id = str(session['user_id'])  # Convert to string to match TEXT type in database
    try:
        connection = music_system.get_database_connection()
        cursor = connection.cursor()

        # Prevent duplicate likes
        cursor.execute("SELECT * FROM liked_songs WHERE user_id=? AND music_id=?", (user_id, song_id))
        if cursor.fetchone():
            return jsonify({'success': False, 'message': 'Already liked'})

        cursor.execute("INSERT INTO liked_songs (user_id, music_id) VALUES (?, ?)", (user_id, song_id))
        connection.commit()
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error liking song: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/add_to_playlist/<int:song_id>', methods=['POST'])
def add_to_playlist(song_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})

    user_id = str(session['user_id'])  # Convert to string to match TEXT type in database
    try:
        data = request.get_json()
        playlist_name = data.get('playlist_name', '').strip()
        
        if not playlist_name:
            return jsonify({'success': False, 'message': 'Playlist name is required'})
        
        connection = music_system.get_database_connection()
        cursor = connection.cursor()

        # Create playlist if it doesn't exist
        cursor.execute(
            "INSERT OR IGNORE INTO playlists (user_id, name) VALUES (?, ?)",
            (user_id, playlist_name)
        )
        connection.commit()
        
        # Get playlist id
        cursor.execute(
            "SELECT id FROM playlists WHERE user_id = ? AND name = ?",
            (user_id, playlist_name)
        )
        playlist = cursor.fetchone()
        
        if not playlist:
            return jsonify({'success': False, 'message': 'Failed to create playlist'})
        
        playlist_id = playlist['id']
        
        # Check if song already in playlist
        cursor.execute(
            "SELECT * FROM playlist_songs WHERE playlist_id = ? AND music_id = ?",
            (playlist_id, song_id)
        )
        if cursor.fetchone():
            return jsonify({'success': False, 'message': 'Song already in this playlist'})
        
        # Add song to playlist
        cursor.execute(
            "INSERT INTO playlist_songs (playlist_id, music_id) VALUES (?, ?)",
            (playlist_id, song_id)
        )
        connection.commit()
        
        return jsonify({'success': True, 'message': f'Added to playlist "{playlist_name}"'})
        
    except Exception as e:
        logger.error(f"Error adding to playlist: {e}")
        return jsonify({'success': False, 'message': str(e)})



# Favorites Page
@app.route('/favorites')
def favorites():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = str(session['user_id'])  # Convert to string to match TEXT type in database
    connection = music_system.get_database_connection()
    cursor = connection.cursor()

    # Get liked songs from liked_songs table
    cursor.execute("""
        SELECT m.* FROM music m
        JOIN liked_songs ls ON m.id = ls.music_id
        WHERE ls.user_id = ?
        ORDER BY ls.created_at DESC
    """, (user_id,))
    songs = cursor.fetchall()

    resp = make_response(render_template('favorites.html', songs=songs))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp



# Debug route to check playlists data
@app.route('/debug/playlists')
def debug_playlists():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'})
    
    try:
        session_user_id = session['user_id']
        user_id_str = str(session_user_id)
        
        connection = music_system.get_database_connection()
        cursor = connection.cursor()
        
        # Get all playlists
        cursor.execute("SELECT * FROM playlists")
        all_playlists = cursor.fetchall()
        
        # Get playlists for this user (as string)
        cursor.execute("SELECT * FROM playlists WHERE user_id = ?", (user_id_str,))
        user_playlists_str = cursor.fetchall()
        
        # Get playlists for this user (as int)
        cursor.execute("SELECT * FROM playlists WHERE user_id = ?", (session_user_id,))
        user_playlists_int = cursor.fetchall()
        
        return jsonify({
            'session_user_id': session_user_id,
            'session_user_id_type': type(session_user_id).__name__,
            'user_id_as_string': user_id_str,
            'all_playlists': [dict(p) for p in all_playlists],
            'user_playlists_with_string_query': [dict(p) for p in user_playlists_str],
            'user_playlists_with_int_query': [dict(p) for p in user_playlists_int]
        })
    except Exception as e:
        return jsonify({'error': str(e)})

# Playlists Page
@app.route('/playlists')
def playlists():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        user_id = str(session['user_id'])  # Convert to string to match TEXT type in database
        connection = music_system.get_database_connection()
        cursor = connection.cursor()

        # Fetch playlists created by the user
        cursor.execute("SELECT * FROM playlists WHERE user_id = ?", (user_id,))
        playlists = cursor.fetchall()

        resp = make_response(render_template('playlists.html', playlists=playlists))
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        resp.headers['Pragma'] = 'no-cache'
        return resp

    except Exception as e:
        logger.error(f"Error loading playlists: {e}")
        return render_template('playlists.html', playlists=[], message=str(e))

# View songs in a specific playlist
@app.route('/playlist/<int:playlist_id>')
def playlist_detail(playlist_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        connection = music_system.get_database_connection()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT m.*
            FROM playlist_songs ps
            JOIN music m ON ps.music_id = m.id
            WHERE ps.playlist_id = ?
        """, (playlist_id,))
        songs = cursor.fetchall()

        cursor.execute("SELECT name FROM playlists WHERE id = ?", (playlist_id,))
        playlist = cursor.fetchone()

        return render_template('playlist_detail.html',
                               playlist_name=playlist['name'] if playlist else "My Playlist",
                               songs=songs)

    except Exception as e:
        logger.error(f"Error loading playlist songs: {e}")
        return render_template('playlist_detail.html', songs=[], message=str(e))


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        fullname = request.form['fullname']
        email = request.form['email']
        password = request.form['password']

        hashed_password = generate_password_hash(password)

        try:
            connection = music_system.get_database_connection()
            cursor = connection.cursor()

            # Check if user already exists
            cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
            existing_user = cursor.fetchone()
            if existing_user:
                return render_template('signup.html', error=" Email already exists. Try logging in.")

            # Insert new user
            cursor.execute(
                "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                (fullname, email, hashed_password)
            )
            connection.commit()

            # Flash success message
            flash(" Your account has been created successfully. Please log in.")
            return redirect(url_for('login'))  # redirect to login page

        except sqlite3.Error as e:
            logger.error(f"Signup error: {e}")
            return render_template('signup.html', error="Something went wrong. Please try again.")

    return render_template('signup.html')



@app.route('/preferences', methods=['GET', 'POST'])
def preferences():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = str(session['user_id'])  # Convert to string to match TEXT type in database

    if request.method == 'POST':
        selected_genres = request.form.getlist('genres')

        connection = music_system.get_database_connection()
        cursor = connection.cursor()

        genre_placeholders = ','.join(['?'] * len(selected_genres))
        cursor.execute(f"SELECT id FROM music WHERE genre IN ({genre_placeholders})", selected_genres)
        songs = cursor.fetchall()

        for song in songs:
            music_system.record_user_interaction(user_id, song['id'], 'preference')

        return redirect(url_for('dashboard'))

    connection = music_system.get_database_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT DISTINCT genre FROM music")
    genres = [row[0] for row in cursor.fetchall()]
    
    return render_template('preferences.html', genres=genres)

from werkzeug.security import check_password_hash
from functools import wraps

# Admin required decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login'))
        
        # Check if user is admin
        connection = music_system.get_database_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT role FROM users WHERE id = ?", (session['user_id'],))
        user = cursor.fetchone()
        
        if not user or user['role'] != 'Admin':
            flash('Access denied. Admin privileges required.', 'error')
            return redirect(url_for('home'))
        
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Use music_system to get a database connection
        connection = music_system.get_database_connection()
        cursor = connection.cursor()

        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()

        if user and check_password_hash(user['password'], password):
            # Store session details
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['user_email'] = user['email']

            flash(" Login successful!", "success")
            return redirect(url_for('home'))
        else:
            flash(" Invalid email or password", "error")
            return redirect(url_for('login'))

    return render_template('login.html')


import random

@app.route('/home')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        connection = music_system.get_database_connection()
        cursor = connection.cursor()

        # Fetch all songs
        cursor.execute("SELECT * FROM music")
        songs = cursor.fetchall()

        # Randomize order of songs
        random.shuffle(songs)
        
        # Get user preferences for recommendations
        cursor.execute("""
            SELECT music_id FROM user_preferences 
            WHERE user_id = ? 
            ORDER BY preference_score DESC 
            LIMIT 5
        """, (session['user_id'],))
        user_prefs = cursor.fetchall()
        user_pref_ids = [pref['music_id'] for pref in user_prefs]
        
        # Get personalized recommendations
        recommended_songs = []
        if user_pref_ids:
            recommended_songs = music_system.calculate_similarities(user_pref_ids)
        
        # If no personalized recommendations, show popular songs
        if not recommended_songs:
            cursor.execute("""
                SELECT * FROM music 
                ORDER BY popularity_score DESC 
                LIMIT 4
            """)
            recommended_songs = cursor.fetchall()
        else:
            # Limit to 4 recommendations
            recommended_songs = recommended_songs[:4]
        
        # Check if user is admin
        cursor.execute("SELECT role FROM users WHERE id = ?", (session['user_id'],))
        user = cursor.fetchone()
        is_admin = user and user['role'] == 'Admin'

        return render_template('home.html', songs=songs, recommended_songs=recommended_songs, is_admin=is_admin)
    except Exception as e:
        logger.error(f"Error loading songs: {e}")
        return render_template('home.html', songs=[], recommended_songs=[], message=str(e), is_admin=False)


@app.route('/update_recommendation/<int:song_id>', methods=['POST'])
def update_recommendation(song_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    try:
        user_id = str(session['user_id'])  # Convert to string to match TEXT type in database
        connection = music_system.get_database_connection()
        cursor = connection.cursor()

        cursor.execute("""
            INSERT INTO listening_history (user_id, music_id, timestamp)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (user_id, song_id))
        connection.commit()

        music_system.record_user_interaction(user_id, song_id, 'play')

        cursor.execute("""
            SELECT DISTINCT m.*
            FROM music m
            JOIN listening_history h ON m.id = h.music_id
            WHERE h.user_id = ?
            ORDER BY h.timestamp DESC
            LIMIT 10
        """, (user_id,))
        recently_played_rows = cursor.fetchall()
        # Convert Row objects to dictionaries
        recently_played = [dict(row) for row in recently_played_rows]

        # Generate recommendations based on the currently playing song
        recommendations = music_system.calculate_similarities([song_id])

        cursor.close()

        return jsonify({
            'success': True,
            'recently_played': recently_played,
            'recommendations': recommendations
        }), 200

    except Exception as e:
        logger.error(f"Update recommendation error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/listen/<int:song_id>', methods=['POST'])
def listen(song_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        user_id = session['user_id']
        connection = music_system.get_database_connection()
        cursor = connection.cursor()

        cursor.execute(
            "INSERT INTO listening_history (user_id, music_id) VALUES (?, ?)",
            (user_id, song_id)
        )
        connection.commit()

        return jsonify({'message': 'Recorded'})
    except Exception as e:
        logger.error(f"Listen error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Admin Routes
@app.route('/admin/songs')
@admin_required
def admin_songs():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        connection = music_system.get_database_connection()
        cursor = connection.cursor()

        # Fetch all songs from music table
        cursor.execute("SELECT * FROM music ORDER BY created_at DESC")
        all_songs = cursor.fetchall()

        return render_template('admin_songs.html', songs=all_songs)

    except Exception as e:
        logger.error(f"Error loading songs: {e}")
        return render_template('admin_songs.html', songs=[], error=str(e))

@app.route('/admin/songs/add', methods=['GET', 'POST'])
@admin_required
def admin_add_song():
    """Add a new song"""
    if request.method == 'POST':
        try:
            title = request.form.get('title')
            artist = request.form.get('artist')
            album = request.form.get('album', '')
            genre = request.form.get('genre')
            year = request.form.get('year')
            duration = request.form.get('duration')
            audio_url = request.form.get('audio_url', '')
            features = request.form.get('features', '')
            
            # Validate required fields
            if not all([title, artist, genre]):
                flash('Title, Artist, and Genre are required!', 'error')
                return render_template('admin_add_song.html')
            
            connection = music_system.get_database_connection()
            cursor = connection.cursor()
            
            cursor.execute(
                """INSERT INTO music (title, artist, album, genre, year, duration, audio_url, features) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (title, artist, album, genre, int(year) if year else None, 
                 int(duration) if duration else None, audio_url, features)
            )
            connection.commit()
            
            # Rebuild feature matrix
            music_system.build_feature_matrix()
            
            flash(f'Successfully added song: {title}', 'success')
            return redirect(url_for('admin_songs'))
            
        except Exception as e:
            logger.error(f"Error adding song: {e}")
            flash(f"Error adding song: {str(e)}", 'error')
    
    return render_template('admin_add_song.html')

@app.route('/admin/songs/edit/<int:song_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_song(song_id):
    """Edit an existing song"""
    connection = music_system.get_database_connection()
    cursor = connection.cursor()
    
    if request.method == 'POST':
        try:
            title = request.form.get('title')
            artist = request.form.get('artist')
            album = request.form.get('album', '')
            genre = request.form.get('genre')
            year = request.form.get('year')
            duration = request.form.get('duration')
            audio_url = request.form.get('audio_url', '')
            features = request.form.get('features', '')
            
            # Validate required fields
            if not all([title, artist, genre]):
                flash('Title, Artist, and Genre are required!', 'error')
                return redirect(url_for('admin_edit_song', song_id=song_id))
            
            cursor.execute(
                """UPDATE music SET title=?, artist=?, album=?, genre=?, year=?, 
                   duration=?, audio_url=?, features=? WHERE id=?""",
                (title, artist, album, genre, int(year) if year else None,
                 int(duration) if duration else None, audio_url, features, song_id)
            )
            connection.commit()
            
            # Rebuild feature matrix
            music_system.build_feature_matrix()
            
            flash(f'Successfully updated song: {title}', 'success')
            return redirect(url_for('admin_songs'))
            
        except Exception as e:
            logger.error(f"Error updating song: {e}")
            flash(f"Error updating song: {str(e)}", 'error')
    
    # GET request - load song data
    cursor.execute("SELECT * FROM music WHERE id = ?", (song_id,))
    song = cursor.fetchone()
    
    if not song:
        flash('Song not found!', 'error')
        return redirect(url_for('admin_songs'))
    
    return render_template('admin_edit_song.html', song=song)

@app.route('/admin/songs/delete/<int:song_id>', methods=['POST'])
@admin_required
def admin_delete_song(song_id):
    """Delete a song"""
    try:
        connection = music_system.get_database_connection()
        cursor = connection.cursor()
        
        # Get song title for confirmation message
        cursor.execute("SELECT title FROM music WHERE id = ?", (song_id,))
        song = cursor.fetchone()
        
        if not song:
            flash('Song not found!', 'error')
            return redirect(url_for('admin_songs'))
        
        song_title = song['title']
        
        # Delete related records first (due to foreign keys)
        cursor.execute("DELETE FROM user_preferences WHERE music_id = ?", (song_id,))
        cursor.execute("DELETE FROM listening_history WHERE music_id = ?", (song_id,))
        cursor.execute("DELETE FROM liked_songs WHERE music_id = ?", (song_id,))
        cursor.execute("DELETE FROM playlist_songs WHERE music_id = ?", (song_id,))
        
        # Delete the song
        cursor.execute("DELETE FROM music WHERE id = ?", (song_id,))
        connection.commit()
        
        # Rebuild feature matrix
        music_system.build_feature_matrix()
        
        flash(f'Successfully deleted song: {song_title}', 'success')
        
    except Exception as e:
        logger.error(f"Error deleting song: {e}")
        flash(f"Error deleting song: {str(e)}", 'error')
    
    return redirect(url_for('admin_songs'))

@app.route('/admin/reload-songs', methods=['POST'])
@admin_required
def reload_songs_from_csv():
    """Reload all songs from CSV file"""
    try:
        import pandas as pd
        
        csv_path = os.path.join(os.path.dirname(__file__), 'Static', 'data', 'spotify_songs.csv')
        
        if not os.path.exists(csv_path):
            flash('CSV file not found!', 'error')
            return redirect(url_for('admin_songs'))
        
        # Read CSV
        df = pd.read_csv(csv_path, encoding='utf-8', on_bad_lines='skip')
        
        connection = music_system.get_database_connection()
        cursor = connection.cursor()
        
        # Clear existing songs
        cursor.execute("DELETE FROM music")
        connection.commit()
        
        # Insert songs
        inserted_count = 0
        for index, row in df.iterrows():
            try:
                title = str(row.get('track_name', 'Unknown'))[:255]
                artist = str(row.get('track_artist', 'Unknown'))[:255]
                album = str(row.get('track_album_name', ''))[:255] if pd.notna(row.get('track_album_name')) else ''
                genre = str(row.get('playlist_genre', ''))[:100] if pd.notna(row.get('playlist_genre')) else ''
                
                year = None
                release_date = row.get('track_album_release_date')
                if pd.notna(release_date):
                    try:
                        year = int(str(release_date)[:4])
                    except:
                        pass
                
                duration = None
                duration_ms = row.get('duration_ms')
                if pd.notna(duration_ms):
                    try:
                        duration = int(float(duration_ms) / 1000)
                    except:
                        pass
                
                features_list = []
                if pd.notna(row.get('playlist_subgenre')):
                    features_list.append(str(row['playlist_subgenre']))
                if pd.notna(row.get('danceability')):
                    features_list.append(f"danceability:{row['danceability']}")
                if pd.notna(row.get('energy')):
                    features_list.append(f"energy:{row['energy']}")
                
                features = ' '.join(features_list)[:500]
                
                cursor.execute(
                    """INSERT INTO music (title, artist, album, genre, year, duration, audio_url, features, popularity_score) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (title, artist, album, genre, year, duration, '', features, 0)
                )
                inserted_count += 1
            except:
                continue
        
        connection.commit()
        
        # Rebuild feature matrix
        music_system.build_feature_matrix()
        
        flash(f'Successfully reloaded {inserted_count} songs from CSV!', 'success')
        logger.info(f"Reloaded {inserted_count} songs from CSV")
        
    except Exception as e:
        logger.error(f"Error reloading songs: {e}")
        flash(f'Error reloading songs: {str(e)}', 'error')
    
    return redirect(url_for('admin_songs'))

@app.route('/')
def landing():
    return render_template('landing.html')

@app.route('/test')
def test_get_music():
    songs = music_system.get_all_music()
    logger.info(f"Test route - songs fetched: {len(songs)}")
    return jsonify(songs)
    

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'error': 'Endpoint not found'
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'error': 'Internal server error'
    }), 500

if __name__ == '__main__':
    logger.info("Starting Music Recommendation System API...")
    logger.info("Database: SQLite (music_recommendation.db)")
    logger.info("API will be available at: http://localhost:5000")
    # music_system.insert_sample_data()  # Commented out - use load_songs_from_csv.py instead
    ensure_admin_account()  # Ensure admin exists
    logger.info(" Admin account ready: email=admin@gmail.com, password=admin123, role=Admin")
    app.run(debug=True, host='0.0.0.0', port=5000)