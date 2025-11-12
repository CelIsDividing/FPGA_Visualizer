import xml.etree.ElementTree as ET
from typing import Dict, List
from models.fpga_architecture import FPGAArchitecture, LogicBlock, RoutingChannel

class ArchitectureParser:
    """Parser za VTR RRG (Routing Resource Graph) XML fajlove"""
    
    def __init__(self):
        self.namespace = {'vtr': 'http://www.vtr.org/vtr'}
    
    def parse_architecture(self, file_path: str) -> FPGAArchitecture:
        """Parsira FPGA arhitekturu iz RRG XML fajla"""
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            
            return self._parse_rrg_document(root)
            
        except ET.ParseError as e:
            raise ValueError(f"Greška pri parsiranju XML fajla: {e}")
        except Exception as e:
            raise ValueError(f"Greška pri učitavanju arhitekture: {e}")
    
    def parse(self, file_path: str) -> FPGAArchitecture:
        """Alias za kompatibilnost — poziva parse_architecture"""
        return self.parse_architecture(file_path)

    def parse_xml(self, file_path: str) -> FPGAArchitecture:
        """Alias za kompatibilnost — poziva parse_architecture"""
        return self.parse_architecture(file_path)
    
    def _parse_rrg_document(self, root: ET.Element) -> FPGAArchitecture:
        """Parsira celokupan RRG XML dokument"""
        # Osnovni podaci o arhitekturi iz RRG
        architecture = FPGAArchitecture(
            name=root.get('tool_name', 'Unknown'),
            width=self._parse_grid_width(root),
            height=self._parse_grid_height(root)
        )
        
        # Parsiranje block_types (logic blocks)
        architecture.logic_blocks = self._parse_block_types(root)
        
        # Parsiranje channels (routing channels)
        architecture.routing_channels = self._parse_channels(root)
        
        # Parsiranje grid pozicija
        self._parse_grid_locations(root, architecture)
        
        # Parsiranje parametara
        architecture.parameters = self._parse_rrg_parameters(root)
        
        return architecture
    
    def _parse_grid_width(self, root: ET.Element) -> int:
        """Određuje širinu grid-a iz channels sekcije"""
        channels = root.find('channels')
        if channels is not None:
            x_lists = channels.findall('x_list')
            if x_lists:
                return len(x_lists)
        return 0
    
    def _parse_grid_height(self, root: ET.Element) -> int:
        """Određuje visinu grid-a iz channels sekcije"""
        channels = root.find('channels')
        if channels is not None:
            y_lists = channels.findall('y_list')
            if y_lists:
                return len(y_lists)
        return 0
    
    def _parse_block_types(self, root: ET.Element) -> List[LogicBlock]:
        """Parsira block_types iz RRG XML-a"""
        logic_blocks = []
        block_types_element = root.find('block_types')
        
        if block_types_element is not None:
            for block_type_elem in block_types_element.findall('block_type'):
                block_type_id = int(block_type_elem.get('id', '0'))
                block_name = block_type_elem.get('name', '')
                
                # Brojanje input i output pinova
                inputs = 0
                outputs = 0
                
                for pin_class in block_type_elem.findall('pin_class'):
                    pin_class_type = pin_class.get('type', '')
                    pins_count = len(pin_class.findall('pin'))
                    
                    if pin_class_type == 'INPUT':
                        inputs += pins_count
                    elif pin_class_type == 'OUTPUT':
                        outputs += pins_count
                
                block = LogicBlock(
                    type=block_name,
                    x=0,  # Postavićemo kasnije iz grid lokacija
                    y=0,
                    inputs=inputs,
                    outputs=outputs,
                    name=f"{block_name}_{block_type_id}",
                    block_type_id=block_type_id
                )
                logic_blocks.append(block)
        
        return logic_blocks
    
    def _parse_channels(self, root: ET.Element) -> List[RoutingChannel]:
        """Parsira routing channels iz RRG XML-a"""
        routing_channels = []
        channels_element = root.find('channels')
        
        if channels_element is not None:
            # Parsiranje channel konfiguracije
            channel_elem = channels_element.find('channel')
            if channel_elem is not None:
                chan_width = int(channel_elem.get('chan_width_max', '8'))
                
                # Kreiranje routing kanala na osnovu grid dimenzija
                width = self._parse_grid_width(root)
                height = self._parse_grid_height(root)
                
                channel_id = 0
                for x in range(width):
                    for y in range(height):
                        # Horizontalni kanali
                        if x < width - 1:
                            routing_channels.append(
                                RoutingChannel(
                                    segment_id=channel_id,
                                    direction="horizontal",
                                    length=1,
                                    capacity=chan_width
                                )
                            )
                            channel_id += 1
                        
                        # Vertikalni kanali
                        if y < height - 1:
                            routing_channels.append(
                                RoutingChannel(
                                    segment_id=channel_id,
                                    direction="vertical", 
                                    length=1,
                                    capacity=chan_width
                                )
                            )
                            channel_id += 1
        
        return routing_channels
    
    def _parse_grid_locations(self, root: ET.Element, architecture: FPGAArchitecture):
        """Parsira grid lokacije i ažurira pozicije logic blocks"""
        grid_element = root.find('grid')
        if grid_element is None:
            return
        
        # Mapa block_type_id -> LogicBlock
        block_type_map = {block.block_type_id: block for block in architecture.logic_blocks 
                         if hasattr(block, 'block_type_id')}
        
        for grid_loc in grid_element.findall('grid_loc'):
            block_type_id = int(grid_loc.get('block_type_id', '0'))
            x = int(grid_loc.get('x', '0'))
            y = int(grid_loc.get('y', '0'))
            
            if block_type_id in block_type_map:
                block = block_type_map[block_type_id]
                block.x = x
                block.y = y
                block.name = f"{block.type}_{x}_{y}"
    
    def _parse_rrg_parameters(self, root: ET.Element) -> Dict[str, str]:
        """Parsira parametre iz RRG fajla"""
        parameters = {}
        
        # Dodavanje osnovnih informacija
        parameters['tool_name'] = root.get('tool_name', '')
        parameters['tool_version'] = root.get('tool_version', '')
        
        # Informacije o channelima
        channels = root.find('channels')
        if channels is not None:
            channel_elem = channels.find('channel')
            if channel_elem is not None:
                parameters['chan_width_max'] = channel_elem.get('chan_width_max', '')
                parameters['grid_width'] = str(self._parse_grid_width(root))
                parameters['grid_height'] = str(self._parse_grid_height(root))
        
        # Informacije o switch-evima
        switches = root.find('switches')
        if switches is not None:
            parameters['switch_count'] = str(len(switches.findall('switch')))
        
        # Informacije o segmentima
        segments = root.find('segments')
        if segments is not None:
            parameters['segment_count'] = str(len(segments.findall('segment')))
        
        return parameters

    def parse_simple_architecture(self, width: int, height: int) -> FPGAArchitecture:
        """Kreira jednostavnu FPGA arhitekturu za testiranje"""
        architecture = FPGAArchitecture(
            name=f"Simple_FPGA_{width}x{height}",
            width=width,
            height=height
        )
        
        # Dodavanje logic blocks:
        # - IO blokovi na ivicama (x=0 ili x=width-1 ili y=0 ili y=height-1)
        # - CLB blokovi u unutrašnjosti 
        # - IZUZETI uglove: (0,0), (0,width-1), (width-1,0), (width-1,width-1)
        corners = {(0, 0), (0, width-1), (width-1, 0), (width-1, width-1)}
        
        for x in range(width):
            for y in range(height):
                # Preskoči uglove - ne kreiraj blokove na uglovima
                if (x, y) in corners:
                    continue
                
                # Proveri da li je ivična pozicija (IO blok)
                is_edge = (x == 0 or x == width-1 or y == 0 or y == height-1)
                
                if is_edge:
                    architecture.logic_blocks.append(
                        LogicBlock(
                            type="IO",
                            x=x,
                            y=y,
                            inputs=1,
                            outputs=1,
                            name=f"IO_{x}_{y}"
                        )
                    )
                else:
                    architecture.logic_blocks.append(
                        LogicBlock(
                            type="CLB",
                            x=x,
                            y=y,
                            inputs=4,
                            outputs=2,
                            name=f"CLB_{x}_{y}"
                        )
                    )
        
        # Dodavanje routing channels
        channel_id = 0
        for x in range(width):
            for y in range(height):
                if x < width - 1:
                    architecture.routing_channels.append(
                        RoutingChannel(
                            segment_id=channel_id,
                            direction="horizontal",
                            length=1
                        )
                    )
                    channel_id += 1
                
                if y < height - 1:
                    architecture.routing_channels.append(
                        RoutingChannel(
                            segment_id=channel_id,
                            direction="vertical",
                            length=1
                        )
                    )
                    channel_id += 1
        
        return architecture