import os
import uuid
import requests
import base64
from flask import Flask, request, redirect, render_template, session
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = str(uuid.uuid4())
app.config['SESSION_COOKIE_NAME'] = 'spotify-login-session'

CLIENT_ID = os.getenv('SPOTIPY_CLIENT_ID')
CLIENT_SECRET = os.getenv('SPOTIPY_CLIENT_SECRET')
REDIRECT_URI = os.getenv('SPOTIPY_REDIRECT_URI')

SCOPE = 'playlist-modify-public playlist-modify-private ugc-image-upload'

def create_spotify_oauth():
    return SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE,
        show_dialog=True
    )

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login')
def login():
    auth_url = create_spotify_oauth().get_authorize_url()
    print("Spotify Auth URL:", auth_url)
    return render_template('login.html', auth_url=auth_url)

@app.route('/callback')
def callback():
    sp_oauth = create_spotify_oauth()
    code = request.args.get('code')

    if code:
        token_info = sp_oauth.get_access_token(code)
        session['token_info'] = token_info
        return redirect('/copy')
    else:
        return "Authorization failed."
    
@app.route('/copy', methods=['GET', 'POST'])
def copy():
    token_info = session.get('token_info', None)
    if not token_info or not create_spotify_oauth().validate_token(token_info):
        return redirect('/login')

    sp = Spotify(auth=token_info['access_token'])

    if request.method == 'POST':
        playlist_url = request.form['playlist_url']
        playlist_id = playlist_url.split("/")[-1].split("?")[0]

        # Get original playlist data
        original = sp.playlist(playlist_id)
        name = "Copy of " + original['name']
        description = original.get('description', '')
        public = original.get('public', False)

        # Create new playlist
        user_id = sp.current_user()['id']
        new_playlist = sp.user_playlist_create(user=user_id, name=name, public=public, description=description)

        # Fetch ALL tracks using pagination
        def get_all_tracks(sp, playlist_id):
            tracks = []
            offset = 0
            while True:
                response = sp.playlist_items(playlist_id, offset=offset, limit=100)
                items = response['items']
                if not items:
                    break
                tracks.extend(items)
                offset += 100
            return tracks

        all_tracks = get_all_tracks(sp, playlist_id)
        track_uris = [item["track"]["uri"] for item in all_tracks if item["track"]]

        # Add tracks in chunks of 100
        for i in range(0, len(track_uris), 100):
            sp.playlist_add_items(new_playlist["id"], track_uris[i:i+100])

        # Copy cover image
        images = original.get('images', [])
        if images:
            import requests, base64, time
            img_url = images[0]['url']
            img_data = requests.get(img_url).content
            encoded_img = base64.b64encode(img_data).decode('utf-8')
            sp.playlist_upload_cover_image(new_playlist['id'], encoded_img)
            time.sleep(2)

        # Fetch the new playlist again to get cover image URL
        new_playlist_data = sp.playlist(new_playlist['id'])
        new_cover_url = new_playlist_data['images'][0]['url'] if new_playlist_data['images'] else None

        return render_template('copy.html', name=new_playlist['name'], cover_url=new_cover_url)

    return render_template('copy.html', name=None)



@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)