import asyncio
import uuid
import pandas as pd
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select
from app.core.db import create_all_tables
from app.models.user import User
from app.models.portfolio import Portfolio
from app.models.holding import Holding

async def seed_data():
    # Ensure tables are created first since the app crash might have prevented it
    await create_all_tables()

    # Direct connection to the now-existing equisight database
    engine = create_async_engine('postgresql+asyncpg://postgres:yourpassword@localhost:5432/equisight')
    SessionLocal = async_sessionmaker(engine)
    
    async with SessionLocal() as session:
        # Seed Test User
        test_user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        user = await session.get(User, test_user_id)
        if not user:
            new_user = User(
                id=test_user_id,
                name="Test User",
                email="test@example.com"
            )
            session.add(new_user)
            await session.commit()
            print("Test user seeded successfully.")
        else:
            print("Test user already exists.")

        # Seed Test Portfolio
        test_portfolio_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        portfolio = await session.get(Portfolio, test_portfolio_id)
        if not portfolio:
            new_portfolio = Portfolio(
                id=test_portfolio_id,
                user_id=test_user_id,
                name="Test Portfolio",
                target_return=0.15,
                target_risk=0.10
            )
            session.add(new_portfolio)
            await session.commit()
            print("Test portfolio seeded successfully.")
        else:
            print("Test portfolio already exists.")

        # Check if Holdings exist for this Portfolio
        existing_holdings_query = await session.execute(
            select(Holding).where(Holding.portfolio_id == test_portfolio_id)
        )
        existing_holdings = existing_holdings_query.scalars().all()
        
        if not existing_holdings:
            print("Seeding dummy_holdings.csv into the portfolio...")
            df = pd.read_csv("dummy_holdings.csv")
            new_holdings = []
            for _, row in df.iterrows():
                holding = Holding(
                    portfolio_id=test_portfolio_id,
                    asset_symbol=row["asset_symbol"],
                    asset_type=row["asset_type"],
                    quantity=float(row["quantity"]),
                    average_buy_price=float(row["average_buy_price"])
                )
                new_holdings.append(holding)
            
            session.add_all(new_holdings)
            await session.commit()
            print(f"Successfully seeded {len(new_holdings)} holdings from CSV.")
        else:
            print("Holdings already exist for this portfolio.")

        print("\n" + "="*50)
        print("SEEDING COMPLETE")
        print("Use the following ID for testing in Swagger UI:")
        print(f"portfolio_id : {test_portfolio_id}")
        print("="*50 + "\n")
            
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(seed_data())
