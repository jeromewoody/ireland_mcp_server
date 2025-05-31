#!/usr/bin/env python3
"""
Comic Book Database MCP Server
A Model Context Protocol server for searching and analyzing comic book collections.
"""

import sqlite3
import json
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from fuzzywuzzy import fuzz, process
from mcp.server.fastmcp import FastMCP

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ComicResult:
    """Data class for comic search results"""
    id: int
    title: str
    series: str
    publisher: str
    year: int
    creators: List[Dict[str, str]]
    characters: List[str]
    teams: List[str]
    file_path: str
    match_confidence: float = 100.0


class DatabaseManager:
    """Manages SQLite database connections and operations"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._connection = None
    
    def get_connection(self) -> sqlite3.Connection:
        """Get database connection with proper configuration"""
        if self._connection is None:
            self._connection = sqlite3.connect(self.db_path)
            self._connection.row_factory = sqlite3.Row
            # Enable foreign keys
            self._connection.execute("PRAGMA foreign_keys = ON")
        return self._connection
    
    def execute_query(self, query: str, params: tuple = ()) -> List[sqlite3.Row]:
        """Execute a SELECT query and return results"""
        try:
            conn = self.get_connection()
            cursor = conn.execute(query, params)
            return cursor.fetchall()
        except sqlite3.Error as e:
            logger.error(f"Database query error: {e}")
            logger.error(f"Query: {query}")
            logger.error(f"Params: {params}")
            raise
    
    def close(self):
        """Close database connection"""
        if self._connection:
            self._connection.close()
            self._connection = None


class SearchUtils:
    """Utility functions for search operations"""
    
    @staticmethod
    def normalize_name(name: str) -> str:
        """Normalize name for consistent matching"""
        if not name:
            return ""
        return name.strip().upper()
    
    @staticmethod
    def fuzzy_match_name(query: str, target: str, threshold: int = 80) -> bool:
        """Check if query matches target with fuzzy matching"""
        if not query or not target:
            return False
        ratio = fuzz.ratio(SearchUtils.normalize_name(query), SearchUtils.normalize_name(target))
        return ratio >= threshold
    
    @staticmethod
    def get_fuzzy_matches(query: str, candidates: List[str], threshold: int = 80) -> List[Tuple[str, int]]:
        """Get list of candidates that fuzzy match the query"""
        if not query or not candidates:
            return []
        
        matches = process.extract(query, candidates, scorer=fuzz.ratio, limit=None)
        return [(match[0], match[1]) for match in matches if match[1] >= threshold]
    
    @staticmethod
    def escape_sql_like(text: str) -> str:
        """Escape special characters for SQL LIKE queries"""
        if not text:
            return ""
        return text.replace("%", "\\%").replace("_", "\\_").replace("'", "''")
    
    @staticmethod
    def build_where_clause(criteria: Dict[str, Any]) -> Tuple[str, List]:
        """Build SQL WHERE clause from criteria dictionary"""
        conditions = []
        params = []
        
        for key, value in criteria.items():
            if value is None:
                continue
                
            if key in ['title', 'series', 'publisher']:
                conditions.append(f"UPPER(c.{key}) LIKE UPPER(?)")
                params.append(f"%{SearchUtils.escape_sql_like(str(value))}%")
            elif key == 'year':
                conditions.append(f"c.year = ?")
                params.append(value)
            elif key == 'start_year':
                conditions.append(f"c.year >= ?")
                params.append(value)
            elif key == 'end_year':
                conditions.append(f"c.year <= ?")
                params.append(value)
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        return where_clause, params


class ComicSearchTools:
    """MCP tools for searching comic database"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    def _build_comic_result(self, row: sqlite3.Row, confidence: float = 100.0) -> ComicResult:
        """Build ComicResult from database row"""
        return ComicResult(
            id=row['id'],
            title=row['title'] or '',
            series=row['series'] or '',
            publisher=row['publisher'] or '',
            year=row['year'] or 0,
            creators=self._get_creators(row['id']),
            characters=self._get_characters(row['id']),
            teams=self._get_teams(row['id']),
            file_path=row['file_path'] or '',
            match_confidence=confidence
        )
    
    def _get_creators(self, comic_id: int) -> List[Dict[str, str]]:
        """Get creators for a comic"""
        query = """
        SELECT cr.name, cc.role
        FROM comic_creators cc
        JOIN creators cr ON cc.creator_id = cr.id
        WHERE cc.comic_id = ?
        ORDER BY cc.role, cr.name
        """
        rows = self.db.execute_query(query, (comic_id,))
        return [{"name": row['name'], "role": row['role']} for row in rows]
    
    def _get_characters(self, comic_id: int) -> List[str]:
        """Get characters for a comic"""
        query = """
        SELECT ch.name
        FROM comic_characters cc
        JOIN characters ch ON cc.character_id = ch.id
        WHERE cc.comic_id = ?
        ORDER BY ch.name
        """
        rows = self.db.execute_query(query, (comic_id,))
        return [row['name'] for row in rows]
    
    def _get_teams(self, comic_id: int) -> List[str]:
        """Get teams for a comic"""
        query = """
        SELECT t.name
        FROM comic_teams ct
        JOIN teams t ON ct.team_id = t.id
        WHERE ct.comic_id = ?
        ORDER BY t.name
        """
        rows = self.db.execute_query(query, (comic_id,))
        return [row['name'] for row in rows]
    
    def search_by_title(self, title: str, exact_match: bool = False) -> Dict[str, Any]:
        """Search for comics by title"""
        start_time = time.time()
        
        if exact_match:
            query = "SELECT * FROM comics WHERE UPPER(title) = UPPER(?) ORDER BY year, title"
            params = (title,)
        else:
            query = "SELECT * FROM comics WHERE UPPER(title) LIKE UPPER(?) ORDER BY year, title"
            params = (f"%{SearchUtils.escape_sql_like(title)}%",)
        
        rows = self.db.execute_query(query, params)
        results = [self._build_comic_result(row) for row in rows]
        
        # If no exact matches and fuzzy matching is enabled, try fuzzy search
        if not results and not exact_match:
            all_titles_query = "SELECT id, title FROM comics WHERE title IS NOT NULL"
            all_titles = self.db.execute_query(all_titles_query)
            
            title_dict = {row['title']: row['id'] for row in all_titles}
            fuzzy_matches = SearchUtils.get_fuzzy_matches(title, list(title_dict.keys()), 70)
            
            if fuzzy_matches:
                fuzzy_ids = [title_dict[match[0]] for match in fuzzy_matches]
                placeholders = ','.join('?' * len(fuzzy_ids))
                fuzzy_query = f"SELECT * FROM comics WHERE id IN ({placeholders}) ORDER BY year, title"
                fuzzy_rows = self.db.execute_query(fuzzy_query, fuzzy_ids)
                
                # Map confidence scores
                confidence_map = {title_dict[match[0]]: match[1] for match in fuzzy_matches}
                results = [self._build_comic_result(row, confidence_map.get(row['id'], 70)) 
                          for row in fuzzy_rows]
        
        return {
            "results": [result.__dict__ for result in results],
            "metadata": {
                "query_time": time.time() - start_time,
                "result_count": len(results),
                "search_terms": {"title": title, "exact_match": exact_match},
                "fuzzy_matches_used": not exact_match and any(r.match_confidence < 100 for r in results)
            }
        }
    
    def search_by_series(self, series: str, publisher: Optional[str] = None, exact_match: bool = False) -> Dict[str, Any]:
        """Search for comics by series name"""
        start_time = time.time()
        
        conditions = []
        params = []
        
        if exact_match:
            conditions.append("UPPER(series) = UPPER(?)")
            params.append(series)
        else:
            conditions.append("UPPER(series) LIKE UPPER(?)")
            params.append(f"%{SearchUtils.escape_sql_like(series)}%")
        
        if publisher:
            conditions.append("UPPER(publisher) LIKE UPPER(?)")
            params.append(f"%{SearchUtils.escape_sql_like(publisher)}%")
        
        where_clause = " AND ".join(conditions)
        query = f"SELECT * FROM comics WHERE {where_clause} ORDER BY series, number, year"
        
        rows = self.db.execute_query(query, params)
        results = [self._build_comic_result(row) for row in rows]
        
        return {
            "results": [result.__dict__ for result in results],
            "metadata": {
                "query_time": time.time() - start_time,
                "result_count": len(results),
                "search_terms": {"series": series, "publisher": publisher, "exact_match": exact_match},
                "fuzzy_matches_used": False
            }
        }
    
    def search_by_character(self, character_name: str, include_teams: bool = True) -> Dict[str, Any]:
        """Find comics featuring specific characters"""
        start_time = time.time()
        
        # Search for character directly
        query = """
        SELECT DISTINCT c.*
        FROM comics c
        JOIN comic_characters cc ON c.id = cc.comic_id
        JOIN characters ch ON cc.character_id = ch.id
        WHERE UPPER(ch.name) LIKE UPPER(?)
        """
        params = [f"%{SearchUtils.escape_sql_like(character_name)}%"]
        
        # If including teams, also search team associations
        if include_teams:
            query += """
            UNION
            SELECT DISTINCT c.*
            FROM comics c
            JOIN comic_teams ct ON c.id = ct.comic_id
            JOIN teams t ON ct.team_id = t.id
            WHERE UPPER(t.name) LIKE UPPER(?)
            """
            params.append(f"%{SearchUtils.escape_sql_like(character_name)}%")
        
        query += " ORDER BY year, title"
        
        rows = self.db.execute_query(query, params)
        results = [self._build_comic_result(row) for row in rows]
        
        return {
            "results": [result.__dict__ for result in results],
            "metadata": {
                "query_time": time.time() - start_time,
                "result_count": len(results),
                "search_terms": {"character_name": character_name, "include_teams": include_teams},
                "fuzzy_matches_used": False
            }
        }
    
    def search_by_team(self, team_name: str) -> Dict[str, Any]:
        """Find comics featuring specific teams"""
        start_time = time.time()
        
        query = """
        SELECT DISTINCT c.*
        FROM comics c
        JOIN comic_teams ct ON c.id = ct.comic_id
        JOIN teams t ON ct.team_id = t.id
        WHERE UPPER(t.name) LIKE UPPER(?)
        ORDER BY c.year, c.title
        """
        params = (f"%{SearchUtils.escape_sql_like(team_name)}%",)
        
        rows = self.db.execute_query(query, params)
        results = [self._build_comic_result(row) for row in rows]
        
        return {
            "results": [result.__dict__ for result in results],
            "metadata": {
                "query_time": time.time() - start_time,
                "result_count": len(results),
                "search_terms": {"team_name": team_name},
                "fuzzy_matches_used": False
            }
        }
    
    def search_by_creator(self, creator_name: str, role: Optional[str] = None, exact_match: bool = False) -> Dict[str, Any]:
        """Find comics by creator"""
        start_time = time.time()
        
        conditions = []
        params = []
        
        if exact_match:
            conditions.append("UPPER(cr.name) = UPPER(?)")
            params.append(creator_name)
        else:
            conditions.append("UPPER(cr.name) LIKE UPPER(?)")
            params.append(f"%{SearchUtils.escape_sql_like(creator_name)}%")
        
        if role:
            conditions.append("UPPER(cc.role) = UPPER(?)")
            params.append(role)
        
        where_clause = " AND ".join(conditions)
        
        query = f"""
        SELECT DISTINCT c.*
        FROM comics c
        JOIN comic_creators cc ON c.id = cc.comic_id
        JOIN creators cr ON cc.creator_id = cr.id
        WHERE {where_clause}
        ORDER BY c.year, c.title
        """
        
        rows = self.db.execute_query(query, params)
        results = [self._build_comic_result(row) for row in rows]
        
        return {
            "results": [result.__dict__ for result in results],
            "metadata": {
                "query_time": time.time() - start_time,
                "result_count": len(results),
                "search_terms": {"creator_name": creator_name, "role": role, "exact_match": exact_match},
                "fuzzy_matches_used": False
            }
        }
    
    def search_by_event(self, event_name: str) -> Dict[str, Any]:
        """Find comics related to specific events or story arcs"""
        start_time = time.time()
        
        query = """
        SELECT * FROM comics
        WHERE UPPER(story_arc) LIKE UPPER(?)
        OR UPPER(title) LIKE UPPER(?)
        OR UPPER(summary) LIKE UPPER(?)
        ORDER BY year, title
        """
        search_term = f"%{SearchUtils.escape_sql_like(event_name)}%"
        params = (search_term, search_term, search_term)
        
        rows = self.db.execute_query(query, params)
        results = [self._build_comic_result(row) for row in rows]
        
        return {
            "results": [result.__dict__ for result in results],
            "metadata": {
                "query_time": time.time() - start_time,
                "result_count": len(results),
                "search_terms": {"event_name": event_name},
                "fuzzy_matches_used": False
            }
        }
    
    def search_by_year(self, year: Optional[int] = None, start_year: Optional[int] = None, 
                      end_year: Optional[int] = None) -> Dict[str, Any]:
        """Find comics published in specific year or year range"""
        start_time = time.time()
        
        conditions = []
        params = []
        
        if year:
            conditions.append("year = ?")
            params.append(year)
        else:
            if start_year:
                conditions.append("year >= ?")
                params.append(start_year)
            if end_year:
                conditions.append("year <= ?")
                params.append(end_year)
        
        if not conditions:
            raise ValueError("Must specify either year or start_year/end_year")
        
        where_clause = " AND ".join(conditions)
        query = f"SELECT * FROM comics WHERE {where_clause} ORDER BY year, title"
        
        rows = self.db.execute_query(query, params)
        results = [self._build_comic_result(row) for row in rows]
        
        return {
            "results": [result.__dict__ for result in results],
            "metadata": {
                "query_time": time.time() - start_time,
                "result_count": len(results),
                "search_terms": {"year": year, "start_year": start_year, "end_year": end_year},
                "fuzzy_matches_used": False
            }
        }
    
    def find_creator_collaborations(self, creator_name: str, collaboration_type: Optional[str] = None) -> Dict[str, Any]:
        """Find relationships between creators"""
        start_time = time.time()
        
        # Base query to find collaborators
        query = """
        SELECT DISTINCT c2.name as collaborator_name, cc2.role, COUNT(*) as collaboration_count
        FROM comic_creators cc1
        JOIN comic_creators cc2 ON cc1.comic_id = cc2.comic_id
        JOIN creators c1 ON cc1.creator_id = c1.id
        JOIN creators c2 ON cc2.creator_id = c2.id
        WHERE UPPER(c1.name) LIKE UPPER(?)
        AND c1.id != c2.id
        """
        params = [f"%{SearchUtils.escape_sql_like(creator_name)}%"]
        
        if collaboration_type:
            query += " AND UPPER(cc2.role) = UPPER(?)"
            params.append(collaboration_type)
        
        query += " GROUP BY c2.name, cc2.role ORDER BY collaboration_count DESC, c2.name"
        
        rows = self.db.execute_query(query, params)
        
        collaborations = []
        for row in rows:
            collaborations.append({
                "collaborator_name": row['collaborator_name'],
                "role": row['role'],
                "collaboration_count": row['collaboration_count']
            })
        
        return {
            "results": collaborations,
            "metadata": {
                "query_time": time.time() - start_time,
                "result_count": len(collaborations),
                "search_terms": {"creator_name": creator_name, "collaboration_type": collaboration_type},
                "fuzzy_matches_used": False
            }
        }
    
    def advanced_search(self, criteria: Dict[str, Any], match_all: bool = True) -> Dict[str, Any]:
        """Multi-criteria search with complex filters"""
        start_time = time.time()
        
        base_query = "SELECT DISTINCT c.* FROM comics c"
        joins = []
        conditions = []
        params = []
        
        # Handle basic comic fields
        basic_where, basic_params = SearchUtils.build_where_clause(criteria)
        if basic_where != "1=1":
            conditions.append(basic_where)
            params.extend(basic_params)
        
        # Handle creator criteria
        if 'creator' in criteria:
            joins.append("JOIN comic_creators cc ON c.id = cc.comic_id")
            joins.append("JOIN creators cr ON cc.creator_id = cr.id")
            conditions.append("UPPER(cr.name) LIKE UPPER(?)")
            params.append(f"%{SearchUtils.escape_sql_like(criteria['creator'])}%")
        
        # Handle character criteria
        if 'character' in criteria:
            joins.append("JOIN comic_characters cch ON c.id = cch.comic_id")
            joins.append("JOIN characters ch ON cch.character_id = ch.id")
            conditions.append("UPPER(ch.name) LIKE UPPER(?)")
            params.append(f"%{SearchUtils.escape_sql_like(criteria['character'])}%")
        
        # Handle team criteria
        if 'team' in criteria:
            joins.append("JOIN comic_teams ct ON c.id = ct.comic_id")
            joins.append("JOIN teams t ON ct.team_id = t.id")
            conditions.append("UPPER(t.name) LIKE UPPER(?)")
            params.append(f"%{SearchUtils.escape_sql_like(criteria['team'])}%")
        
        # Build final query
        query = base_query
        if joins:
            query += " " + " ".join(set(joins))  # Remove duplicates
        
        if conditions:
            connector = " AND " if match_all else " OR "
            query += " WHERE " + connector.join(conditions)
        
        query += " ORDER BY c.year, c.title"
        
        rows = self.db.execute_query(query, params)
        results = [self._build_comic_result(row) for row in rows]
        
        return {
            "results": [result.__dict__ for result in results],
            "metadata": {
                "query_time": time.time() - start_time,
                "result_count": len(results),
                "search_terms": criteria,
                "match_all": match_all,
                "fuzzy_matches_used": False
            }
        }


