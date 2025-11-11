import sqlite3

conn = sqlite3.connect('music_recommendation.db')
cursor = conn.cursor()

genres = ['pop', 'rock', 'rap', 'r&b', 'latin', 'edm']
print('\nSample Songs from Each Genre:')
print('=' * 70)

for genre in genres:
    cursor.execute('SELECT title, artist FROM music WHERE genre = ? LIMIT 3', (genre,))
    songs = cursor.fetchall()
    print(f'\n{genre.upper()}:')
    for s in songs:
        title = s[0][:40]
        artist = s[1][:25]
        print(f'  • {title:40} - {artist}')

print('=' * 70)
cursor.execute('SELECT COUNT(*) FROM music')
print(f'\nTotal Songs in Database: {cursor.fetchone()[0]}')
print('=' * 70)
