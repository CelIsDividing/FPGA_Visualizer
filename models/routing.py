from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from .fpga_architecture import FPGAArchitecture
from .circuit import Circuit

class RouteSegment:
    """Čvor u routing stablu (ne samo segment!)"""
    def __init__(self, 
                 node_id: int = 0,
                 node_type: str = '',
                 x: int = -1,
                 y: int = -1,
                 track: int = 0,
                 switch_id: int = 0,
                 pad: int = -1,
                 **kwargs: Any):
        # Osnovni VPR atributi
        self.node_id = node_id
        self.node_type = node_type  # SOURCE, OPIN, CHANX, CHANY, IPIN, SINK
        self.x = x
        self.y = y
        self.track = track
        self.switch_id = switch_id
        self.pad = pad
        
        # Tree struktura
        self.children: List['RouteSegment'] = []
        self.parent: Optional['RouteSegment'] = None
        
        # Legacy polja (za kompatibilnost)
        self.channel_id = kwargs.get('channel_id', 0)
        self.offset = kwargs.get('offset', 0)
        
        # Dodatni atributi (Pad, Pin, Layer, ...)
        for k, v in kwargs.items():
            if k not in ('node_id', 'node_type', 'x', 'y', 'track', 'switch_id', 
                        'channel_id', 'offset', 'pad'):
                setattr(self, k, v)
    
    def is_io_pad(self) -> bool:
        """Da li je IO pad (SOURCE/SINK sa Pad oznakom)"""
        return self.pad >= 0
    
    def add_child(self, child: 'RouteSegment'):
        """Dodaj dete čvor u stablo"""
        self.children.append(child)
        child.parent = self
    
    def is_leaf(self) -> bool:
        """Da li je list (SINK čvor)"""
        return len(self.children) == 0 and self.node_type == 'SINK'
    
    def is_root(self) -> bool:
        """Da li je koren (SOURCE čvor)"""
        return self.parent is None and self.node_type == 'SOURCE'
    
    def get_path_to_root(self) -> List['RouteSegment']:
        """Vraća putanju od ovog čvora do korena"""
        path = [self]
        current = self.parent
        while current:
            path.append(current)
            current = current.parent
        return list(reversed(path))
    
    def get_all_paths_to_leaves(self) -> List[List['RouteSegment']]:
        """Rekurzivno vraća sve putanje od ovog čvora do listova"""
        if self.is_leaf():
            return [[self]]
        
        all_paths = []
        for child in self.children:
            child_paths = child.get_all_paths_to_leaves()
            for path in child_paths:
                all_paths.append([self] + path)
        
        return all_paths
    
    def to_dict(self, include_children: bool = False) -> Dict[str, Any]:
        """Serijalizacija u dict"""
        result = {
            'node_id': self.node_id,
            'node_type': self.node_type,
            'x': self.x,
            'y': self.y,
            'track': self.track,
            'switch_id': self.switch_id,
            'channel_id': self.channel_id,
            'offset': self.offset,
            'pad': self.pad
        }
        
        # Dodaj sve custom atribute
        for k, v in self.__dict__.items():
            if k not in result and k not in ('children', 'parent'):
                result[k] = v
        
        if include_children:
            result['children'] = [c.to_dict(include_children=True) 
                                 for c in self.children]
        
        return result


