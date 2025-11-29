#!/usr/bin/env python3
"""
Komga MCP Server

A Model Context Protocol server for interacting with Komga comic book server.
Provides tools for searching libraries, managing reading lists, and discovering comics.
"""

import os
import json
import httpx
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from mcp.server.fastmcp import FastMCP

# Create the MCP server
mcp = FastMCP("Komga")

@dataclass
class KomgaConfig:
    """Configuration for Komga server connection"""
    base_url: str
    api_key: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None

# Global configuration
komga_config = KomgaConfig(
    base_url=os.getenv("KOMGA_BASE_URL", "http://localhost:25600"),
    api_key=os.getenv("KOMGA_API_KEY"),
    username=os.getenv("KOMGA_USERNAME"),
    password=os.getenv("KOMGA_PASSWORD")
)

def get_auth_headers() -> Dict[str, str]:
    """Get authentication headers for Komga API"""
    headers = {"Content-Type": "application/json"}
    
    if komga_config.api_key:
        headers["X-API-Key"] = komga_config.api_key
    elif komga_config.username and komga_config.password:
        import base64
        credentials = f"{komga_config.username}:{komga_config.password}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        headers["Authorization"] = f"Basic {encoded_credentials}"
    else:
        raise ValueError("No authentication method configured. Set KOMGA_API_KEY or KOMGA_USERNAME/KOMGA_PASSWORD")
    
    return headers

async def make_komga_request(method: str, endpoint: str, params: Optional[Dict] = None, json_data: Optional[Dict] = None) -> Dict[str, Any]:
    """Make a request to the Komga API"""
    url = f"{komga_config.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
    headers = get_auth_headers()
    
    async with httpx.AsyncClient() as client:
        response = await client.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=json_data,
            timeout=30.0
        )
        response.raise_for_status()
        return response.json()

@mcp.tool()
async def search_series(
    search_text: Optional[str] = None,
    library_ids: Optional[List[str]] = None,
    publisher: Optional[List[str]] = None,
    genre: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    read_status: Optional[List[str]] = None,
    status: Optional[List[str]] = None,
    page: int = 0,
    size: int = 20
) -> Dict[str, Any]:
    """
    Search for comic series with advanced filtering options.
    
    Args:
        search_text: Text to search for in series titles
        library_ids: List of library IDs to search in
        publisher: List of publishers to filter by
        genre: List of genres to filter by
        tags: List of tags to filter by
        read_status: List of read statuses (UNREAD, READ, IN_PROGRESS)
        status: List of series statuses (ENDED, ONGOING, ABANDONED, HIATUS)
        page: Page number for pagination (default: 0)
        size: Number of results per page (default: 20)
    """
    search_condition = {}
    
    if search_text:
        search_condition["fullTextSearch"] = search_text
    
    # Build complex search condition if filters are provided
    conditions = []
    
    if library_ids:
        for lib_id in library_ids:
            conditions.append({"libraryId": {"operator": "is", "value": lib_id}})
    
    if publisher:
        for pub in publisher:
            conditions.append({"publisher": {"operator": "is", "value": pub}})
    
    if genre:
        for g in genre:
            conditions.append({"genre": {"operator": "is", "value": g}})
    
    if tags:
        for tag in tags:
            conditions.append({"tag": {"operator": "is", "value": tag}})
    
    if read_status:
        for status_val in read_status:
            conditions.append({"readStatus": {"operator": "is", "value": status_val}})
    
    if status:
        for stat in status:
            conditions.append({"seriesStatus": {"operator": "is", "value": stat}})
    
    if conditions:
        if len(conditions) == 1:
            search_condition["condition"] = conditions[0]
        else:
            search_condition["condition"] = {"allOf": conditions}
    
    params = {"page": page, "size": size}
    result = await make_komga_request("POST", "/api/v1/series/list", params=params, json_data=search_condition)
    return result

