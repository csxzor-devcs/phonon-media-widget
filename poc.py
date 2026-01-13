import asyncio
from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager

async def get_media_info():
    # 1. Get the session manager
    print("Connecting to Media Session Manager...")
    sessions = await GlobalSystemMediaTransportControlsSessionManager.request_async()

    # 2. Get the current session
    current_session = sessions.get_current_session()
    if not current_session:
        print("No active media session found.")
        return

    print(f"Source: {current_session.source_app_user_model_id}")

    # 3. Get media properties
    info = await current_session.try_get_media_properties_async()
    
    print("\n--- Now Playing ---")
    print(f"Title: {info.title}")
    print(f"Artist: {info.artist}")
    print(f"Album: {info.album_title}")
    print(f"Genres: {', '.join(info.genres)}")

    # 4. Check controls capability
    controls = current_session.transport_controls
    print("\n--- Controls Available ---")
    print(f"Play/Pause: {controls.is_play_enabled}/{controls.is_pause_enabled}")
    print(f"Next/Prev: {controls.is_next_enabled}/{controls.is_previous_enabled}")

if __name__ == '__main__':
    try:
        asyncio.run(get_media_info())
    except Exception as e:
        print(f"Error: {e}")
