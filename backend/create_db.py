import asyncio
import asyncpg

async def create_db():
    try:
        # Connect to the default 'postgres' database to create the new one
        conn = await asyncpg.connect('postgresql://postgres:yourpassword@localhost:5432/postgres')
        try:
            await conn.execute('CREATE DATABASE equisight')
            print('Database equisight created successfully!')
        except asyncpg.exceptions.DuplicateDatabaseError:
            print('Database already exists.')
        finally:
            await conn.close()
    except Exception as e:
        print(f'Error connecting: {e}')

if __name__ == "__main__":
    asyncio.run(create_db())
