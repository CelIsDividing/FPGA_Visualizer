#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test za konflikt graf sa routing podacima
"""

import sys
import os

# Postavi UTF-8 encoding za stdout
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Dodaj putanju za import
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models.routing import RoutingResult, NetRoute, RouteSegment
from analysis.conflict_graph import ConflictGraphBuilder

def create_test_routing():
    """Kreira test routing sa dva net-a koji dele segmente"""
    
    # Net 1: koristi segmente (1,1), (1,2), (2,2)
    seg1_1 = RouteSegment(node_id=1, node_type='SOURCE', x=1, y=1)
    seg1_2 = RouteSegment(node_id=2, node_type='CHANX', x=1, y=2)
    seg1_3 = RouteSegment(node_id=3, node_type='SINK', x=2, y=2)
    
    net1 = NetRoute(
        net_name='Net_1',
        segments=[seg1_1, seg1_2, seg1_3],
        root=seg1_1
    )
    
    # Net 2: koristi segmente (1,2), (2,2), (3,2) - deli (1,2) i (2,2) sa Net 1
    seg2_1 = RouteSegment(node_id=4, node_type='SOURCE', x=0, y=2)
    seg2_2 = RouteSegment(node_id=5, node_type='CHANX', x=1, y=2)
    seg2_3 = RouteSegment(node_id=6, node_type='CHANX', x=2, y=2)
    seg2_4 = RouteSegment(node_id=7, node_type='SINK', x=3, y=2)
    
    net2 = NetRoute(
        net_name='Net_2',
        segments=[seg2_1, seg2_2, seg2_3, seg2_4],
        root=seg2_1
    )
    
    # Net 3: nema konflikte, koristi (0,0), (0,1)
    seg3_1 = RouteSegment(node_id=8, node_type='SOURCE', x=0, y=0)
    seg3_2 = RouteSegment(node_id=9, node_type='SINK', x=0, y=1)
    
    net3 = NetRoute(
        net_name='Net_3',
        segments=[seg3_1, seg3_2],
        root=seg3_1
    )
    
    routing = RoutingResult(routes=[net1, net2, net3])
    return routing

def test_conflict_graph():
    """Test konflikt grafa sa routing podacima"""
    print("=" * 50)
    print("TEST: Konflikt Graf sa Routing podacima")
    print("=" * 50)
    
    # Kreiraj test routing
    routing = create_test_routing()
    print(f"\nKreirano {len(routing.routes)} net-ova:")
    for route in routing.routes:
        print(f"  - {route.net_name}: {len(route.segments)} segmenata")
    
    # Kreiraj konflikt graf
    builder = ConflictGraphBuilder()
    conflict_graph = builder.build_conflict_graph(routing)
    
    print(f"\nKonflikt Graf:")
    print(f"  Cvorovi: {conflict_graph.number_of_nodes()}")
    print(f"  Grane (konflikti): {conflict_graph.number_of_edges()}")
    
    # Ispis konflikata
    print(f"\nDetektovani konflikti:")
    for edge in conflict_graph.edges(data=True):
        net1, net2, data = edge
        conflict_type = data.get('conflict_type', 'unknown')
        segment = data.get('segment', 'N/A')
        print(f"  {net1} <-> {net2}")
        print(f"    Tip: {conflict_type}, Segment: {segment}")
    
    # Metrike
    metrics = builder.calculate_graph_metrics()
    print(f"\nMetrike:")
    for key, value in metrics.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.3f}")
        else:
            print(f"  {key}: {value}")
    
    # Habovi
    hubs = builder.identify_hubs(centrality_threshold=0.0)
    print(f"\nHabovi: {hubs}")
    
    print("\n" + "=" * 50)
    print("TEST ZAVRŠEN USPEŠNO!")
    print("=" * 50)

if __name__ == '__main__':
    test_conflict_graph()
