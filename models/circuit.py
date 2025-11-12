from dataclasses import dataclass, field
from typing import List, Dict, Optional
from .fpga_architecture import Point, BoundingBox
import math

@dataclass
class Signal:
    name: str
    source: Optional[Point] = None
    destination: Optional[Point] = None
    route: List[Point] = field(default_factory=list)
    length: float = 0.0
    is_excluded: bool = False
    
    def calculate_length(self) -> float:
        """Računa dužinu signala na osnovu rute"""
        if len(self.route) < 2:
            return 0.0
        
        total_length = 0.0
        for i in range(len(self.route) - 1):
            p1 = self.route[i]
            p2 = self.route[i + 1]
            total_length += math.sqrt((p2.x - p1.x)**2 + (p2.y - p1.y)**2)
        
        self.length = total_length
        return total_length
    
    def get_bounding_box(self) -> BoundingBox:
        """Vraća bounding box signala"""
        if not self.route:
            return BoundingBox(0, 0, 0, 0)
        
        xs = [p.x for p in self.route]
        ys = [p.y for p in self.route]
        
        return BoundingBox(
            min_x=min(xs),
            min_y=min(ys),
            max_x=max(xs),
            max_y=max(ys)
        )

@dataclass
class Component:
    name: str
    type: str
    position: Point
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)

@dataclass
class Circuit:
    name: str
    signals: List[Signal] = field(default_factory=list)
    components: List[Component] = field(default_factory=list)
    
    def add_signal(self, signal: Signal):
        """Dodaje signal u kolo"""
        self.signals.append(signal)
    
    def add_component(self, component: Component):
        """Dodaje komponentu u kolo"""
        self.components.append(component)
    
    def get_signal(self, name: str) -> Optional[Signal]:
        """Vraća signal po imenu"""
        for signal in self.signals:
            if signal.name == name:
                return signal
        return None
    
    def exclude_signals(self, signal_names: List[str]):
        """Isključuje signale iz analize"""
        for signal in self.signals:
            if signal.name in signal_names:
                signal.is_excluded = True
    
    def include_signals(self, signal_names: List[str]):
        """Uključuje signale u analizu"""
        for signal in self.signals:
            if signal.name in signal_names:
                signal.is_excluded = False
    
    def get_active_signals(self) -> List[Signal]:
        """Vraća signale koji nisu isključeni"""
        return [signal for signal in self.signals if not signal.is_excluded]
    
    def calculate_total_wire_length(self) -> float:
        """Računa ukupnu dužinu žica za aktivne signale"""
        return sum(signal.calculate_length() for signal in self.get_active_signals())
    
    def to_dict(self) -> Dict:
        """Konvertuje kolo u dictionary za JSON serijalizaciju"""
        return {
            'name': self.name,
            'signals': [
                {
                    'name': s.name,
                    'source': {'x': s.source.x, 'y': s.source.y} if s.source else None,
                    'destination': {'x': s.destination.x, 'y': s.destination.y} if s.destination else None,
                    'route': [{'x': p.x, 'y': p.y} for p in s.route],
                    'length': s.length,
                    'is_excluded': s.is_excluded
                } for s in self.signals
            ],
            'components': [
                {
                    'name': c.name,
                    'type': c.type,
                    'position': {'x': c.position.x, 'y': c.position.y},
                    'inputs': c.inputs,
                    'outputs': c.outputs
                } for c in self.components
            ]
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Circuit':
        """Kreira Circuit iz dictionary"""
        circuit = cls(name=data['name'])
        
        for signal_data in data.get('signals', []):
            signal = Signal(name=signal_data['name'])
            
            if signal_data.get('source'):
                signal.source = Point(**signal_data['source'])
            if signal_data.get('destination'):
                signal.destination = Point(**signal_data['destination'])
            
            signal.route = [Point(**p) for p in signal_data.get('route', [])]
            signal.length = signal_data.get('length', 0.0)
            signal.is_excluded = signal_data.get('is_excluded', False)
            
            circuit.add_signal(signal)
        
        for comp_data in data.get('components', []):
            component = Component(
                name=comp_data['name'],
                type=comp_data['type'],
                position=Point(**comp_data['position']),
                inputs=comp_data.get('inputs', []),
                outputs=comp_data.get('outputs', [])
            )
            circuit.add_component(component)
        
        return circuit