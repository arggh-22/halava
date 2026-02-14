
    @classmethod
    async def get_by_customer_and_worker(cls, customer_id: int, worker_id: int) -> Optional['WorkersAndAbs'] | None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute(
                'SELECT * FROM workers_and_abs WHERE worker_id = ? AND abs_id IN (SELECT id FROM abs WHERE customer_id = ?)',
                [worker_id, customer_id])
            records = await cursor.fetchall()
            await cursor.close()
            if records:
                # Return the latest one if multiple exist? Or handle multiple chats?
                # Assuming one active chat per customer-worker pair for simplicity, or just return first found.
                # The logic in anonymous_chat.py suggests we look up by worker_id and customer_id context.
                # But here let's just reverse the generic get logic.
                pass
            return None
        finally:
            await conn.close()
