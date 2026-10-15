import networkx as nx
import matplotlib.pyplot as plt
from typing import List, Dict, Tuple, Set, Union
from models.circuit import Circuit, Signal
from models.routing import RoutingResult, NetRoute
from models.fpga_architecture import BoundingBox, Point

class ConflictGraphBuilder:
    """Class for building and analyzing a conflict graph"""
    
    def __init__(self):
        self.conflict_graph = nx.Graph()
    
    def build_conflict_graph(self, data: Union[Circuit, RoutingResult]) -> nx.Graph:
        """Builds a conflict graph for the given circuit or routing"""
        self.conflict_graph.clear()
        
        # Check the data type
        if isinstance(data, RoutingResult):
            return self._build_from_routing(data)
        elif isinstance(data, Circuit):
            return self._build_from_circuit(data)
        else:
            raise ValueError(f"Unsupported data type: {type(data)}")
    
    def _build_from_circuit(self, circuit: Circuit) -> nx.Graph:
        """Builds a conflict graph from a Circuit object (legacy)"""
        # Add all active signals as nodes
        active_signals = circuit.get_active_signals()
        for signal in active_signals:
            self.conflict_graph.add_node(signal.name, signal=signal)
        
        # Detect conflicts based on bounding box overlap
        self._detect_bounding_box_conflicts_circuit(circuit)
        
        # Detect conflicts based on routing resource sharing
        self._detect_routing_conflicts_circuit(circuit)
        
        return self.conflict_graph
    
    def _build_from_routing(self, routing: RoutingResult) -> nx.Graph:
        """Builds a conflict graph from a Routing object"""
        # Add all nets as nodes
        for route in routing.routes:
            self.conflict_graph.add_node(route.net_name, route=route)
        
        # Detect conflicts based on bounding box overlap
        self._detect_bounding_box_conflicts_routing(routing)
        
        # Detect conflicts based on routing resource sharing
        self._detect_routing_conflicts_routing(routing)
        
        return self.conflict_graph
    
    def _detect_bounding_box_conflicts_circuit(self, circuit: Circuit):
        """Detects conflicts based on bounding box overlap (Circuit)"""
        signal_bboxes = {}
        
        # Compute bounding boxes for all signals
        for signal in circuit.get_active_signals():
            signal_bboxes[signal.name] = signal.get_bounding_box()
        
        # Check overlap for each pair of signals
        signal_names = list(signal_bboxes.keys())
        for i in range(len(signal_names)):
            for j in range(i + 1, len(signal_names)):
                signal1 = signal_names[i]
                signal2 = signal_names[j]
                
                bbox1 = signal_bboxes[signal1]
                bbox2 = signal_bboxes[signal2]
                
                if bbox1.overlaps(bbox2):
                    self.conflict_graph.add_edge(signal1, signal2, 
                                               conflict_type='bbox_overlap')
    
    def _detect_bounding_box_conflicts_routing(self, routing: RoutingResult):
        """Detects conflicts based on bounding box overlap (Routing)"""
        route_bboxes = {}
        
        # Compute bounding boxes for all routes
        for route in routing.routes:
            bbox = self._calculate_route_bounding_box(route)
            if bbox:
                route_bboxes[route.net_name] = bbox
        
        # Check overlap for each pair of routes
        route_names = list(route_bboxes.keys())
        for i in range(len(route_names)):
            for j in range(i + 1, len(route_names)):
                route1 = route_names[i]
                route2 = route_names[j]
                
                bbox1 = route_bboxes[route1]
                bbox2 = route_bboxes[route2]
                
                if self._bboxes_overlap(bbox1, bbox2):
                    self.conflict_graph.add_edge(route1, route2, 
                                               conflict_type='bbox_overlap')
    
    def _calculate_route_bounding_box(self, route: NetRoute) -> Dict[str, int]:
        """Computes the bounding box for a NetRoute"""
        if not route.segments:
            return None
        
        # Extract all x,y coordinates from the segments
        x_coords = [seg.x for seg in route.segments if seg.x >= 0]
        y_coords = [seg.y for seg in route.segments if seg.y >= 0]
        
        if not x_coords or not y_coords:
            return None
        
        return {
            'min_x': min(x_coords),
            'max_x': max(x_coords),
            'min_y': min(y_coords),
            'max_y': max(y_coords)
        }
    
    def _bboxes_overlap(self, bbox1: Dict[str, int], bbox2: Dict[str, int]) -> bool:
        """Checks whether two bounding boxes overlap"""
        return not (bbox1['max_x'] < bbox2['min_x'] or 
                   bbox1['min_x'] > bbox2['max_x'] or
                   bbox1['max_y'] < bbox2['min_y'] or 
                   bbox1['min_y'] > bbox2['max_y'])
    
    def _detect_routing_conflicts_circuit(self, circuit: Circuit):
        """Detects conflicts based on bounding box overlap"""
        signal_bboxes = {}
        
        # Compute bounding boxes for all signals
        for signal in circuit.get_active_signals():
            signal_bboxes[signal.name] = signal.get_bounding_box()
        
        # Check overlap for each pair of signals
        signal_names = list(signal_bboxes.keys())
        for i in range(len(signal_names)):
            for j in range(i + 1, len(signal_names)):
                signal1 = signal_names[i]
                signal2 = signal_names[j]
                
                bbox1 = signal_bboxes[signal1]
                bbox2 = signal_bboxes[signal2]
                
                if bbox1.overlaps(bbox2):
                    self.conflict_graph.add_edge(signal1, signal2, 
                                               conflict_type='bbox_overlap')
    
    def _detect_routing_conflicts_circuit(self, circuit: Circuit):
        """Detects conflicts based on routing resource sharing (Circuit)"""
        segment_usage = {}
        
        # Group signals by used segments
        for signal in circuit.get_active_signals():
            if signal.route:
                for point in signal.route:
                    segment_key = f"{point.x},{point.y}"
                    if segment_key not in segment_usage:
                        segment_usage[segment_key] = set()
                    segment_usage[segment_key].add(signal.name)
        
        # Add edges for signals that share the same segments
        for segment, signals in segment_usage.items():
            if len(signals) > 1:
                signal_list = list(signals)
                for i in range(len(signal_list)):
                    for j in range(i + 1, len(signal_list)):
                        if not self.conflict_graph.has_edge(signal_list[i], signal_list[j]):
                            self.conflict_graph.add_edge(signal_list[i], signal_list[j],
                                                       conflict_type='shared_segment',
                                                       segment=segment)
    
    def _detect_routing_conflicts_routing(self, routing: RoutingResult):
        """Detects conflicts based on routing resource sharing (Routing)"""
        segment_usage = {}
        
        # Group nets by used segments (x,y coordinates)
        for route in routing.routes:
            if route.segments:
                for segment in route.segments:
                    # Create a key for the segment based on x,y,type
                    segment_key = f"{segment.x},{segment.y},{segment.node_type}"
                    if segment_key not in segment_usage:
                        segment_usage[segment_key] = set()
                    segment_usage[segment_key].add(route.net_name)
        
        # Add edges for nets that share the same segments
        for segment, nets in segment_usage.items():
            if len(nets) > 1:
                net_list = list(nets)
                for i in range(len(net_list)):
                    for j in range(i + 1, len(net_list)):
                        if not self.conflict_graph.has_edge(net_list[i], net_list[j]):
                            self.conflict_graph.add_edge(net_list[i], net_list[j],
                                                       conflict_type='shared_segment',
                                                       segment=segment)
    
    def identify_hubs(self, centrality_threshold: float = 0.1) -> List[str]:
        """Identifies hubs in the conflict graph"""
        if self.conflict_graph.number_of_nodes() == 0:
            return []
        
        # Compute betweenness centrality
        centrality = nx.betweenness_centrality(self.conflict_graph)
        
        # Find nodes with centrality above the threshold
        hubs = [node for node, cent in centrality.items() 
                if cent > centrality_threshold]
        
        return sorted(hubs, key=lambda x: centrality[x], reverse=True)
    
    def get_connected_components(self) -> List[Set[str]]:
        """Returns the connected components of the conflict graph"""
        return list(nx.connected_components(self.conflict_graph))
    
    def calculate_graph_metrics(self) -> Dict[str, float]:
        """Computes conflict graph metrics"""
        if self.conflict_graph.number_of_nodes() == 0:
            return {}
        
        return {
            'num_nodes': self.conflict_graph.number_of_nodes(),
            'num_edges': self.conflict_graph.number_of_edges(),
            'density': nx.density(self.conflict_graph),
            'avg_degree': sum(dict(self.conflict_graph.degree()).values()) / 
                         self.conflict_graph.number_of_nodes(),
            'clustering_coefficient': nx.average_clustering(self.conflict_graph),
            'connected_components': nx.number_connected_components(self.conflict_graph)
        }
    
    def visualize_conflict_graph(self, highlight_hubs: bool = True) -> plt.Figure:
        """Visualizes the conflict graph"""
        fig, ax = plt.subplots(figsize=(12, 8))
        
        if self.conflict_graph.number_of_nodes() == 0:
            ax.text(0.5, 0.5, 'No conflicts detected', 
                   ha='center', va='center', transform=ax.transAxes)
            return fig
        
        # Node positioning
        pos = nx.spring_layout(self.conflict_graph, seed=42)
        
        # Node coloring - hubs are red
        node_colors = []
        hubs = set(self.identify_hubs()) if highlight_hubs else set()
        
        for node in self.conflict_graph.nodes():
            if node in hubs:
                node_colors.append('red')
            else:
                node_colors.append('lightblue')
        
        # Draw the graph
        nx.draw_networkx_nodes(self.conflict_graph, pos, 
                              node_color=node_colors,
                              node_size=500, alpha=0.7, ax=ax)
        
        nx.draw_networkx_edges(self.conflict_graph, pos, 
                              alpha=0.5, edge_color='gray', ax=ax)
        
        nx.draw_networkx_labels(self.conflict_graph, pos, 
                               font_size=8, ax=ax)
        
        # Legend
        if highlight_hubs and hubs:
            ax.plot([], [], 'ro', markersize=8, label='Hubs')
            ax.plot([], [], 'bo', markersize=8, label='Regular nodes')
            ax.legend(loc='upper right')
        
        ax.set_title('Conflict Graph', fontsize=14, pad=20)
        ax.axis('off')
        
        # Add metrics
        metrics = self.calculate_graph_metrics()
        metrics_text = "\n".join([f"{k}: {v:.3f}" for k, v in metrics.items()])
        ax.text(0.02, 0.98, metrics_text, transform=ax.transAxes,
               verticalalignment='top', fontsize=10,
               bbox=dict(boxstyle="round", facecolor='wheat', alpha=0.5))
        
        return fig
    
    def get_conflicts_for_signal(self, signal_name: str) -> List[str]:
        """Returns the signals in conflict with the given signal"""
        if signal_name not in self.conflict_graph:
            return []
        
        return list(self.conflict_graph.neighbors(signal_name))
    
    def export_to_gml(self, filename: str):
        """Exports the conflict graph in GML format"""
        nx.write_gml(self.conflict_graph, filename)