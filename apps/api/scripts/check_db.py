import asyncio
from sqlalchemy import text
from app.core.database import AsyncSessionLocal
from app.models.document import Document

async def check_db():
    try:
        async with AsyncSessionLocal() as session:
            print("Connecting to DB...")
            result = await session.execute(text("SELECT 1"))
            print(f"Connection test: {result.scalar()}")
            
            print("Listing documents...")
            result = await session.execute(text("SELECT id, name FROM documents LIMIT 5"))
            docs = result.fetchall()
            print(f"Found {len(docs)} documents:")
            for doc in docs:
                print(f"- {doc.name} ({doc.id})")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_db())
