# Comic Book Database MCP Server Specification

## Overview
Build a Python MCP (Model Context Protocol) server that provides intelligent search capabilities for a comic book collection database. The server will expose tools for searching comics by various criteria with fuzzy matching and relationship analysis.

## Project Structure
```
comic_mcp_server/
├── src/
│   ├── comic_mcp_server/
│   │   ├── __init__.py
│   │   ├── server.py          # Main MCP server
│   │   ├── database.py        # Database connection and queries
│   │   ├── search_tools.py    # Search tool implementations
│   │   └── utils.py           # Helper functions for fuzzy matching
├── pyproject.toml
├── README.md
└── requirements.txt
```

## Dependencies
```toml
[project]
dependencies = [
    "mcp>=1.0.0",
    "sqlite3",  # Built into Python
    "fuzzywuzzy>=0.18.0",
    "python-levenshtein>=0.25.0",  # For faster fuzzy matching
    "typing-extensions>=4.0.0"
]
```

## Core Components

### 1. Database Connection Module (`database.py`)
- Create a database connection manager
- Implement connection pooling for SQLite
- Handle database errors gracefully
- Provide base query execution methods

### 2. Search Tools Module (`search_tools.py`)
Implement the following MCP tools:

#### Tool: `search_by_title`
- **Description**: Search for comics by title with fuzzy matching
- **Parameters**:
  - `title` (str): Comic title to search for
  - `exact_match` (bool, default=False): Whether to require exact match
- **Returns**: List of matching comics with metadata

#### Tool: `search_by_series`
- **Description**: Search for comics by series name
- **Parameters**:
  - `series` (str): Series name to search for
  - `publisher` (str, optional): Filter by publisher
  - `exact_match` (bool, default=False)
- **Returns**: List of comics in matching series

#### Tool: `search_by_character`
- **Description**: Find comics featuring specific characters
- **Parameters**:
  - `character_name` (str): Character name to search for
  - `include_teams` (bool, default=True): Include team appearances
- **Returns**: Comics featuring the character

#### Tool: `search_by_team`
- **Description**: Find comics featuring specific teams
- **Parameters**:
  - `team_name` (str): Team name to search for
- **Returns**: Comics featuring the team

#### Tool: `search_by_creator`
- **Description**: Find comics by creator (writer, artist, etc.)
- **Parameters**:
  - `creator_name` (str): Creator name to search for
  - `role` (str, optional): Specific role (writer, artist, etc.)
  - `exact_match` (bool, default=False)
- **Returns**: Comics by the creator

#### Tool: `search_by_event`
- **Description**: Find comics related to specific events or story arcs
- **Parameters**:
  - `event_name` (str): Event or story arc name
- **Returns**: Comics related to the event

#### Tool: `search_by_year`
- **Description**: Find comics published in specific year or year range
- **Parameters**:
  - `year` (int, optional): Specific year
  - `start_year` (int, optional): Start of year range
  - `end_year` (int, optional): End of year range
- **Returns**: Comics from specified time period

#### Tool: `find_creator_collaborations`
- **Description**: Find relationships between creators
- **Parameters**:
  - `creator_name` (str): Primary creator name
  - `collaboration_type` (str, optional): Type of collaboration to find
- **Returns**: Other creators who worked with the specified creator

#### Tool: `advanced_search`
- **Description**: Multi-criteria search with complex filters
- **Parameters**:
  - `criteria` (dict): Dictionary of search criteria
  - `match_all` (bool, default=True): Whether all criteria must match
- **Returns**: Comics matching the criteria

### 3. Utility Functions (`utils.py`)

#### Fuzzy Matching Functions
```python
def fuzzy_match_name(query: str, target: str, threshold: int = 80) -> bool:
    """Check if query matches target with fuzzy matching"""

def get_fuzzy_matches(query: str, candidates: list, threshold: int = 80) -> list:
    """Get list of candidates that fuzzy match the query"""

def normalize_name(name: str) -> str:
    """Normalize name for consistent matching"""
```

#### Query Building Functions
```python
def build_where_clause(criteria: dict) -> tuple[str, list]:
    """Build SQL WHERE clause from criteria dictionary"""

def escape_sql_like(text: str) -> str:
    """Escape special characters for SQL LIKE queries"""
```

### 4. Main Server (`server.py`)

#### Server Setup
```python
from mcp.server.fastmcp import FastMCP
from .search_tools import *
from .database import DatabaseManager

# Initialize MCP server
mcp = FastMCP("ComicBookSearcher")

# Initialize database connection
db_manager = DatabaseManager("path/to/comics.db")
```