@mcp.tool()
async def search_books(
    search_text: Optional[str] = None,
    library_ids: Optional[List[str]] = None,
    series_id: Optional[str] = None,
    read_status: Optional[List[str]] = None,
    media_status: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    page: int = 0,
    size: int = 20
) -> Dict[str, Any]:
    """
    Search for individual comic books with filtering options.
    
    Args:
        search_text: Text to search for in book titles
        library_ids: List of library IDs to search in
        series_id: Specific series ID to search within
        read_status: List of read statuses (UNREAD, READ, IN_PROGRESS)
        media_status: List of media statuses (READY, ERROR, UNKNOWN, UNSUPPORTED, OUTDATED)
        tags: List of tags to filter by
        page: Page number for pagination (default: 0)
        size: Number of results per page (default: 20)
    """
    search_condition = {}
    
    if search_text:
        search_condition["fullTextSearch"] = search_text
    
    conditions = []
    
    if library_ids:
        for lib_id in library_ids:
            conditions.append({"libraryId": {"operator": "is", "value": lib_id}})
    
    if series_id:
        conditions.append({"seriesId": {"operator": "is", "value": series_id}})
    
    if read_status:
        for status_val in read_status:
            conditions.append({"readStatus": {"operator": "is", "value": status_val}})
    
    if media_status:
        for status_val in media_status:
            conditions.append({"mediaStatus": {"operator": "is", "value": status_val}})
    
    if tags:
        for tag in tags:
            conditions.append({"tag": {"operator": "is", "value": tag}})
    
    if conditions:
        if len(conditions) == 1:
            search_condition["condition"] = conditions[0]
        else:
            search_condition["condition"] = {"allOf": conditions}
    
    params = {"page": page, "size": size}
    result = await make_komga_request("POST", "/api/v1/books/list", params=params, json_data=search_condition)
    return result

@mcp.tool()
async def get_libraries() -> List[Dict[str, Any]]:
    """
    List all available comic libraries in the Komga server.
    
    Returns:
        List of library objects with details like name, path, and settings
    """
    result = await make_komga_request("GET", "/api/v1/libraries")
    return result

@mcp.tool()
async def search_authors(
    search_text: Optional[str] = None,
    role: Optional[str] = None,
    library_ids: Optional[List[str]] = None,
    series_id: Optional[str] = None,
    page: int = 0,
    size: int = 20
) -> Dict[str, Any]:
    """
    Find comics by author/creator with role filtering.
    
    Args:
        search_text: Text to search for in author names
        role: Author role to filter by (writer, artist, penciller, inker, colorist, etc.)
        library_ids: List of library IDs to search in
        series_id: Specific series ID to search within
        page: Page number for pagination (default: 0)
        size: Number of results per page (default: 20)
    """
    params = {"page": page, "size": size}
    
    if search_text:
        params["search"] = search_text
    if role:
        params["role"] = role
    if library_ids:
        params["library_id"] = library_ids
    if series_id:
        params["series_id"] = series_id
    
    result = await make_komga_request("GET", "/api/v2/authors", params=params)
    return result

@mcp.tool()
async def create_reading_list(
    name: str,
    book_ids: List[str],
    summary: str = "",
    ordered: bool = True
) -> Dict[str, Any]:
    """
    Create a new reading list with specified books.
    
    Args:
        name: Name of the reading list
        book_ids: List of book IDs to include in the reading list
        summary: Optional description of the reading list
        ordered: Whether the reading list should maintain book order (default: True)
    """
    reading_list_data = {
        "name": name,
        "bookIds": book_ids,
        "summary": summary,
        "ordered": ordered
    }
    
    result = await make_komga_request("POST", "/api/v1/readlists", json_data=reading_list_data)
    return result

@mcp.tool()
async def get_reading_lists(
    search: Optional[str] = None,
    library_ids: Optional[List[str]] = None,
    page: int = 0,
    size: int = 20
) -> Dict[str, Any]:
    """
    List existing reading lists with optional filtering.
    
    Args:
        search: Text to search for in reading list names
        library_ids: List of library IDs to filter by
        page: Page number for pagination (default: 0)
        size: Number of results per page (default: 20)
    """
    params = {"page": page, "size": size}
    
    if search:
        params["search"] = search
    if library_ids:
        params["library_id"] = library_ids
    
    result = await make_komga_request("GET", "/api/v1/readlists", params=params)
    return result

@mcp.tool()
async def add_to_reading_list(
    reading_list_id: str,
    book_ids: List[str],
    name: Optional[str] = None,
    summary: Optional[str] = None,
    ordered: Optional[bool] = None
) -> Dict[str, Any]:
    """
    Add books to an existing reading list or update its properties.
    
    Args:
        reading_list_id: ID of the reading list to update
        book_ids: List of book IDs to add to the reading list
        name: Optional new name for the reading list
        summary: Optional new summary for the reading list
        ordered: Optional new ordered setting for the reading list
    """
    # First get the current reading list to merge book IDs
    current_list = await make_komga_request("GET", f"/api/v1/readlists/{reading_list_id}")
    
    # Merge existing book IDs with new ones (avoiding duplicates)
    existing_book_ids = set(current_list.get("bookIds", []))
    all_book_ids = list(existing_book_ids.union(set(book_ids)))
    
    update_data = {"bookIds": all_book_ids}
    
    if name is not None:
        update_data["name"] = name
    if summary is not None:
        update_data["summary"] = summary
    if ordered is not None:
        update_data["ordered"] = ordered
    
    result = await make_komga_request("PATCH", f"/api/v1/readlists/{reading_list_id}", json_data=update_data)
    return {"status": "updated", "reading_list_id": reading_list_id, "total_books": len(all_book_ids)}

