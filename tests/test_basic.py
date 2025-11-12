import unittest
import sys
import os

# Dodaj parent directory u Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.fpga_architecture import FPGAArchitecture, Point
from models.circuit import Circuit, Signal

class TestBasicModels(unittest.TestCase):
    
    def test_point_creation(self):
        point = Point(5, 10)
        self.assertEqual(point.x, 5)
        self.assertEqual(point.y, 10)
    
    def test_fpga_architecture(self):
        arch = FPGAArchitecture("Test", 8, 8)
        self.assertEqual(arch.name, "Test")
        self.assertEqual(arch.width, 8)
        self.assertEqual(arch.height, 8)
    
    def test_circuit_signal_addition(self):
        circuit = Circuit("Test_Circuit")
        signal = Signal("sig1")
        circuit.add_signal(signal)
        self.assertEqual(len(circuit.signals), 1)
        self.assertEqual(circuit.signals[0].name, "sig1")

if __name__ == '__main__':
    unittest.main()