# Initialize MCP server and database
DATABASE_PATH = "comics.db"  # Default path, can be configured
db_manager = DatabaseManager(DATABASE_PATH)
search_tools = ComicSearchTools(db_manager)

# Create MCP server
mcp = FastMCP("ComicBookSearcher")


@mcp.tool()
def search_by_title(title: str, exact_match: bool = False) -> dict:
    """Search for comics by title with fuzzy matching support"""
    try:
        return search_tools.search_by_title(title, exact_match)
    except Exception as e:
        logger.error(f"Error in search_by_title: {e}")
        return {"error": str(e), "results": [], "metadata": {"error": True}}


@mcp.tool()
def search_by_series(series: str, publisher: str = None, exact_match: bool = False) -> dict:
    """Search for comics by series name, optionally filtered by publisher"""
    try:
        return search_tools.search_by_series(series, publisher, exact_match)
    except Exception as e:
        logger.error(f"Error in search_by_series: {e}")
        return {"error": str(e), "results": [], "metadata": {"error": True}}


@mcp.tool()
def search_by_character(character_name: str, include_teams: bool = True) -> dict:
    """Find comics featuring specific characters, optionally including team appearances"""
    try:
        return search_tools.search_by_character(character_name, include_teams)
    except Exception as e:
        logger.error(f"Error in search_by_character: {e}")
        return {"error": str(e), "results": [], "metadata": {"error": True}}