class NetRoute:
    """Routing stablo za jedan net"""
    def __init__(self, 
                 net_name: str = "", 
                 segments: List[RouteSegment] = None,
                 root: Optional[RouteSegment] = None,
                 **kwargs: Any):
        self.net_name = net_name
        
        # NOVO: root čvor (SOURCE)
        self.root = root
        
        # segments = flat list (za legacy)
        self.segments = segments if segments is not None else []
        
        # dodatni atributi
        for k, v in kwargs.items():
            setattr(self, k, v)
    
    def build_tree_from_segments(self):
        """Konvertuje linearnu listu segmenata u stablo koristeći VPR routing semantiku"""
        if not self.segments:
            return
        
        # Pronađi SOURCE čvor
        source = next((s for s in self.segments if s.node_type == 'SOURCE'), None)
        if not source:
            return
        
        self.root = source
        
        # VPR .route files list segments in order, but branches are indicated by
        # repeating a node and then listing the branch segments
        # For example, Net 10 has node 1691 (CHANY 5,5) appearing twice - 
        # once in main path, once as branch point
        
        # Build tree by parsing segments sequentially, but handle branches properly
        self._build_vpr_tree_sequential()
    
    def _build_vpr_tree_sequential(self):
        """Build tree from VPR route file sequential format"""
        if len(self.segments) < 2:
            return
            
        # Create node map for fast lookup
        node_map = {}
        for seg in self.segments:
            if seg.node_id not in node_map:
                node_map[seg.node_id] = []
            node_map[seg.node_id].append(seg)
        
        # Track which nodes have been processed
        processed_nodes = set()
        
        # Start with root
        current_parent = self.root
        processed_nodes.add(self.root.node_id)
        
        i = 1  # Start from second segment (first is SOURCE)
        
        while i < len(self.segments):
            seg = self.segments[i]
            
            # If this node ID was already processed, it's a branch point
            if seg.node_id in processed_nodes:
                # Find the previously processed node with this ID
                branch_point = self._find_node_in_tree(self.root, seg.node_id)
                if branch_point:
                    current_parent = branch_point
                    print(f"🌿 Branch detected at Node {seg.node_id} ({seg.node_type} {seg.x},{seg.y})")
                i += 1
                continue
            
            # Add this segment to the current parent
            current_parent.add_child(seg)
            processed_nodes.add(seg.node_id)
            
            # Move to this node as the new parent (unless it's a SINK)
            if seg.node_type != 'SINK':
                current_parent = seg
            else:
                # SINK ends a path, go back to find the branch point for next path
                # Look ahead to see if next segment is a repeat (branch indicator)
                if i + 1 < len(self.segments):
                    next_seg = self.segments[i + 1]
                    if next_seg.node_id in processed_nodes:
                        # Next is a branch, don't change current_parent yet
                        pass
                    else:
                        # Find appropriate parent for next segment
                        current_parent = self._find_appropriate_parent_for_next_segment(i + 1)
            
            i += 1
    
    def _find_node_in_tree(self, root: 'RouteSegment', node_id: int) -> Optional['RouteSegment']:
        """Recursively find a node with given ID in the tree"""
        if root.node_id == node_id:
            return root
        
        for child in root.children:
            result = self._find_node_in_tree(child, node_id)
            if result:
                return result
        
        return None
    
    def _find_appropriate_parent_for_next_segment(self, next_index: int) -> 'RouteSegment':
        """Find the appropriate parent for the next segment in sequence"""
        if next_index >= len(self.segments):
            return self.root
        
        next_seg = self.segments[next_index]
        
        # If next segment is a routing channel, find the last routing node
        # that could logically connect to it
        if next_seg.node_type in ['CHANX', 'CHANY']:
            # Look for a routing node that could connect
            candidate = self._find_routing_connection_point(next_seg)
            if candidate:
                return candidate
        
        # Default to root if no better parent found
        return self.root
    
    def _find_routing_connection_point(self, target_seg: 'RouteSegment') -> Optional['RouteSegment']:
        """Find a node in the tree that could logically connect to target segment"""
        def search_tree(node: 'RouteSegment') -> Optional['RouteSegment']:
            # Check if this node could connect to target
            if (node.node_type in ['CHANX', 'CHANY', 'OPIN'] and
                self._is_adjacent_or_same(node, target_seg)):
                return node
            
            # Search children
            for child in node.children:
                result = search_tree(child)
                if result:
                    return result
            
            return None
        
        return search_tree(self.root)
    
    def _build_tree_recursive(self, current_node: 'RouteSegment', node_map: Dict[int, 'RouteSegment'], visited: set):
        """Rekurzivno gradi stablo na osnovu routing logike"""
        visited.add(current_node.node_id)
        
        # Pronađi sledeće čvorove na osnovu routing sekvence
        next_nodes = self._find_next_nodes(current_node, node_map, visited)
        
        for next_node in next_nodes:
            if next_node.node_id not in visited:
                current_node.add_child(next_node)
                self._build_tree_recursive(next_node, node_map, visited)
    
    def _find_next_nodes(self, current: 'RouteSegment', node_map: Dict[int, 'RouteSegment'], visited: set) -> List['RouteSegment']:
        """Pronalazi sledeće čvorove u routing sekvenci"""
        next_nodes = []
        
        # Za SOURCE, traži OPIN na istoj lokaciji
        if current.node_type == 'SOURCE':
            for node in node_map.values():
                if (node.node_type == 'OPIN' and 
                    node.x == current.x and node.y == current.y and
                    node.node_id not in visited):
                    next_nodes.append(node)
        
        # Za OPIN, traži CHANX/CHANY koji počinje rutiranje
        elif current.node_type == 'OPIN':
            for node in node_map.values():
                if (node.node_type in ['CHANX', 'CHANY'] and
                    node.node_id not in visited and
                    self._is_adjacent_or_same(current, node)):
                    next_nodes.append(node)
        
        # Za CHANX/CHANY, traži sledeći routing čvor ili IPIN
        elif current.node_type in ['CHANX', 'CHANY']:
            for node in node_map.values():
                if (node.node_id not in visited and
                    (node.node_type in ['CHANX', 'CHANY', 'IPIN'] and
                     self._is_routing_continuation(current, node))):
                    next_nodes.append(node)
        
        # Za IPIN, traži SINK na istoj lokaciji
        elif current.node_type == 'IPIN':
            for node in node_map.values():
                if (node.node_type == 'SINK' and
                    node.x == current.x and node.y == current.y and
                    node.node_id not in visited):
                    next_nodes.append(node)
        
        return next_nodes
    
    def _is_adjacent_or_same(self, node1: 'RouteSegment', node2: 'RouteSegment') -> bool:
        """Proverava da li su čvorovi susedni ili na istoj lokaciji"""
        dx = abs(node1.x - node2.x)
        dy = abs(node1.y - node2.y)
        return (dx <= 1 and dy <= 1)
    
    def _is_routing_continuation(self, current: 'RouteSegment', next_node: 'RouteSegment') -> bool:
        """Proverava da li je next_node logičko produženje routing putanje"""
        # CHANX se kreće horizontalno (x menja, y ostaje isto ili +-1)
        # CHANY se kreće vertikalno (y menja, x ostaje isto ili +-1)
        
        if current.node_type == 'CHANX':
            if next_node.node_type == 'CHANY':
                # Prelaz sa horizontalnog na vertikalni kanal
                return abs(current.x - next_node.x) <= 1 and abs(current.y - next_node.y) <= 1
            elif next_node.node_type == 'CHANX':
                # Horizontalni nastavak
                return current.y == next_node.y and abs(current.x - next_node.x) == 1
            elif next_node.node_type == 'IPIN':
                # Kraj routing-a - ulaz u CLB
                return abs(current.x - next_node.x) <= 1 and abs(current.y - next_node.y) <= 1
        
        elif current.node_type == 'CHANY':
            if next_node.node_type == 'CHANX':
                # Prelaz sa vertikalnog na horizontalni kanal
                return abs(current.x - next_node.x) <= 1 and abs(current.y - next_node.y) <= 1
            elif next_node.node_type == 'CHANY':
                # Vertikalni nastavak
                return current.x == next_node.x and abs(current.y - next_node.y) == 1
            elif next_node.node_type == 'IPIN':
                # Kraj routing-a - ulaz u CLB
                return abs(current.x - next_node.x) <= 1 and abs(current.y - next_node.y) <= 1
        
        return False
    
    def get_all_source_to_sink_paths(self) -> List[List[RouteSegment]]:
        """Vraća sve putanje od SOURCE do svih SINK-ova"""
        if not self.root:
            return []
        return self.root.get_all_paths_to_leaves()
    
    def get_path_coordinates(self) -> List[List[tuple]]:
        """Vraća koordinate svih putanja (za vizuelizaciju)"""
        paths = self.get_all_source_to_sink_paths()
        return [
            [(seg.x, seg.y) for seg in path]
            for path in paths
        ]

    def to_dict(self, include_tree: bool = True) -> Dict[str, Any]:
        """Serijalizacija sa tree strukturom"""
        extra = {k: v for k, v in self.__dict__.items() 
                if k not in ("net_name", "segments", "root")}
        
        result = {
            "net_name": self.net_name,
            "segments": [s.to_dict() for s in self.segments],
            **extra
        }
        
        if include_tree and self.root:
            result['tree'] = self.root.to_dict(include_children=True)
            result['paths'] = self.get_path_coordinates()
        
        return result


