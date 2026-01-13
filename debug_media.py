import asyncio
from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager

async def debug_sessions():
    print("Requesting Session Manager...")
    try:
        manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
    except Exception as e:
        print(f"Failed to get manager: {e}")
        return

    # 1. Check Current Session (What Windows thinks is active)
    print("\n--- Current Session ---")
    current = manager.get_current_session()
    if current:
        print(f"App ID: {current.source_app_user_model_id}")
        try:
            info = await current.try_get_media_properties_async()
            print(f"Title: {info.title}")
            print(f"Artist: {info.artist}")
        except Exception as e:
            print(f"Error fetching props: {e}")
    else:
        print("None")

    # 2. List ALL Sessions
    print("\n--- All Sessions ---")
    sessions = manager.get_sessions()
    print(f"Found {len(sessions)} sessions.")
    
    for i, session in enumerate(sessions):
        print(f"\n[Session {i}]")
        print(f"App ID: {session.source_app_user_model_id}")
        
        # Playback Status
        try:
            playback = session.get_playback_info()
            # 4=Playing, 5=Paused, 2=Stopped (Closed is 0)
            print(f"Playback Status: {playback.playback_status}") 
            print(f"Controls Type: {playback.playback_type}") # 1=Music, 2=Video, 3=Image
        except Exception as e:
            print(f"Error fetching playback info: {e}")

        # Properties
        try:
            props = await session.try_get_media_properties_async()
            print(f"Title: {props.title}")
            print(f"Artist: {props.artist}")
        except Exception as e:
            print(f"Error fetching props: {e}")
            
        # Timeline
        try:
            timeline = session.get_timeline_properties()
            print(f"Position: {timeline.position}") # TimeSpan
            print(f"Last Updated: {getattr(timeline, 'last_updated_time', 'N/A')}")
            print(f"Min Seek: {timeline.min_seek_time}")
            print(f"Max Seek: {timeline.max_seek_time}")
            
            # Poll for 5 seconds to see if it changes
            import time
            print("Polling position for 3 seconds...")
            for _ in range(3):
                time.sleep(1)
                t_poll = session.get_timeline_properties()
                print(f"  Pos: {t_poll.position}")
                
        except Exception as e:
            print(f"Error fetching timeline: {e}")

if __name__ == "__main__":
    asyncio.run(debug_sessions())