@mcp.tool()
def search_by_team(team_name: str) -> dict:
    """Find comics featuring specific teams"""
    try:
        return search_tools.search_by_team(team_name)
    except Exception as e:
        logger.error(f"Error in search_by_team: {e}")
        return {"error": str(e), "results": [], "metadata": {"error": True}}


@mcp.tool()
def search_by_creator(creator_name: str, role: str = None, exact_match: bool = False) -> dict:
    """Find comics by creator (writer, artist, etc.) with optional role filtering"""
    try:
        return search_tools.search_by_creator(creator_name, role, exact_match)
    except Exception as e:
        logger.error(f"Error in search_by_creator: {e}")
        return {"error": str(e), "results": [], "metadata": {"error": True}}


@mcp.tool()
def search_by_event(event_name: str) -> dict:
    """Find comics related to specific events or story arcs"""
    try:
        return search_tools.search_by_event(event_name)
    except Exception as e:
        logger.error(f"Error in search_by_event: {e}")
        return {"error": str(e), "results": [], "metadata": {"error": True}}


@mcp.tool()
def search_by_year(year: int = None, start_year: int = None, end_year: int = None) -> dict:
    """Find comics published in specific year or year range"""
    try:
        return search_tools.search_by_year(year, start_year, end_year)
    except Exception as e:
        logger.error(f"Error in search_by_year: {e}")
        return {"error": str(e), "results": [], "metadata": {"error": True}}


