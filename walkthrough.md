# Walkthrough: Web App Notification Center

I have successfully implemented the Web App Notification Center, effectively moving non-urgent notifications from direct chat messages to a dedicated interface.

## 🚀 Key Changes

1.  **Database Upgrade**: Enabled **WAL Mode** for `database.db` to allow simultaneous access by the Bot and the API.
2.  **New API Service**: Created a FastAPI application (`api/`) using **Tortoise ORM** to serve notifications.
3.  **Bot Integration**: Updated `notification_helper.py` and `worker_responses.py` to:
    *   **Log** standard notifications (like "New Response") to the database.
    *   **Smart Notifications**: The bot now manages a single "New Notifications" message in the chat, deleting old ones to prevent spam.
    *   **Push** only critical notifications (Payment, Ban) to the chat.
4.  **Frontend**: Scaffolding a **React + Vite** application (`frontend/`) using **@twa-dev/sdk** for Telegram Web App integration. Requests are secured via `Authorization: tma <initData>`.

## 🛠️ How to Run

You now have three components to run:

### 1. The Bot (Existing)
Run as usual. It will now log response notifications to the DB instead of spamming.
```bash
python main.py
```

### 2. The API (New)
The API serves the frontend and handles database queries.
```bash
# From root directory
uvicorn api.main:app --reload --port 8000
```
*   Docs available at: http://localhost:8000/docs

### 3. The Frontend (New)
The Web App interface.
```bash
cd frontend
npm run dev
```
*   Accessible at: http://localhost:5173

### 4. Cloudflare Tunnel (Optional)
If you are using Cloudflare Tunnel, I have configured `frontend/vite.config.ts` to allow the tunnel host and proxy API requests.
1.  Update `frontend/.env` with your tunnel URL:
    ```
    VITE_TUNNEL_URL=your-tunnel-url.trycloudflare.com
    ```
2.  The API requests like `/api/notifications` will be proxied by Vite to `http://127.0.0.1:8000` automatically.


I created and ran a verification script `verify_notification.py` which:
1.  Simulated the Bot creating a "New Response" notification (using `aiosqlite`).
2.  Verified the API could read this notification (using `tortoise-orm`).
3.  **Result**: `Verification SUCCESS!`

## 📂 File Structure
*   `api/` - FastAPI backend.
*   `frontend/` - React frontend.
*   `app/untils/notification_helper.py` - Updated notification logic.
*   `app/data/database/models.py` - Updated with `Notification` model.

## ⚠️ Important Notes
*   **Dependencies**: Ensure you run `pip install -r api/requirements.txt` and `npm install` in `frontend/`.
*   **Telegram Web App**: To fully test the frontend as a Web App, you will need to configure a Menu Button in @BotFather to point to your frontend URL (tunneled via ngrok if local).
