import numpy as np
from typing import Dict, List, Tuple
from models.circuit import Circuit
from models.fpga_architecture import FPGAArchitecture
from models.routing import RoutingResult

class StatisticsCalculator:
    """Klasa za računanje statistike FPGA dizajna"""
    
    def __init__(self):
        pass
    
    def calculate_comprehensive_stats(self, circuit: Circuit, 
                                    architecture: FPGAArchitecture,
                                    routing_result: RoutingResult = None) -> Dict:
        """Računa sveobuhvatnu statistiku za FPGA dizajn"""
        stats = {}
        
        # Osnovna statistika kola
        stats.update(self._calculate_circuit_stats(circuit))
        
        # Statistika arhitekture
        stats.update(self._calculate_architecture_stats(architecture))
        
        # Statistika rutiranja (ako postoji)
        if routing_result:
            stats.update(self._calculate_routing_stats(routing_result))
        
        # Integrisana statistika
        stats.update(self._calculate_integrated_stats(circuit, architecture, routing_result))
        
        return stats
    
    def _calculate_circuit_stats(self, circuit: Circuit) -> Dict:
        """Računa statistiku kola"""
        active_signals = circuit.get_active_signals()
        signal_lengths = [signal.calculate_length() for signal in active_signals]
        
        return {
            'circuit_name': circuit.name,
            'total_signals': len(circuit.signals),
            'active_signals': len(active_signals),
            'excluded_signals': len([s for s in circuit.signals if s.is_excluded]),
            'total_components': len(circuit.components),
            'total_wire_length': sum(signal_lengths),
            'avg_signal_length': np.mean(signal_lengths) if signal_lengths else 0,
            'max_signal_length': max(signal_lengths) if signal_lengths else 0,
            'min_signal_length': min(signal_lengths) if signal_lengths else 0,
            'signal_length_std': np.std(signal_lengths) if signal_lengths else 0
        }
    
    def _calculate_architecture_stats(self, architecture: FPGAArchitecture) -> Dict:
        """Računa statistiku arhitekture"""
        return {
            'architecture_name': architecture.name,
            'fpga_width': architecture.width,
            'fpga_height': architecture.height,
            'total_logic_blocks': len(architecture.logic_blocks),
            'total_routing_channels': len(architecture.routing_channels),
            'horizontal_channels': len([c for c in architecture.routing_channels 
                                      if c.direction == 'horizontal']),
            'vertical_channels': len([c for c in architecture.routing_channels 
                                    if c.direction == 'vertical']),
            'total_segment_length': sum(c.length for c in architecture.routing_channels),
            'avg_channel_length': np.mean([c.length for c in architecture.routing_channels]) 
                               if architecture.routing_channels else 0
        }
    
    def _calculate_routing_stats(self, routing_result: RoutingResult) -> Dict:
        """Računa statistiku rutiranja"""
        congestion_metrics = routing_result.calculate_congestion_metrics()
        
        stats = {
            'routing_success': routing_result.successful,
            'routing_iterations': routing_result.iteration_count,
            'routing_wire_length': routing_result.total_wire_length
        }
        
        stats.update({f'congestion_{k}': v for k, v in congestion_metrics.items()})
        
        # Timing statistika
        if routing_result.timing_data:
            stats.update({f'timing_{k}': v for k, v in routing_result.timing_data.items()})
        
        return stats
    
    def _calculate_integrated_stats(self, circuit: Circuit, architecture: FPGAArchitecture,
                                  routing_result: RoutingResult = None) -> Dict:
        """Računa integrisanu statistiku"""
        stats = {}
        
        # Gustina kola na FPGA
        total_blocks = architecture.width * architecture.height
        used_blocks = len(architecture.logic_blocks)
        block_utilization = used_blocks / total_blocks if total_blocks > 0 else 0
        
        stats.update({
            'block_utilization': block_utilization,
            'blocks_per_component': len(architecture.logic_blocks) / len(circuit.components) 
                                  if circuit.components else 0,
            'signals_per_block': len(circuit.get_active_signals()) / len(architecture.logic_blocks) 
                               if architecture.logic_blocks else 0
        })
        
        # Statistika zagušenja ako postoji rutiranje
        if routing_result and routing_result.congestion_map:
            congestion_values = list(routing_result.congestion_map.values())
            stats.update({
                'congestion_variance': np.var(congestion_values) if congestion_values else 0,
                'congestion_skewness': self._calculate_skewness(congestion_values),
                'high_congestion_ratio': len([v for v in congestion_values if v > 0.8]) / 
                                       len(congestion_values) if congestion_values else 0
            })
        
        return stats
    
    def _calculate_skewness(self, data: List[float]) -> float:
        """Računa skewness za listu brojeva"""
        if not data or len(data) < 2:
            return 0.0
        
        data_array = np.array(data)
        mean = np.mean(data_array)
        std = np.std(data_array)
        
        if std == 0:
            return 0.0
        
        skewness = np.mean(((data_array - mean) / std) ** 3)
        return float(skewness)
    
    def calculate_signal_correlation(self, circuit: Circuit) -> List[Dict]:
        """Računa korelaciju između signala na osnovu bounding box preklapanja"""
        correlations = []
        active_signals = circuit.get_active_signals()
        
        for i, signal1 in enumerate(active_signals):
            for j, signal2 in enumerate(active_signals[i+1:], i+1):
                bbox1 = signal1.get_bounding_box()
                bbox2 = signal2.get_bounding_box()
                
                overlap_area = self._calculate_overlap_area(bbox1, bbox2)
                total_area = bbox1.width * bbox1.height + bbox2.width * bbox2.height - overlap_area
                
                if total_area > 0:
                    correlation = overlap_area / total_area
                    if correlation > 0.1:  # Samo značajne korelacije
                        correlations.append({
                            'signal1': signal1.name,
                            'signal2': signal2.name,
                            'correlation': correlation,
                            'overlap_area': overlap_area
                        })
        
        # Sortiranje po korelaciji
        return sorted(correlations, key=lambda x: x['correlation'], reverse=True)
    
    def _calculate_overlap_area(self, bbox1, bbox2) -> float:
        """Računa površinu preklapanja dva bounding box-a"""
        x_overlap = max(0, min(bbox1.max_x, bbox2.max_x) - max(bbox1.min_x, bbox2.min_x) + 1)
        y_overlap = max(0, min(bbox1.max_y, bbox2.max_y) - max(bbox1.min_y, bbox2.min_y) + 1)
        return x_overlap * y_overlap
    
    def generate_statistics_report(self, stats: Dict) -> str:
        """Generiše tekstualni izveštaj sa statistikom"""
        report = "=== FPGA Design Statistics Report ===\n\n"
        
        # Sekcija za kolo
        report += "CIRCUIT STATISTICS:\n"
        report += f"  Name: {stats.get('circuit_name', 'N/A')}\n"
        report += f"  Total Signals: {stats.get('total_signals', 0)}\n"
        report += f"  Active Signals: {stats.get('active_signals', 0)}\n"
        report += f"  Components: {stats.get('total_components', 0)}\n"
        report += f"  Total Wire Length: {stats.get('total_wire_length', 0):.2f}\n"
        report += f"  Avg Signal Length: {stats.get('avg_signal_length', 0):.2f}\n\n"
        
        # Sekcija za arhitekturu
        report += "ARCHITECTURE STATISTICS:\n"
        report += f"  Name: {stats.get('architecture_name', 'N/A')}\n"
        report += f"  Size: {stats.get('fpga_width', 0)}x{stats.get('fpga_height', 0)}\n"
        report += f"  Logic Blocks: {stats.get('total_logic_blocks', 0)}\n"
        report += f"  Routing Channels: {stats.get('total_routing_channels', 0)}\n"
        report += f"  Block Utilization: {stats.get('block_utilization', 0):.1%}\n\n"
        
        # Sekcija za rutiranje (ako postoji)
        if 'routing_success' in stats:
            report += "ROUTING STATISTICS:\n"
            report += f"  Success: {stats.get('routing_success', False)}\n"
            report += f"  Iterations: {stats.get('routing_iterations', 0)}\n"
            report += f"  Max Congestion: {stats.get('congestion_max_congestion', 0):.3f}\n"
            report += f"  Avg Congestion: {stats.get('congestion_avg_congestion', 0):.3f}\n"
            report += f"  Congested Segments: {stats.get('congestion_congested_segments', 0)}\n\n"
        
        return report