@mcp.tool()
def find_creator_collaborations(creator_name: str, collaboration_type: str = None) -> dict:
    """Find relationships between creators and their collaboration history"""
    try:
        return search_tools.find_creator_collaborations(creator_name, collaboration_type)
    except Exception as e:
        logger.error(f"Error in find_creator_collaborations: {e}")
        return {"error": str(e), "results": [], "metadata": {"error": True}}


@mcp.tool()
def advanced_search(criteria: dict, match_all: bool = True) -> dict:
    """Multi-criteria search with complex filters. 
    
    Criteria can include: title, series, publisher, year, start_year, end_year, 
    creator, character, team. Set match_all=False for OR logic instead of AND.
    """
    try:
        return search_tools.advanced_search(criteria, match_all)
    except Exception as e:
        logger.error(f"Error in advanced_search: {e}")
        return {"error": str(e), "results": [], "metadata": {"error": True}}


@mcp.tool()
def get_database_stats() -> dict:
    """Get statistics about the comic database"""
    try:
        stats_queries = {
            "total_comics": "SELECT COUNT(*) as count FROM comics",
            "total_series": "SELECT COUNT(DISTINCT series) as count FROM comics WHERE series IS NOT NULL",
            "total_publishers": "SELECT COUNT(DISTINCT publisher) as count FROM comics WHERE publisher IS NOT NULL",
            "total_creators": "SELECT COUNT(*) as count FROM creators",
            "total_characters": "SELECT COUNT(*) as count FROM characters",
            "total_teams": "SELECT COUNT(*) as count FROM teams",
            "year_range": "SELECT MIN(year) as min_year, MAX(year) as max_year FROM comics WHERE year IS NOT NULL"
        }
        
        stats = {}
        for stat_name, query in stats_queries.items():
            result = db_manager.execute_query(query)
            if stat_name == "year_range":
                stats[stat_name] = dict(result[0]) if result else {"min_year": None, "max_year": None}
            else:
                stats[stat_name] = result[0]['count'] if result else 0
        
        return {"stats": stats, "success": True}
    except Exception as e:
        logger.error(f"Error in get_database_stats: {e}")
        return {"error": str(e), "success": False}


# Server configuration
if __name__ == "__main__":
    import sys
    import os
    
    # Check for database path argument
    if len(sys.argv) > 1:
        DATABASE_PATH = sys.argv[1]
    elif 'COMIC_DB_PATH' in os.environ:
        DATABASE_PATH = os.environ['COMIC_DB_PATH']
    
    # Verify database exists
    if not Path(DATABASE_PATH).exists():
        logger.error(f"Database file not found: {DATABASE_PATH}")
        sys.exit(1)
    
    # Update database manager with correct path
    db_manager.db_path = DATABASE_PATH
    
    logger.info(f"Starting Comic Book MCP Server with database: {DATABASE_PATH}")
    mcp.run()
