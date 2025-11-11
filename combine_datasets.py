import pandas as pd

# Load both datasets
lyrics_df = pd.read_csv("static/data/spotify_millsongdata.csv")
tracks_df = pd.read_csv("static/data/spotify_songs.csv")

# Clean titles for merging (lowercase and strip whitespace)
lyrics_df['track_name_clean'] = lyrics_df['song'].str.lower().str.strip()
tracks_df['track_name_clean'] = tracks_df['track_name'].str.lower().str.strip()

# Optional: Also clean artist names to improve matching
lyrics_df['artist_clean'] = lyrics_df['artist'].str.lower().str.strip()
tracks_df['artist_clean'] = tracks_df['track_artist'].str.lower().str.strip()

# Merge on cleaned song name and artist
combined_df = pd.merge(tracks_df, lyrics_df, how='inner', 
                       left_on=['track_name_clean', 'artist_clean'], 
                       right_on=['track_name_clean', 'artist_clean'])

# Save to new CSV
combined_df.to_csv("static/data/combined_dataset.csv", index=False)

print("Datasets combined successfully. Total records:", len(combined_df))
