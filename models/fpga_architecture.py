from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
import json

class Point:
    """Represents a 2D point with x,y coordinates"""
    def __init__(self, x: int = 0, y: int = 0):
        self.x = x
        self.y = y

    def __eq__(self, other):
        if not isinstance(other, Point):
            return False
        return self.x == other.x and self.y == other.y

    def __hash__(self):
        return hash((self.x, self.y))

    def to_dict(self) -> Dict[str, int]:
        return {"x": self.x, "y": self.y}
    
class BoundingBox:
    """Represents a rectangular region defined by two points"""
    def __init__(self, min_point: Point = None, max_point: Point = None):
        self.min_point = min_point if min_point is not None else Point()
        self.max_point = max_point if max_point is not None else Point()

    @property
    def width(self) -> int:
        return self.max_point.x - self.min_point.x + 1

    @property
    def height(self) -> int:
        return self.max_point.y - self.min_point.y + 1

    def contains_point(self, point: Point) -> bool:
        return (self.min_point.x <= point.x <= self.max_point.x and
                self.min_point.y <= point.y <= self.max_point.y)

    def intersects(self, other: 'BoundingBox') -> bool:
        return not (self.max_point.x < other.min_point.x or
                   self.min_point.x > other.max_point.x or
                   self.max_point.y < other.min_point.y or
                   self.min_point.y > other.max_point.y)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "min_point": self.min_point.to_dict(),
            "max_point": self.max_point.to_dict()
        }
    
class LogicBlock:
    def __init__(self,
                 type: str = "",
                 x: int = 0,
                 y: int = 0,
                 inputs: int = 0,
                 outputs: int = 0,
                 name: str = "",
                 **kwargs: Any):
        self.type = type
        self.x = x
        self.y = y
        self.inputs = inputs
        self.outputs = outputs
        self.name = name
        # Prihvata sve dodatne atribute koje parser može proslediti
        for k, v in kwargs.items():
            setattr(self, k, v)

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


class RoutingChannel:
    def __init__(self,
                 segment_id: int = 0,
                 direction: str = "",
                 length: int = 0,
                 capacity: int = None,
                 **kwargs: Any):
        self.segment_id = segment_id
        self.direction = direction
        self.length = length
        self.capacity = capacity
        # Dodatni atributi iz parsera (npr. track_ids, segment_type, switches)
        for k, v in kwargs.items():
            setattr(self, k, v)

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


class FPGAArchitecture:
    def __init__(self,
                 name: str = "Unknown",
                 width: int = 0,
                 height: int = 0,
                 logic_blocks: List[LogicBlock] = None,
                 routing_channels: List[RoutingChannel] = None,
                 parameters: Dict[str, str] = None,
                 **kwargs: Any):
        self.name = name
        self.width = width
        self.height = height
        self.logic_blocks = logic_blocks if logic_blocks is not None else []
        self.routing_channels = routing_channels if routing_channels is not None else []
        self.parameters = parameters if parameters is not None else {}
        # Sačuvaj sve dodatne informacije (npr. segments, switches, extra metadata)
        for k, v in kwargs.items():
            setattr(self, k, v)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "logic_blocks": [lb.to_dict() for lb in self.logic_blocks],
            "routing_channels": [rc.to_dict() for rc in self.routing_channels],
            "parameters": dict(self.parameters)
        }