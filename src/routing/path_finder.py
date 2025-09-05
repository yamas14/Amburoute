import osmnx as ox
import networkx as nx
from typing import List, Tuple

class PathFinder:
    def __init__(self):
        self.graph = None
        
    def load_road_network(self, location: str):
        """Load road network for a specific location"""
        self.graph = ox.graph_from_place(location, network_type='drive')
        
    def get_shortest_path(self, start_coords: Tuple[float, float], 
                         end_coords: Tuple[float, float]) -> List[int]:
        """
        Find shortest path between two coordinates
        Args:
            start_coords: (latitude, longitude) of start point
            end_coords: (latitude, longitude) of end point
        Returns:
            List of node IDs representing the path
        """
        start_node = ox.nearest_nodes(self.graph, start_coords[1], start_coords[0])
        end_node = ox.nearest_nodes(self.graph, end_coords[1], end_coords[0])
        
        return nx.shortest_path(self.graph, start_node, end_node, weight='length')