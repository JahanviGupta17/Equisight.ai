import asyncio
import sqlalchemy.ext.asyncio as sa_async
import sqlalchemy

async def drop_table():
    engine = sa_async.create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5432/equisight')
    async with engine.begin() as conn:
        await conn.execute(sqlalchemy.text('DROP TABLE IF EXISTS user_preferences CASCADE;'))
    print('Table dropped.')

if __name__ == '__main__':
    asyncio.run(drop_table())
