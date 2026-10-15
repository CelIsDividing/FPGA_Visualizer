import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Tuple, Set, Optional, Any
import re
import traceback
import xml.etree.ElementTree as ET

from flask import json
from models.routing import NetRoute, RouteSegment, RoutingResult
from models.fpga_architecture import FPGAArchitecture
from models.circuit import Circuit, Point, Signal, Component

class RoutingParser:
    """Parser for VTR routing files (.route) and RRG files"""
    
    def __init__(self):
        self.net_pattern = re.compile(r'Net\s+(\d+)\s+\((.+?)\)')
        self.route_segment_pattern = re.compile(r'(\d+)\s+(\d+)\s+(\d+)\s+(\d+)')
    
    def parse_routing_file(self, filepath: str, 
                      architecture: FPGAArchitecture, 
                      circuit: Optional[Circuit] = None) -> RoutingResult:
        """
        Parse VPR .route file with format:
        Net 0 (c0)
        Node:	547	SOURCE (4,0,0)  Pad: 7  Switch: 0
        Node:	556	  OPIN (4,0,0)  Pad: 7  Switch: 2
        Node:	1108	 CHANX (4,0,0)  Track: 4  Switch: 2
        """
        try:
            routes = []
            congestion = {}
            
            print("=" * 60)
            print("🔍 Starting .route file parsing...")
            
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            current_net_name = None
            current_segments = []
            
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                
                if not line or line.startswith('#') or line.startswith('Placement_File:') or line.startswith('Array size:') or line == 'Routing:':
                    continue
                
                net_match = self.net_pattern.match(line)
                if net_match:
                    if current_net_name and current_segments:
                        route = NetRoute(
                            net_name=current_net_name,
                            segments=current_segments
                        )
                        route.build_tree_from_segments()
                        routes.append(route)
                        
                        print(f"✅ Net '{current_net_name}': {len(current_segments)} segments")
                        if route.root:
                            paths = route.get_all_source_to_sink_paths()
                            print(f"   🌳 Tree built: {len(paths)} paths to SINK")
                    
                    net_id = net_match.group(1)
                    current_net_name = net_match.group(2)
                    current_segments = []
                    print(f"\n📌 Starting Net {net_id} ({current_net_name})")
                    continue
                
                if line.startswith("Node:"):
                    seg = self._parse_node_line(line, line_num)
                    if seg:
                        current_segments.append(seg)
                        
                        if seg.node_type in ['CHANX', 'CHANY']:
                            key = f"{seg.node_type}_{seg.x}_{seg.y}_{seg.track}"
                            congestion[key] = congestion.get(key, 0) + 1
            
            if current_net_name and current_segments:
                route = NetRoute(
                    net_name=current_net_name,
                    segments=current_segments
                )
                route.build_tree_from_segments()
                routes.append(route)
                
                print(f"✅ Net '{current_net_name}': {len(current_segments)} segments")
                if route.root:
                    paths = route.get_all_source_to_sink_paths()
                    print(f"   🌳 Tree built: {len(paths)} paths to SINK")
            
            print("=" * 60)
            print(f"🎯 PARSING COMPLETE: {len(routes)} nets parsed")
            
            stats = self._calculate_tree_statistics(routes)
            print(f"📊 Tree Statistics:")
            print(f"   - Nets with branches: {stats['nets_with_branches']}")
            print(f"   - Max fanout: {stats['max_fanout']}")
            print(f"   - Avg path length: {stats['avg_path_length']:.2f}")
            print("=" * 60)
            
            if congestion:
                max_cong = max(congestion.values())
                congestion = {k: v/max_cong for k, v in congestion.items()}
            
            return RoutingResult(
                routes=routes,
                congestion=congestion,
                architecture=architecture,
                circuit=circuit,
                successful=True,
                total_wire_length=sum(len(route.segments) for route in routes)
            )
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise ValueError(f"Failed to parse routing file: {str(e)}")
    
    def _parse_node_line(self, line: str, line_num: int) -> Optional[RouteSegment]:
        """
        Parse: Node:	547	SOURCE (4,0,0)  Pad: 7  Switch: 0
        """
        try:
            line = line.replace('Switch::', 'Switch:')  
            line = line.replace('Track::', 'Track:')    
            line = line.replace('Pad::', 'Pad:')        
            
            parts = line.replace('Node:', '').split()
        
            if len(parts) < 3:
                return None
            
            node_id = int(parts[0])
            node_type = parts[1].upper()
            
            # Parse coordinates (x,y) or (x,y,z)
            coord_str = parts[2].strip('()')
            coords = coord_str.split(',')
            x = int(coords[0]) if len(coords) > 0 else -1
            y = int(coords[1]) if len(coords) > 1 else -1
            
            # Extract track number
            track = 0
            switch_id = 0

            # Search all "Keyword: Value" pairs
            i = 3
            while i < len(parts):
                key = parts[i].rstrip(':').lower()
                
                if i + 1 >= len(parts):
                    break
                
                value_str = parts[i + 1]
                
                try:
                    if key == 'track':
                        track = int(value_str)
                        i += 2
                        continue
                    elif key == 'switch':
                        switch_id = int(value_str)
                        i += 2
                        continue
                except ValueError:
                    pass  # Skip if not a number
                
                i += 1
            
            extra_attrs = {}
            i = 3
            while i < len(parts):
                if parts[i].endswith(':') and i + 1 < len(parts):
                    key = parts[i].rstrip(':').lower()
                    
                    if key in ['track', 'switch']:
                        i += 2
                        continue
                    
                    try:
                        value = int(parts[i + 1])
                        extra_attrs[key] = value
                    except ValueError:
                        extra_attrs[key] = parts[i + 1]
                    
                    i += 2
                else:
                    i += 1
            
            seg = RouteSegment(
                node_id=node_id,
                node_type=node_type,
                x=x,
                y=y,
                track=track,
                switch_id=switch_id,
                **extra_attrs  # Pad, Pin, Class, ...
            )
            
            # Debug: IO pad detection
            if node_type in ['SOURCE', 'SINK', 'OPIN', 'IPIN'] and hasattr(seg, 'pad') and seg.pad >= 0:
                print(f"    🔌 IO PAD detected: Node {node_id} has pad={seg.pad}")
            
            track_str = f"trk={track}" if track >= 0 else ""
            switch_str = f"sw={switch_id}" if switch_id != 0 else ""
            print(f"    Node {node_id:4d}: {node_type:6s} ({x},{y}) {track_str} {switch_str}")
            
            return seg
            
        except Exception as e:
            print(f"⚠️ Line {line_num}: Error parsing '{line[:80]}...' - {e}")
            return None
        
    def _parse_placement_info(self, content: str, routing_result: RoutingResult):
        """Parses placement information from the header"""
        lines = content.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Parsing array dimensions
            placement_match = self.placement_pattern.search(line)
            if placement_match:
                width = int(placement_match.group(1))
                height = int(placement_match.group(2))
                routing_result.placement_dimensions = (width, height)
                break
    
    def _parse_net_routes(self, content: str, circuit: Circuit):
        """Parses routes for each net in the .route file"""
        lines = content.split('\n')
        current_net = None
        current_route = []
        
        for line in lines:
            line = line.strip()
            
            # Start of a new net
            net_match = self.net_pattern.match(line)
            if net_match:
                # Save the previous net if it exists
                if current_net and current_route:
                    self._process_net_route(current_net, current_route, circuit)
                
                # Start a new net
                net_id = net_match.group(1)
                net_name = net_match.group(2)
                current_net = (net_id, net_name)
                current_route = []
                continue
            
            # Parsing nodes in the route
            node_match = self.node_pattern.match(line)
            if node_match and current_net:
                node_id = node_match.group(1)
                node_type = node_match.group(2)
                location_str = node_match.group(3)
                
                # Parsing coordinates
                coord_match = self.coord_pattern.search(location_str)
                if coord_match:
                    x = int(coord_match.group(1))
                    y = int(coord_match.group(2))
                    layer = int(coord_match.group(3))
                    
                    node_info = {
                        'id': node_id,
                        'type': node_type,
                        'x': x,
                        'y': y,
                        'layer': layer,
                        'raw_line': line
                    }
                    
                    # Parsing additional information
                    track_match = self.track_pattern.search(line)
                    if track_match:
                        node_info['track'] = int(track_match.group(1))
                    
                    pin_match = self.pin_pattern.search(line)
                    if pin_match:
                        node_info['pin_num'] = int(pin_match.group(1))
                        node_info['pin_name'] = pin_match.group(2)
                    
                    current_route.append(node_info)
        
        # Process the last net
        if current_net and current_route:
            self._process_net_route(current_net, current_route, circuit)
    
    def _process_net_route(self, net_info: tuple, route_nodes: List[Dict], circuit: Circuit):
        """Processes the route of a single net and creates the corresponding signal"""
        net_id, net_name = net_info
        
        # Find or create the signal
        signal = circuit.get_signal(net_name)
        if not signal:
            signal = Signal(name=net_name)
            circuit.add_signal(signal)
        
        # Set the signal route
        signal.route = []
        source_node = None
        sink_nodes = []
        
        for node in route_nodes:
            point = Point(node['x'], node['y'])
            signal.route.append(point)
            
            # Identify source and sink nodes
            if node['type'] == 'SOURCE':
                signal.source = point
                source_node = node
            elif node['type'] == 'SINK':
                sink_nodes.append(node)
        
        # If there is no explicit SINK, use the last point
        if not signal.destination and signal.route:
            signal.destination = signal.route[-1]
        
        # Calculate the route length
        signal.calculate_length()
        
        # Add metadata about the net
        signal.metadata = {
            'net_id': net_id,
            'node_count': len(route_nodes),
            'source_node': source_node,
            'sink_nodes': sink_nodes
        }
    
    def _analyze_route_congestion(self, content: str, architecture: FPGAArchitecture) -> Dict[str, float]:
        """Analyzes congestion based on the parsed routes"""
        congestion_map = {}
        segment_usage = {}
        
        # Parsing all nodes from the .route file
        lines = content.split('\n')
        
        for line in lines:
            line = line.strip()
            node_match = self.node_pattern.match(line)
            if node_match:
                node_type = node_match.group(2)
                location_str = node_match.group(3)
                
                # We focus on routing nodes (CHANX, CHANY)
                if node_type in ['CHANX', 'CHANY']:
                    coord_match = self.coord_pattern.search(location_str)
                    if coord_match:
                        x = int(coord_match.group(1))
                        y = int(coord_match.group(2))
                        
                        # Parsing the track number
                        track_match = self.track_pattern.search(line)
                        if track_match:
                            track = int(track_match.group(1))
                            segment_key = f"{node_type}_{x}_{y}_{track}"
                        else:
                            segment_key = f"{node_type}_{x}_{y}"
                        
                        segment_usage[segment_key] = segment_usage.get(segment_key, 0) + 1
        
        # Computing congestion
        if segment_usage:
            max_usage = max(segment_usage.values())
            for segment_key, usage in segment_usage.items():
                congestion_map[segment_key] = min(1.0, usage / max_usage)
        
        return congestion_map
    
    def _parse_timing_info(self, content: str, routing_result: RoutingResult):
        """Parses execution time information if available"""
        lines = content.split('\n')
        
        for line in lines:
            line = line.strip().lower()
            
            if 'routing time' in line:
                # Try to extract the time
                time_parts = line.split(':')
                if len(time_parts) > 1:
                    time_str = time_parts[1].strip()
                    # Try to convert to float
                    try:
                        # Remove non-numeric characters except the decimal point
                        time_clean = ''.join(c for c in time_str if c.isdigit() or c == '.')
                        if time_clean:
                            routing_time = float(time_clean)
                            routing_result.timing_data['total_routing_time'] = routing_time
                    except ValueError:
                        pass
    
    def parse_rrg_file(self, file_path: str, architecture: FPGAArchitecture, 
                      circuit: Circuit) -> RoutingResult:
        """Parses a VTR RRG file for routing resources"""
        routing_result = RoutingResult(circuit=circuit, architecture=architecture)
        
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            
            # Parsing rr_nodes
            self._parse_rr_nodes(root, circuit)
            
            # Parsing rr_edges for connections
            self._parse_rr_edges(root, circuit)
            
            # Analyzing congestion based on capacity and usage
            congestion_map = self._analyze_rrg_congestion(root, architecture)
            routing_result.congestion_map = congestion_map
            
            # Computing total wire length
            routing_result.total_wire_length = circuit.calculate_total_wire_length()
            
            routing_result.successful = True
            
        except Exception as e:
            raise ValueError(f"Error parsing RRG file: {e}")
        
        return routing_result
    
    def _parse_rr_nodes(self, root: ET.Element, circuit: Circuit):
        """Parses the rr_nodes section from the RRG file"""
        rr_nodes_element = root.find('rr_nodes')
        if rr_nodes_element is None:
            return
        
        for node_elem in rr_nodes_element.findall('node'):
            node_id = int(node_elem.get('id', '0'))
            node_type = node_elem.get('type', '')
            capacity = int(node_elem.get('capacity', '1'))
            
            # Parsing the location
            loc_elem = node_elem.find('loc')
            if loc_elem is not None:
                x = int(loc_elem.get('xlow', '0'))
                y = int(loc_elem.get('ylow', '0'))
                ptc = int(loc_elem.get('ptc', '0'))
                
                # Creating signals for relevant node types
                if node_type in ['SOURCE', 'OPIN']:
                    signal_name = f"node_{node_id}_{node_type}"
                    signal = circuit.get_signal(signal_name)
                    if not signal:
                        signal = Signal(name=signal_name)
                        circuit.add_signal(signal)
                    
                    signal.source = Point(x, y)
                    signal.route.append(Point(x, y))
                
                elif node_type in ['SINK', 'IPIN']:
                    signal_name = f"node_{node_id}_{node_type}" 
                    signal = circuit.get_signal(signal_name)
                    if not signal:
                        signal = Signal(name=signal_name)
                        circuit.add_signal(signal)
                    
                    signal.destination = Point(x, y)
                    if not signal.route:
                        signal.route.append(Point(x, y))
                    else:
                        signal.route[-1] = Point(x, y)  # Updating destination
    
    def _parse_rr_edges(self, root: ET.Element, circuit: Circuit):
        """Parses the rr_edges section for connections between nodes"""
        rr_edges_element = root.find('rr_edges')
        if rr_edges_element is None:
            return
        
        # First we collect all edges
        edges = []
        for edge_elem in rr_edges_element.findall('edge'):
            src_node = int(edge_elem.get('src_node', '0'))
            sink_node = int(edge_elem.get('sink_node', '0'))
            switch_id = int(edge_elem.get('switch_id', '0'))
            edges.append((src_node, sink_node, switch_id))
        
        # Linking signals based on edges
        for src_node, sink_node, switch_id in edges:
            src_signal_name = f"node_{src_node}_SOURCE"
            sink_signal_name = f"node_{sink_node}_SINK"
            
            # Try to find and link the signals
            src_signal = circuit.get_signal(src_signal_name)
            sink_signal = circuit.get_signal(sink_signal_name)
            
            if src_signal and sink_signal:
                # Merging signals
                sink_signal.source = src_signal.source
                if src_signal.route:
                    sink_signal.route = src_signal.route.copy()
    
    def _analyze_rrg_congestion(self, root: ET.Element, architecture: FPGAArchitecture) -> Dict[str, float]:
        """Analyzes congestion based on RRG nodes"""
        congestion_map = {}
        
        # Analysis of routing resource usage
        rr_nodes_element = root.find('rr_nodes')
        if rr_nodes_element is None:
            return congestion_map
        
        # Counting nodes by locations
        location_usage = {}
        for node_elem in rr_nodes_element.findall('node'):
            loc_elem = node_elem.find('loc')
            if loc_elem is not None:
                x = int(loc_elem.get('xlow', '0'))
                y = int(loc_elem.get('ylow', '0'))
                capacity = int(node_elem.get('capacity', '1'))
                
                location_key = f"{x},{y}"
                location_usage[location_key] = location_usage.get(location_key, 0) + 1
        
        # Computing congestion
        max_usage = max(location_usage.values()) if location_usage else 1
        
        for location_key, usage in location_usage.items():
            congestion_map[location_key] = min(1.0, usage / max_usage)
        
        return congestion_map
    
    def parse_simple_routing(self, architecture: FPGAArchitecture, 
                           circuit: Circuit) -> RoutingResult:
        """Generates simple routing results for testing"""
        routing_result = RoutingResult(circuit=circuit, architecture=architecture)
        
        # Generating random congestion for routing channels
        congestion_map = {}
        for channel in architecture.routing_channels:
            congestion_map[str(channel.segment_id)] = min(1.0, max(0.0, 0.3 + 0.5 * (channel.segment_id % 3) / 3))
        
        routing_result.congestion_map = congestion_map
        routing_result.total_wire_length = circuit.calculate_total_wire_length()
        routing_result.iteration_count = 5
        routing_result.successful = True
        routing_result.timing_data = {
            'total_routing_time': 2.5,
            'placement_time': 1.2,
            'routing_time': 1.3
        }
        
        return routing_result

    def export_routing_summary(self, result: RoutingResult, output_path: str):
        """Export routing results summary to JSON"""
        try:
            summary = {
                "total_routes": len(result.routes),
                "total_wire_length": result.total_wire_length,
                "max_congestion": max(result.congestion.values()) if result.congestion else 0,
                "avg_congestion": sum(result.congestion.values())/len(result.congestion) if result.congestion else 0
            }
            
            with open(output_path, 'w') as f:
                json.dump(summary, f, indent=2)
                
        except Exception as e:
            print(f"Error exporting routing summary: {e}")

    def _calculate_tree_statistics(self, routes: List[NetRoute]) -> Dict[str, Any]:
        """Computes routing tree statistics"""
        stats = {
            'nets_with_branches': 0,
            'max_fanout': 0,
            'total_paths': 0,
            'total_path_length': 0,
            'avg_path_length': 0.0
        }
        
        for route in routes:
            if route.root:
                paths = route.get_all_source_to_sink_paths()
                fanout = len(paths)
                
                if fanout > 1:
                    stats['nets_with_branches'] += 1
                
                stats['max_fanout'] = max(stats['max_fanout'], fanout)
                stats['total_paths'] += fanout
                
                for path in paths:
                    stats['total_path_length'] += len(path)
        
        if stats['total_paths'] > 0:
            stats['avg_path_length'] = stats['total_path_length'] / stats['total_paths']
        
        return stats
    
    def export_routing_trees(self, result: RoutingResult, output_path: str):
        """Export routing trees to JSON for visualization"""
        try:
            data = {
                "nets": [],
                "statistics": result.get_route_statistics()
            }
            
            for route in result.routes:
                net_data = {
                    "net_name": route.net_name,
                    "paths": route.get_path_coordinates(),
                    "tree": route.root.to_dict(include_children=True) if route.root else None,
                    "segment_count": len(route.segments),
                    "fanout": len(route.get_all_source_to_sink_paths()) if route.root else 0
                }
                data["nets"].append(net_data)
            
            with open(output_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            print(f"✅ Exported routing trees to {output_path}")
            
        except Exception as e:
            print(f"❌ Error exporting routing trees: {e}")