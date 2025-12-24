import asyncio
import websockets
import json

async def test_video_stream():
    uri = "ws://localhost:8000/ws/video"
    print(f"Connecting to {uri}...")
    try:
        async with websockets.connect(uri) as websocket:
            print("[+] Connected to Video WebSocket!")
            
            # Try to receive a few frames
            count = 0
            try:
                while count < 5:
                    message = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    print(f"    Received frame {count+1}, size: {len(message)} bytes")
                    count += 1
                print("[SUCCESS] Video stream is transmitting data.")
            except asyncio.TimeoutError:
                print("[-] Timeout waiting for frame data.")
    except Exception as e:
        print(f"[-] Connection failed: {e}")

async def test_status_stream():
    uri = "ws://localhost:8000/ws/status"
    print(f"Connecting to {uri}...")
    try:
        async with websockets.connect(uri) as websocket:
            print("[+] Connected to Status WebSocket!")
            
            # Try to receive a status update
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                data = json.loads(message)
                print(f"    Received status: {data}")
                print("[SUCCESS] Status stream is working.")
            except asyncio.TimeoutError:
                print("[-] Timeout waiting for status data.")
    except Exception as e:
        print(f"[-] Connection failed: {e}")

async def main():
    print("--- ARGUS WebSocket Diagnostic ---")
    await test_video_stream()
    print("-" * 30)
    await test_status_stream()

if __name__ == "__main__":
    asyncio.run(main())