@mcp.tool()
async def get_collections(
    search: Optional[str] = None,
    library_ids: Optional[List[str]] = None,
    page: int = 0,
    size: int = 20
) -> Dict[str, Any]:
    """
    Browse curated collections of series.
    
    Args:
        search: Text to search for in collection names
        library_ids: List of library IDs to filter by
        page: Page number for pagination (default: 0)
        size: Number of results per page (default: 20)
    """
    params = {"page": page, "size": size}
    
    if search:
        params["search"] = search
    if library_ids:
        params["library_id"] = library_ids
    
    result = await make_komga_request("GET", "/api/v1/collections", params=params)
    return result

@mcp.tool()
async def get_metadata_options(
    library_ids: Optional[List[str]] = None
) -> Dict[str, List[str]]:
    """
    Get available metadata options for filtering (genres, publishers, tags, etc.).
    
    Args:
        library_ids: List of library IDs to get metadata for (optional)
    """
    params = {}
    if library_ids:
        params["library_id"] = library_ids
    
    # Fetch all metadata types
    genres = await make_komga_request("GET", "/api/v1/genres", params=params)
    publishers = await make_komga_request("GET", "/api/v1/publishers", params=params)
    tags = await make_komga_request("GET", "/api/v1/tags", params=params)
    languages = await make_komga_request("GET", "/api/v1/languages", params=params)
    age_ratings = await make_komga_request("GET", "/api/v1/age-ratings", params=params)
    
    return {
        "genres": genres,
        "publishers": publishers,
        "tags": tags,
        "languages": languages,
        "age_ratings": age_ratings
    }

@mcp.tool()
async def get_on_deck_books(
    library_ids: Optional[List[str]] = None,
    page: int = 0,
    size: int = 20
) -> Dict[str, Any]:
    """
    Get suggested "next to read" books based on reading progress.
    
    Args:
        library_ids: List of library IDs to get suggestions from
        page: Page number for pagination (default: 0)
        size: Number of results per page (default: 20)
    """
    params = {"page": page, "size": size}
    
    if library_ids:
        params["library_id"] = library_ids
    
    result = await make_komga_request("GET", "/api/v1/books/ondeck", params=params)
    return result

@mcp.tool()
async def get_latest_additions(
    content_type: str = "both",
    library_ids: Optional[List[str]] = None,
    page: int = 0,
    size: int = 20
) -> Dict[str, Any]:
    """
    Get recently added series and/or books.
    
    Args:
        content_type: Type of content to retrieve ("series", "books", or "both")
        library_ids: List of library IDs to get additions from
        page: Page number for pagination (default: 0)
        size: Number of results per page (default: 20)
    """
    params = {"page": page, "size": size}
    
    if library_ids:
        params["library_id"] = library_ids
    
    result = {}
    
    if content_type in ["series", "both"]:
        series_result = await make_komga_request("GET", "/api/v1/series/latest", params=params)
        result["latest_series"] = series_result
    
    if content_type in ["books", "both"]:
        books_result = await make_komga_request("GET", "/api/v1/books/latest", params=params)
        result["latest_books"] = books_result
    
    return result

# Configuration tool for setting up Komga connection
@mcp.tool()
def configure_komga(
    base_url: str,
    api_key: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None
) -> Dict[str, str]:
    """
    Configure Komga server connection settings.
    
    Args:
        base_url: Base URL of the Komga server (e.g., http://localhost:25600)
        api_key: API key for authentication (preferred method)
        username: Username for basic auth (if no API key)
        password: Password for basic auth (if no API key)
    """
    global komga_config
    
    komga_config.base_url = base_url.rstrip('/')
    komga_config.api_key = api_key
    komga_config.username = username
    komga_config.password = password
    
    auth_method = "API Key" if api_key else "Basic Auth" if username and password else "None"
    
    return {
        "status": "configured",
        "base_url": komga_config.base_url,
        "authentication": auth_method
    }

if __name__ == "__main__":
    # Set up configuration from environment variables if available
    if not komga_config.api_key and not (komga_config.username and komga_config.password):
        print("Warning: No authentication configured. Use configure_komga tool or set environment variables:")
        print("  KOMGA_API_KEY=your_api_key")
        print("  or")
        print("  KOMGA_USERNAME=your_username")
        print("  KOMGA_PASSWORD=your_password")
        print("  KOMGA_BASE_URL=http://localhost:25600")
    
    mcp.run()