#### Tool Registration
Register all search tools with proper error handling and validation.

## Database Query Patterns

### Fuzzy Search Implementations
1. **Case-insensitive matching**: Use `UPPER()` or `LOWER()` in SQL
2. **Partial matching**: Use `LIKE '%term%'` patterns
3. **Word-based matching**: Split terms and match individual words
4. **Fuzzy matching**: Use Python fuzzywuzzy for post-processing results

### Example Query Structures

#### Character Search
```sql
SELECT DISTINCT c.* FROM comics c
JOIN comic_characters cc ON c.id = cc.comic_id
JOIN characters ch ON cc.character_id = ch.id
WHERE UPPER(ch.name) LIKE UPPER('%{character_name}%')
```

#### Creator Collaboration Query
```sql
SELECT DISTINCT c2.name, cc2.role, COUNT(*) as collaboration_count
FROM comic_creators cc1
JOIN comic_creators cc2 ON cc1.comic_id = cc2.comic_id
JOIN creators c1 ON cc1.creator_id = c1.id
JOIN creators c2 ON cc2.creator_id = c2.id
WHERE UPPER(c1.name) LIKE UPPER('%{creator_name}%')
AND c1.id != c2.id
GROUP BY c2.name, cc2.role
ORDER BY collaboration_count DESC
```

## Error Handling Strategy

### Database Errors
- Connection failures: Retry with exponential backoff
- Query errors: Return descriptive error messages
- Missing data: Return empty results with appropriate messages

### Input Validation
- Sanitize all user inputs
- Validate parameter types
- Handle special characters in search terms

### Response Formatting
- Consistent JSON response structure
- Include metadata (search time, result count)
- Provide helpful error messages

## Implementation Guidelines

### Performance Considerations
1. **Indexing**: Ensure proper database indexes exist
2. **Query Optimization**: Use EXPLAIN QUERY PLAN for complex queries
3. **Result Limiting**: Implement pagination for large result sets
4. **Caching**: Consider caching for frequently accessed data

### Fuzzy Matching Strategy
1. **Primary**: SQL-based partial matching (fast)
2. **Secondary**: Python fuzzy matching for refined results
3. **Threshold**: Configurable similarity thresholds
4. **Fallback**: Gradually reduce match requirements if no results

### Response Structure
```python
{
    "results": [
        {
            "id": int,
            "title": str,
            "series": str,
            "publisher": str,
            "year": int,
            "creators": [{"name": str, "role": str}],
            "characters": [str],
            "file_path": str,
            "match_confidence": float  # For fuzzy matches
        }
    ],
    "metadata": {
        "query_time": float,
        "result_count": int,
        "search_terms": dict,
        "fuzzy_matches_used": bool
    }
}
```

## Testing Strategy

### Unit Tests
- Database connection and query functions
- Fuzzy matching algorithms
- Input validation and sanitization

### Integration Tests
- End-to-end tool execution
- Database schema compatibility
- Error handling scenarios

### Test Data
- Create sample database with known test cases
- Include edge cases (special characters, duplicates)
- Test with actual comic metadata formats

## Usage Examples

### Example 1: Find Spider-Man Comics
```python
# User query: "Find all Spider-Man comics from the 2000s"
search_by_character(character_name="Spider-Man")
search_by_year(start_year=2000, end_year=2009)
```

### Example 2: Creator Collaboration
```python
# User query: "What artists did Stan Lee work with?"
find_creator_collaborations(
    creator_name="Stan Lee",
    collaboration_type="artist"
)
```

### Example 3: Event Comics
```python
# User query: "Find all Dark Crisis comics"
search_by_event(event_name="Dark Crisis")
```

## Deployment Notes

### MCP Server Registration
- Register with Open WebUI MCP integration
- Configure appropriate permissions and access controls
- Set up logging for debugging and monitoring

### Configuration
- Database path configuration
- Search sensitivity thresholds
- Result limits and pagination settings
- Caching configuration

## Future Enhancements

### Potential Additions
1. **Natural Language Processing**: Parse complex queries
2. **Reading Order Generation**: Create reading lists for events/series
3. **Recommendation Engine**: Suggest similar comics
4. **Metadata Enrichment**: Auto-populate missing information
5. **Komga Integration**: Direct integration with Komga API

### Scalability Considerations
- Support for multiple database backends
- Distributed search capabilities
- Real-time metadata updates
- Web interface for testing and administration
