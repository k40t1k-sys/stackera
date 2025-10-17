import asyncio
import websockets

async def main():
    uri = "ws://localhost:8000/ws"
    async with websockets.connect(uri) as ws:
        async for msg in ws:
            print(msg)

if __name__ == "__main__":
    asyncio.run(main())
