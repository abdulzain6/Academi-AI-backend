from youtubesearchpython import CustomSearch
from typing import List, Dict
import concurrent.futures

class YouTubeSearch:
    def __init__(self):
        """Initialize YouTube search"""
        self.max_workers = 3
        self.caption_filter = "EgIoAQ%253D%253D"  # Filter for videos with captions
    
    def search_videos(
        self,
        query: str,
        max_results: int = 10
    ) -> List[Dict]:
        """
        Search for YouTube videos with captions using CustomSearch.
        
        Args:
            query (str): Search query
            max_results (int): Maximum number of results to return
            
        Returns:
            List[Dict]: List of videos with captions
        """
        try:
            # Create search with caption filter
            search = CustomSearch(
                query,
                searchPreferences="sp=" + self.caption_filter,
                limit=max_results
            )
            results = search.result()['result']
            
            # Process results in parallel
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                videos = list(executor.map(self._transform_result, results))
            
            return [video for video in videos if video is not None]
            
        except Exception as e:
            raise Exception(f"Error searching YouTube videos: {str(e)}")
    
    def _transform_result(self, result: Dict) -> Dict:
        """
        Transform search result into standardized format.
        
        Args:
            result (Dict): Raw search result
            
        Returns:
            Dict: Transformed video data
        """
        try:
            return {
                'id': result.get('id'),
                'title': result.get('title'),
                'url': result.get('link'),
                'duration': result.get('duration'),
                'view_count': result.get('viewCount', {}).get('text'),
                'thumbnail': result.get('thumbnails', [{}])[0].get('url'),
                'channel_name': result.get('channel', {}).get('name'),
                'channel_url': result.get('channel', {}).get('link'),
                'publish_time': result.get('publishedTime'),
                'has_captions': True  # Since we're using caption filter
            }
        except:
            return None