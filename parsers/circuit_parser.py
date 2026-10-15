import re
import xml.etree.ElementTree as ET
from typing import List, Dict
from models.circuit import Circuit, Signal, Component, Point

class CircuitParser:
    """Parser for Verilog and BLIF files"""
    
    def __init__(self):
        self.wire_pattern = re.compile(r'wire\s+(\w+(?:\s*,\s*\w+)*);')
        self.assign_pattern = re.compile(r'assign\s+(\w+)\s*=\s*(\w+);')
        self.module_pattern = re.compile(r'(\w+)\s+(\w+)\s*\((.*?)\)')
    
    def parse_verilog(self, file_path: str) -> Circuit:
        """Parses a Verilog file"""
        circuit_name = self._extract_circuit_name(file_path)
        circuit = Circuit(name=circuit_name)
        
        try:
            with open(file_path, 'r') as file:
                content = file.read()
                
            # Removing comments
            content = self._remove_comments(content)
            
            # Parsing line by line
            lines = content.split('\n')
            for line in lines:
                self._parse_verilog_line(line.strip(), circuit)
                
        except Exception as e:
            raise ValueError(f"Error parsing Verilog file: {e}")
        
        return circuit
    
    def parse_blif(self, file_path: str) -> Circuit:
        """Parses a BLIF file"""
        circuit_name = self._extract_circuit_name(file_path)
        circuit = Circuit(name=circuit_name)
        
        try:
            with open(file_path, 'r') as file:
                lines = file.readlines()
                
            for line in lines:
                self._parse_blif_line(line.strip(), circuit)
                
        except Exception as e:
            raise ValueError(f"Error parsing BLIF file: {e}")
        
        return circuit
    
    def _parse_verilog_line(self, line: str, circuit: Circuit):
        """Parses a single line of Verilog code"""
        if not line or line.startswith('//'):
            return
        
        # Wire declarations
        wire_match = self.wire_pattern.match(line)
        if wire_match:
            wires = [w.strip() for w in wire_match.group(1).split(',')]
            for wire in wires:
                if wire and not circuit.get_signal(wire):
                    circuit.add_signal(Signal(name=wire))
            return
        
        # Assign statements
        assign_match = self.assign_pattern.match(line)
        if assign_match:
            target = assign_match.group(1)
            source = assign_match.group(2)
            
            # Creating signals if they do not exist
            if not circuit.get_signal(target):
                circuit.add_signal(Signal(name=target))
            if not circuit.get_signal(source):
                circuit.add_signal(Signal(name=source))
            return
        
        # Module instance
        module_match = self.module_pattern.search(line)
        if module_match:
            module_type = module_match.group(1)
            instance_name = module_match.group(2)
            connections_str = module_match.group(3)
            
            component = Component(
                name=instance_name,
                type=module_type,
                position=Point(0, 0)  # Default position
            )
            
            # Parsing connections
            self._parse_connections(connections_str, component)
            circuit.add_component(component)
    
    def _parse_blif_line(self, line: str, circuit: Circuit):
        """Parses a single line of a BLIF file"""
        if not line or line.startswith('#'):
            return
        
        if line.startswith('.inputs'):
            inputs = line[7:].strip().split()
            for input_name in inputs:
                if input_name and not circuit.get_signal(input_name):
                    circuit.add_signal(Signal(name=input_name))
        
        elif line.startswith('.outputs'):
            outputs = line[8:].strip().split()
            for output_name in outputs:
                if output_name and not circuit.get_signal(output_name):
                    circuit.add_signal(Signal(name=output_name))
        
        elif line.startswith('.names'):
            parts = line[6:].strip().split()
            if len(parts) >= 2:
                # The last one is the output, the rest are inputs
                output = parts[-1]
                inputs = parts[:-1]
                
                component = Component(
                    name=f"gate_{len(circuit.components)}",
                    type="LUT",
                    position=Point(0, 0)
                )
                
                component.inputs.extend(inputs)
                component.outputs.append(output)
                circuit.add_component(component)
    
    def _parse_connections(self, connections_str: str, component: Component):
        """Parses connections in a Verilog module"""
        connections = [c.strip() for c in connections_str.split(',')]
        
        for connection in connections:
            if '.' in connection:
                parts = connection.split('.')
                if len(parts) == 2:
                    port = parts[0].strip()
                    net = parts[1].strip()
                    
                    if port.startswith('in'):
                        component.inputs.append(net)
                    elif port.startswith('out'):
                        component.outputs.append(net)
    
    def _remove_comments(self, content: str) -> str:
        """Removes comments from Verilog code"""
        # Removing single-line comments
        content = re.sub(r'//.*', '', content)
        # Removing multi-line comments
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        return content
    
    def _extract_circuit_name(self, file_path: str) -> str:
        """Extracts the circuit name from the file path"""
        import os
        filename = os.path.basename(file_path)
        name = os.path.splitext(filename)[0]
        return name
    
    def create_test_circuit(self, num_signals: int = 10) -> Circuit:
        """Creates a test circuit for demonstration"""
        circuit = Circuit(name="Test_Circuit")
        
        # Adding signals with random routes
        import random
        for i in range(num_signals):
            signal = Signal(name=f"signal_{i}")
            
            # Random source and destination
            signal.source = Point(random.randint(0, 3), random.randint(0, 10))
            signal.destination = Point(random.randint(0, 2), random.randint(0, 9))
            
            # Generating a simple route
            self._generate_simple_route(signal)
            circuit.add_signal(signal)
        
        return circuit
    
    def _generate_simple_route(self, signal: Signal):
        """Generates a simple route between source and destination"""
        if not signal.source or not signal.destination:
            return
        
        current = Point(signal.source.x, signal.source.y)
        signal.route.append(Point(current.x, current.y))
        
        # First horizontally, then vertically
        while current.x != signal.destination.x:
            if current.x < signal.destination.x:
                current.x += 1
            else:
                current.x -= 1
            signal.route.append(Point(current.x, current.y))
        
        while current.y != signal.destination.y:
            if current.y < signal.destination.y:
                current.y += 1
            else:
                current.y -= 1
            signal.route.append(Point(current.x, current.y))
        
        signal.calculate_length()