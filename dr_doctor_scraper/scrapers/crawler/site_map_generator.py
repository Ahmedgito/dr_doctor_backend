"""Site map generator for crawled pages."""

from __future__ import annotations

from typing import Dict, List, Optional
from collections import defaultdict

from scrapers.logger import logger
from scrapers.crawler.utils import extract_domain


class SiteMapGenerator:
    """Generates hierarchical site map from crawled pages."""
    
    def __init__(self, domain: str, root_url: str):
        """Initialize site map generator.
        
        Args:
            domain: Domain name
            root_url: Root URL of the site
        """
        self.domain = domain
        self.root_url = root_url
    
    def generate_site_map(self, pages: List[Dict]) -> Dict:
        """Generate site map from list of crawled pages.
        
        Args:
            pages: List of page dictionaries with 'url' and 'depth' keys
            
        Returns:
            Site map dictionary with structure and statistics
        """
        if not pages:
            return {
                "domain": self.domain,
                "root_url": self.root_url,
                "total_pages": 0,
                "max_depth": 0,
                "pages_by_depth": {},
                "pages": [],
            }
        
        # Build parent-child relationships
        url_to_page = {page["url"]: page for page in pages}
        children_map = defaultdict(list)
        
        # Find children for each page
        for page in pages:
            parent_url = page.get("parent_url")
            if parent_url and parent_url in url_to_page:
                children_map[parent_url].append(page["url"])
        
        # Build tree structure
        root_pages = [p for p in pages if p.get("depth", 0) == 0]
        if not root_pages:
            # If no depth 0 pages, use root URL as root
            root_pages = [p for p in pages if p["url"] == self.root_url]
            if not root_pages:
                root_pages = [pages[0]]  # Use first page as root
        
        # Calculate statistics
        max_depth = max((p.get("depth", 0) for p in pages), default=0)
        pages_by_depth = defaultdict(int)
        for page in pages:
            depth = page.get("depth", 0)
            pages_by_depth[depth] += 1
        
        # Build tree recursively
        def build_tree(url: str, visited: set) -> Optional[Dict]:
            if url in visited:
                return None
            visited.add(url)
            
            page = url_to_page.get(url)
            if not page:
                return None
            
            node = {
                "url": url,
                "depth": page.get("depth", 0),
                "title": page.get("title"),
                "content_type": page.get("content_type"),
                "children": [],
            }
            
            # Add children
            for child_url in children_map.get(url, []):
                child_node = build_tree(child_url, visited)
                if child_node:
                    node["children"].append(child_node)
            
            return node
        
        # Build tree starting from root pages
        tree_pages = []
        visited = set()
        for root_page in root_pages:
            root_node = build_tree(root_page["url"], visited)
            if root_node:
                tree_pages.append(root_node)
        
        # Add any unvisited pages (orphaned pages)
        for page in pages:
            if page["url"] not in visited:
                node = {
                    "url": page["url"],
                    "depth": page.get("depth", 0),
                    "title": page.get("title"),
                    "content_type": page.get("content_type"),
                    "children": [],
                }
                tree_pages.append(node)
        
        return {
            "domain": self.domain,
            "root_url": self.root_url,
            "total_pages": len(pages),
            "max_depth": max_depth,
            "pages_by_depth": dict(pages_by_depth),
            "pages": tree_pages,
        }
    
    def get_flat_url_list(self, site_map: Dict) -> List[str]:
        """Get flat list of all URLs from site map.
        
        Args:
            site_map: Site map dictionary
            
        Returns:
            List of URLs
        """
        urls = []
        
        def extract_urls(nodes: List[Dict]):
            for node in nodes:
                urls.append(node["url"])
                if node.get("children"):
                    extract_urls(node["children"])
        
        extract_urls(site_map.get("pages", []))
        return urls
    
    def get_pages_at_depth(self, site_map: Dict, depth: int) -> List[Dict]:
        """Get all pages at a specific depth.
        
        Args:
            site_map: Site map dictionary
            depth: Depth level
            
        Returns:
            List of page nodes at that depth
        """
        pages = []
        
        def find_at_depth(nodes: List[Dict], current_depth: int):
            for node in nodes:
                if node.get("depth") == depth:
                    pages.append(node)
                if node.get("children"):
                    find_at_depth(node["children"], current_depth + 1)
        
        find_at_depth(site_map.get("pages", []), 0)
        return pages