class RoutingResult:
    def __init__(self,
                 routes: List[NetRoute] = None,
                 congestion: Dict[str, float] = None,
                 metadata: Dict[str, Any] = None,
                 circuit: Optional[Circuit] = None,
                 architecture: Optional[FPGAArchitecture] = None,
                 successful: bool = False,
                 total_wire_length: float = 0.0,
                 iteration_count: int = 0,
                 timing_data: Dict[str, float] = None,
                 **kwargs: Any):
        self.routes = routes if routes is not None else []
        self.congestion = congestion if congestion is not None else {}
        self.metadata = metadata if metadata is not None else {}
        self.circuit = circuit
        self.architecture = architecture
        self.successful = successful
        self.total_wire_length = total_wire_length
        self.iteration_count = iteration_count
        self.timing_data = timing_data if timing_data is not None else {}
        # prihvati dodatne atribute iz parsera (npr. iteration, stats)
        for k, v in kwargs.items():
            setattr(self, k, v)

    def calculate_congestion_metrics(self) -> Dict[str, float]:
        """Računa različite metrike zagušenja"""
        if not self.congestion:
            return {}

        congestion_values = list(self.congestion.values())

        return {
            'max_congestion': max(congestion_values) if congestion_values else 0.0,
            'avg_congestion': sum(congestion_values) / len(congestion_values) if congestion_values else 0.0,
            'min_congestion': min(congestion_values) if congestion_values else 0.0,
            'congested_segments': len([v for v in congestion_values if v > 0.8]),
            'total_segments': len(congestion_values)
        }

    def get_high_congestion_segments(self, threshold: float = 0.8) -> List[str]:
        """Vraća segmente sa visokim zagušenjem"""
        return [segment for segment, congestion in self.congestion.items()
                if congestion > threshold]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'routes': [r.to_dict() for r in self.routes],
            'congestion': dict(self.congestion),
            'metadata': dict(self.metadata),
            'successful': self.successful,
            'total_wire_length': self.total_wire_length,
            'iteration_count': self.iteration_count,
            'timing_data': dict(self.timing_data)
        }
    
    def get_route_statistics(self) -> Dict[str, Any]:
        """Statistika routing stabala"""
        stats = {
            'total_nets': len(self.routes),
            'total_segments': sum(len(r.segments) for r in self.routes),
            'nets_with_branches': 0,
            'max_fanout': 0,
            'avg_path_length': 0.0
        }
        
        total_paths = 0
        total_path_length = 0
        
        for route in self.routes:
            if route.root:
                paths = route.get_all_source_to_sink_paths()
                fanout = len(paths)
                
                if fanout > 1:
                    stats['nets_with_branches'] += 1
                
                stats['max_fanout'] = max(stats['max_fanout'], fanout)
                
                for path in paths:
                    total_paths += 1
                    total_path_length += len(path)
        
        if total_paths > 0:
            stats['avg_path_length'] = total_path_length / total_paths
        
        return stats