import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# Try to get from env, else use the one from summary
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:yourpassword@localhost:5432/equisight")

async def fix_db():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        try:
            # Add the target_weights column
            await conn.execute(text("ALTER TABLE portfolios ADD COLUMN target_weights JSONB;"))
            print("Successfully added target_weights column to portfolios table.")
        except Exception as e:
            if "already exists" in str(e):
                print("Column already exists.")
            else:
                print(f"Error adding column: {e}")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(fix_db())
