#!/usr/bin/env python3
"""
Database Migration Script
Creates/updates database tables with new sharing fields
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from loguru import logger
from app.core.database import engine, init_db


async def check_column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table"""
    async with engine.connect() as conn:
        # SQLite specific query
        result = await conn.execute(
            text(f"PRAGMA table_info({table_name})")
        )
        columns = [row[1] for row in result.fetchall()]
        return column_name in columns


async def migrate():
    """Run database migration"""
    logger.info("🔄 Starting database migration...")
    
    try:
        # Initialize database (creates tables if they don't exist)
        await init_db()
        logger.info("✅ Base tables initialized")
        
        # Check if migration is needed
        needs_migration = False
        
        async with engine.connect() as conn:
            # Check if documents table exists
            result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='documents'")
            )
            table_exists = result.fetchone() is not None
            
            if not table_exists:
                logger.info("ℹ️  Documents table doesn't exist yet, will be created")
                needs_migration = False
            else:
                # Check if new columns exist
                has_share_token = await check_column_exists('documents', 'share_token')
                has_share_expires = await check_column_exists('documents', 'share_expires_at')
                has_share_access = await check_column_exists('documents', 'share_access_level')
                
                if not (has_share_token and has_share_expires and has_share_access):
                    needs_migration = True
                    logger.warning("⚠️  Sharing columns missing, migration needed")
                else:
                    logger.info("✅ All sharing columns already exist")
        
        if needs_migration:
            logger.info("📝 Adding sharing columns to documents table...")
            
            async with engine.begin() as conn:
                # Add columns if they don't exist (SQLite safe approach)
                if not await check_column_exists('documents', 'share_token'):
                    await conn.execute(
                        text("ALTER TABLE documents ADD COLUMN share_token VARCHAR")
                    )
                    await conn.execute(
                        text("CREATE UNIQUE INDEX IF NOT EXISTS ix_documents_share_token ON documents(share_token)")
                    )
                    logger.info("  ✅ Added share_token column")
                
                if not await check_column_exists('documents', 'share_expires_at'):
                    await conn.execute(
                        text("ALTER TABLE documents ADD COLUMN share_expires_at DATETIME")
                    )
                    logger.info("  ✅ Added share_expires_at column")
                
                if not await check_column_exists('documents', 'share_access_level'):
                    await conn.execute(
                        text("ALTER TABLE documents ADD COLUMN share_access_level VARCHAR DEFAULT 'VIEW'")
                    )
                    logger.info("  ✅ Added share_access_level column")
            
            logger.info("✅ Migration completed successfully")
        else:
            # Just recreate all tables based on current models
            async with engine.begin() as conn:
                from app.core.database import Base
                await conn.run_sync(Base.metadata.create_all)
            logger.info("✅ Tables created/updated from models")
        
        logger.info("🎉 Database is up to date!")
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(migrate())
