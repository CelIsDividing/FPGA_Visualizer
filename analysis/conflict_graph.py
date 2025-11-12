import networkx as nx
import matplotlib.pyplot as plt
from typing import List, Dict, Tuple, Set, Union
from models.circuit import Circuit, Signal
from models.routing import RoutingResult, NetRoute
from models.fpga_architecture import BoundingBox, Point

class ConflictGraphBuilder:
    """Klasa za građenje i analizu konflikt grafa"""
    
    def __init__(self):
        self.conflict_graph = nx.Graph()
    
    def build_conflict_graph(self, data: Union[Circuit, RoutingResult]) -> nx.Graph:
        """Građi konflikt graf za dato kolo ili routing"""
        self.conflict_graph.clear()
        
        # Proveri tip podataka
        if isinstance(data, RoutingResult):
            return self._build_from_routing(data)
        elif isinstance(data, Circuit):
            return self._build_from_circuit(data)
        else:
            raise ValueError(f"Unsupported data type: {type(data)}")
    
    def _build_from_circuit(self, circuit: Circuit) -> nx.Graph:
        """Građi konflikt graf iz Circuit objekta (legacy)"""
        # Dodavanje svih aktivnih signala kao čvorova
        active_signals = circuit.get_active_signals()
        for signal in active_signals:
            self.conflict_graph.add_node(signal.name, signal=signal)
        
        # Detekcija konflikata baziranih na bounding box preklapanju
        self._detect_bounding_box_conflicts_circuit(circuit)
        
        # Detekcija konflikata baziranih na deljenju routing resursa
        self._detect_routing_conflicts_circuit(circuit)
        
        return self.conflict_graph
    
    def _build_from_routing(self, routing: RoutingResult) -> nx.Graph:
        """Građi konflikt graf iz Routing objekta"""
        # Dodavanje svih net-ova kao čvorova
        for route in routing.routes:
            self.conflict_graph.add_node(route.net_name, route=route)
        
        # Detekcija konflikata baziranih na bounding box preklapanju
        self._detect_bounding_box_conflicts_routing(routing)
        
        # Detekcija konflikata baziranih na deljenju routing resursa
        self._detect_routing_conflicts_routing(routing)
        
        return self.conflict_graph
    
    def _detect_bounding_box_conflicts_circuit(self, circuit: Circuit):
        """Detektuje konflikte bazirane na preklapanju bounding box-ova (Circuit)"""
        signal_bboxes = {}
        
        # Računanje bounding box-ova za sve signale
        for signal in circuit.get_active_signals():
            signal_bboxes[signal.name] = signal.get_bounding_box()
        
        # Provera preklapanja za svaki par signala
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
        """Detektuje konflikte bazirane na preklapanju bounding box-ova (Routing)"""
        route_bboxes = {}
        
        # Računanje bounding box-ova za sve route-ove
        for route in routing.routes:
            bbox = self._calculate_route_bounding_box(route)
            if bbox:
                route_bboxes[route.net_name] = bbox
        
        # Provera preklapanja za svaki par route-ova
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
        """Izračunava bounding box za NetRoute"""
        if not route.segments:
            return None
        
        # Izvuci sve x,y koordinate iz segmenata
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
        """Proverava da li se dva bounding box-a preklapaju"""
        return not (bbox1['max_x'] < bbox2['min_x'] or 
                   bbox1['min_x'] > bbox2['max_x'] or
                   bbox1['max_y'] < bbox2['min_y'] or 
                   bbox1['min_y'] > bbox2['max_y'])
    
    def _detect_routing_conflicts_circuit(self, circuit: Circuit):
        """Detektuje konflikte bazirane na preklapanju bounding box-ova"""
        signal_bboxes = {}
        
        # Računanje bounding box-ova za sve signale
        for signal in circuit.get_active_signals():
            signal_bboxes[signal.name] = signal.get_bounding_box()
        
        # Provera preklapanja za svaki par signala
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
        """Detektuje konflikte bazirane na deljenju routing resursa (Circuit)"""
        segment_usage = {}
        
        # Grupisanje signala po korišćenim segmentima
        for signal in circuit.get_active_signals():
            if signal.route:
                for point in signal.route:
                    segment_key = f"{point.x},{point.y}"
                    if segment_key not in segment_usage:
                        segment_usage[segment_key] = set()
                    segment_usage[segment_key].add(signal.name)
        
        # Dodavanje grana za signale koji dele iste segmente
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
        """Detektuje konflikte bazirane na deljenju routing resursa (Routing)"""
        segment_usage = {}
        
        # Grupisanje net-ova po korišćenim segmentima (x,y koordinatama)
        for route in routing.routes:
            if route.segments:
                for segment in route.segments:
                    # Kreiraj ključ za segment baziran na x,y,type
                    segment_key = f"{segment.x},{segment.y},{segment.node_type}"
                    if segment_key not in segment_usage:
                        segment_usage[segment_key] = set()
                    segment_usage[segment_key].add(route.net_name)
        
        # Dodavanje grana za net-ove koji dele iste segmente
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
        """Identifikuje habove u konflikt grafu"""
        if self.conflict_graph.number_of_nodes() == 0:
            return []
        
        # Računanje betweenness centrality
        centrality = nx.betweenness_centrality(self.conflict_graph)
        
        # Pronalaženje čvorova sa centralnošću iznad thresholda
        hubs = [node for node, cent in centrality.items() 
                if cent > centrality_threshold]
        
        return sorted(hubs, key=lambda x: centrality[x], reverse=True)
    
    def get_connected_components(self) -> List[Set[str]]:
        """Vraća povezane komponente konflikt grafa"""
        return list(nx.connected_components(self.conflict_graph))
    
    def calculate_graph_metrics(self) -> Dict[str, float]:
        """Računa metriku konflikt grafa"""
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
        """Vizuelizuje konflikt graf"""
        fig, ax = plt.subplots(figsize=(12, 8))
        
        if self.conflict_graph.number_of_nodes() == 0:
            ax.text(0.5, 0.5, 'No conflicts detected', 
                   ha='center', va='center', transform=ax.transAxes)
            return fig
        
        # Pozicioniranje čvorova
        pos = nx.spring_layout(self.conflict_graph, seed=42)
        
        # Bojenje čvorova - habovi su crveni
        node_colors = []
        hubs = set(self.identify_hubs()) if highlight_hubs else set()
        
        for node in self.conflict_graph.nodes():
            if node in hubs:
                node_colors.append('red')
            else:
                node_colors.append('lightblue')
        
        # Crtanje grafa
        nx.draw_networkx_nodes(self.conflict_graph, pos, 
                              node_color=node_colors,
                              node_size=500, alpha=0.7, ax=ax)
        
        nx.draw_networkx_edges(self.conflict_graph, pos, 
                              alpha=0.5, edge_color='gray', ax=ax)
        
        nx.draw_networkx_labels(self.conflict_graph, pos, 
                               font_size=8, ax=ax)
        
        # Legenda
        if highlight_hubs and hubs:
            ax.plot([], [], 'ro', markersize=8, label='Hubs')
            ax.plot([], [], 'bo', markersize=8, label='Regular nodes')
            ax.legend(loc='upper right')
        
        ax.set_title('Conflict Graph', fontsize=14, pad=20)
        ax.axis('off')
        
        # Dodavanje metrika
        metrics = self.calculate_graph_metrics()
        metrics_text = "\n".join([f"{k}: {v:.3f}" for k, v in metrics.items()])
        ax.text(0.02, 0.98, metrics_text, transform=ax.transAxes,
               verticalalignment='top', fontsize=10,
               bbox=dict(boxstyle="round", facecolor='wheat', alpha=0.5))
        
        return fig
    
    def get_conflicts_for_signal(self, signal_name: str) -> List[str]:
        """Vraća signale u konfliktu sa datim signalom"""
        if signal_name not in self.conflict_graph:
            return []
        
        return list(self.conflict_graph.neighbors(signal_name))
    
    def export_to_gml(self, filename: str):
        """Izvozi konflikt graf u GML format"""
        nx.write_gml(self.conflict_graph, filename)