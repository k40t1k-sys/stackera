# STACKERA BACKEND ASSIGNMENT

#### Objective

Build a Python application that:

● Connects to Binance’s public WebSocket API to listen to live crypto prices.

● Runs its own WebSocket server that broadcasts these prices to any
connected clients in real-time
Requirements

1. Binance Listener
Use the Binance WebSocket endpoint:
wss://stream.binance.com:9443/ws/btcusdt@ticker
Continuously receive updates for BTC/USDT (and optionally ETH/USDT).
Extract and store:
Symbol (e.g., BTCUSDT)
Last price
24h change percentage
Timestamp

2. Local WebSocket Server
Build your own WebSocket server using FastAPI, Starlette, or websockets
library.
The server should:
Allow multiple clients to connect (e.g., from ws://localhost:8000/ws).
Continuously broadcast the latest Binance price updates to all
connected clients.
Handle disconnections gracefully.

3. Expected Flow
Binance WebSocket ---> Your Listener ---> Your Local WebSocket Server --->
Clients

Bonus Features (Optional)
Support multiple pairs (BTC/USDT, ETH/USDT, BNB/USDT).
Add a REST API endpoint (GET /price) returning the latest price as JSON.
Add rate limiting or connection limits.
Use asyncio.Queue or Broadcast channels to manage messages.
Containerize using Docker.