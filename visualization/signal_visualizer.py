import os
import random
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.lines import Line2D
from typing import Dict, Optional, List, Tuple

from models.fpga_architecture import FPGAArchitecture
from models.routing import RoutingResult, RouteSegment
from config.settings import settings


class SignalVisualizer:
    """
    VPR-style routing visualization:
    - IPIN (crna tačka) na spoju žice i klastera
    - OPIN (siva tačka) na spoju klastera i žice
    - CHANX (plava linija sa strelicom →)
    - CHANY (crvena linija sa strelicom ↑)
    - SOURCE (crveni kvadrat)
    - SINK (zeleni trougao)
    - SB (tanke linije na presecima)
    """

    # Boje po tipu čvora
    NODE_COLORS = {
        'SOURCE': '#d62728',    # Crvena
        'SINK': "#00e400",      # Zelena
        'OPIN': '#7f7f7f',      # Siva
        'IPIN': '#000000',      # Crna
        'CHANX': '#1f77b4',     # Plava
        'CHANY': '#ff7f0e',     # Narandžasta/crvena
    }

    def __init__(self):
        self.TILE_SIZE = getattr(settings, "CELL_SIZE", 100)  # Increased from 80 to 100
        self.CLB_SIZE = int(self.TILE_SIZE * 0.50)  # Back to normal size - problem was missing blocks, not size
        self.IO_SIZE = int(self.TILE_SIZE * 0.45)   # Back to normal size
        self.TRACK_COUNT = 8  # 8 tracks per channel with better spacing
        self.ROUTE_COLORS = getattr(settings, "SIGNAL_COLORS",
                                    ["#e41a1c", "#377eb8", "#4daf4a", "#ff7f00", "#984ea3", "#00aa7f"])
        self.fig = None
        self.ax = None
        self.architecture = None

    def visualize_routing(self,
                          architecture: FPGAArchitecture,
                          routing: RoutingResult,
                          output_path: str,
                          show_grid: bool = True,
                          show_segment_ids: bool = True,
                          show_legend: bool = True,
                          show_signals: bool = True,
                          show_bounding_boxes: bool = True,
                          show_bounding_box_labels: bool = False,
                          show_signal_labels: bool = True,
                          show_directions: bool = True,
                          show_heatmap: bool = True,
                          architecture_file: str = None,
                          routing_file: str = None,
                          filter_type: str = None,
                          filter_value: int = None):
        w, h = architecture.width, architecture.height
        
        self.architecture = architecture
        
        # Reset arrows tracking for new visualization
        self.arrows_drawn = set()

        margin = self.TILE_SIZE

        # Adjusted for proper 8x8 grid (no extra border)
        width_px = w * self.TILE_SIZE + 2 * margin
        height_px = h * self.TILE_SIZE + 2 * margin
        
        dpi = 100
        self.fig = plt.figure(figsize=(width_px/dpi, height_px/dpi), dpi=dpi)
        
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_facecolor("white")
        self.fig.patch.set_facecolor("white")

        self.ax.set_xlim(-margin, w * self.TILE_SIZE + margin)
        self.ax.set_ylim(-margin, h * self.TILE_SIZE + margin)
        self.ax.set_aspect('equal')
        self.ax.axis('off')
        self.ax.margins(0)
        
        self.ax.autoscale(False)
        self.ax.set_adjustable('box')

        if show_grid:
            self._draw_background_grid(w, h)

        # Izračunaj HPWL statistike za svaki blok ako je heat mapa uključena
        block_hpwl_stats = None
        if show_heatmap and routing:
            block_hpwl_stats = self._calculate_block_hpwl_coverage(routing, w, h)

        self._draw_blocks(w, h, block_hpwl_stats)
        self._draw_tracks(w, h)
        
        # Prikaži obojene bounding boxove ako je checkbox uključen
        if show_bounding_boxes:
            self._draw_bounding_boxes(routing, show_bounding_box_labels)
        
        # Prikaži signale (rute i čvorove) samo ako je checkbox uključen
        if show_signals:
            self._draw_routes(routing, architecture, show_segment_ids, show_directions, show_signal_labels)

        if show_legend and routing and routing.routes and show_signals:
            self._draw_legend(routing)
        
        # Dodaj naslov i podnaslov na osnovu opcija
        self._add_title_and_subtitle(show_heatmap, show_signals, show_bounding_boxes, 
                                     architecture_file, routing_file, filter_type, filter_value)
        
        self._save(output_path, dpi)
        return self.fig
    
    def _calculate_block_hpwl_coverage(self, routing: RoutingResult, width: int, height: int) -> Dict:
        """
        Računa prosečnu HPWL vrednost za svaki blok na osnovu bounding boxova koji ga pokrivaju
        Returns: Dict[(x, y)] = average_hpwl
        """
        block_hpwl_sums = {}  # (x, y) -> [lista HPWL vrednosti]
        
        nets = getattr(routing, 'routes', getattr(routing, 'nets', []))
        
        for ridx, net in enumerate(nets):
            # Dobavi segmente
            segments = []
            if hasattr(net, 'root') and net.root:
                paths = self._extract_all_paths(net.root)
                for path in paths:
                    segments.extend(path)
            elif hasattr(net, 'get_all_source_to_sink_paths'):
                paths = net.get_all_source_to_sink_paths()
                for path in paths:
                    segments.extend(path)
            else:
                segments = getattr(net, 'segments', [])
            
            if not segments:
                continue
            
            # Filtriraj validne koordinate
            valid_segments = [s for s in segments 
                            if hasattr(s, 'x') and hasattr(s, 'y') 
                            and s.x >= 0 and s.y >= 0]
            
            if not valid_segments:
                continue
            
            # Nađi bounding box koordinate
            min_x = min(s.x for s in valid_segments)
            max_x = max(s.x for s in valid_segments)
            min_y = min(s.y for s in valid_segments)
            max_y = max(s.y for s in valid_segments)
            
            # Izračunaj HPWL
            hpwl = (max_x - min_x + 1) + (max_y - min_y + 1)
            
            # Za svaki blok koji je pokriven ovim bounding boxom, dodaj HPWL vrednost
            for x in range(min_x, max_x + 1):
                for y in range(min_y, max_y + 1):
                    if 0 <= x < width and 0 <= y < height:
                        if (x, y) not in block_hpwl_sums:
                            block_hpwl_sums[(x, y)] = []
                        block_hpwl_sums[(x, y)].append(hpwl)
        
        # Izračunaj prosek za svaki blok
        block_avg_hpwl = {}
        for (x, y), hpwl_list in block_hpwl_sums.items():
            block_avg_hpwl[(x, y)] = sum(hpwl_list) / len(hpwl_list)
        
        return block_avg_hpwl
    
    def _get_heatmap_color(self, value: float, min_val: float, max_val: float) -> str:
        """
        Izračunava boju na gradientu od žute (najmanja vrednost) preko narandžaste do crvene (najveća vrednost)
        """
        if min_val == max_val:
            return "#FFA500"  # Narandžasta ako su sve vrednosti iste
        
        # Normalizuj vrednost između 0 i 1
        normalized = (value - min_val) / (max_val - min_val)
        
        # Gradijent: žuta (0) -> narandžasta (0.5) -> crvena (1)
        if normalized < 0.5:
            # Žuta (#FFFF00) -> Narandžasta (#FFA500)
            t = normalized * 2  # 0 to 1
            r = 255
            g = int(255 - (85 * t))  # 255 -> 170
            b = int(0 + (0 * t))     # 0 -> 0
        else:
            # Narandžasta (#FFA500) -> Crvena (#FF0000)
            t = (normalized - 0.5) * 2  # 0 to 1
            r = 255
            g = int(165 - (165 * t))  # 165 -> 0
            b = 0
        
        return f"#{r:02X}{g:02X}{b:02X}"
    
    # ---------- Geometry helpers ----------
    def io_center(self, gx: int, gy: int) -> Tuple[float, float]:
        """Alias za _get_io_position() - za kompatibilnost"""
        return self._get_io_position(gx, gy)
    
    def clb_center(self, x: int, y: int):
        """CLB/IO block center - now works directly with grid coordinates"""
        return (x + 0.5) * self.TILE_SIZE, (y + 0.5) * self.TILE_SIZE

    def chanx_y_for_track(self, row: int, track: int):
        """Y koordinata horizontalnog track-a - matching track drawing exactly"""
        # Use same calculation as track drawing
        gap_size = self.TILE_SIZE - self.CLB_SIZE
        usable_gap = gap_size * 0.8  # Same 80% as track drawing
        track_spacing = usable_gap / (self.TRACK_COUNT + 1)  # Same formula as track drawing
        
        # Gap center Y position
        gap_center_y = (row + 1) * self.TILE_SIZE
        track_area_start = gap_center_y - usable_gap / 2
        
        # Position track exactly as in drawing
        track_y = track_area_start + (track + 1) * track_spacing
        return track_y
    
    def chany_x_for_track(self, col: int, track: int):
        """X koordinata vertikalnog track-a - matching track drawing exactly"""
        # Use same calculation as track drawing
        gap_size = self.TILE_SIZE - self.CLB_SIZE
        usable_gap = gap_size * 0.8  # Same 80% as track drawing
        track_spacing = usable_gap / (self.TRACK_COUNT + 1)  # Same formula as track drawing
        
        # Gap center X position
        gap_center_x = (col + 1) * self.TILE_SIZE
        track_area_start = gap_center_x - usable_gap / 2
        
        # Position track exactly as in drawing
        track_x = track_area_start + (track + 1) * track_spacing
        return track_x

    # ---------- Drawing ----------
    def _draw_background_grid(self, width: int, height: int):
        for x in range(width + 1):
            gx = x * self.TILE_SIZE
            self.ax.plot([gx, gx], [0, height * self.TILE_SIZE],
                         color="#e8e8e8", linewidth=0.5, zorder=0)
        for y in range(height + 1):
            gy = y * self.TILE_SIZE
            self.ax.plot([0, width * self.TILE_SIZE], [gy, gy],
                         color="#e8e8e8", linewidth=0.5, zorder=0)

    def _draw_blocks(self, width: int, height: int, block_hpwl_stats: Dict = None):
        """Draw blocks based on standard FPGA layout - IO on edges (excluding corners), CLB in interior"""
        
        # Always use fallback method for consistent 8x8 grid layout
        # RRG files don't always have complete block information
        corners = {(0, 0), (0, height-1), (width-1, 0), (width-1, height-1)}
        
        # Nađi minimalnu i maksimalnu HPWL vrednost za gradijent boja
        min_hpwl = None
        max_hpwl = None
        if block_hpwl_stats:
            values = list(block_hpwl_stats.values())
            if values:
                min_hpwl = min(values)
                max_hpwl = max(values)
        
        for x in range(width):
            for y in range(height):
                if (x, y) in corners:
                    continue  # Skip corners - no blocks there
                    
                is_edge = (x == 0 or x == width-1 or y == 0 or y == height-1)
                
                # Dobavi prosečnu HPWL vrednost za ovaj blok ako postoji
                avg_hpwl = None
                if block_hpwl_stats and (x, y) in block_hpwl_stats:
                    avg_hpwl = block_hpwl_stats[(x, y)]
                
                if is_edge:
                    self._draw_io_block_at_grid(x, y, avg_hpwl, min_hpwl, max_hpwl)
                else:
                    self._draw_clb_block_at_grid(x, y, avg_hpwl, min_hpwl, max_hpwl)
    
    def _draw_clb_block_at_grid(self, grid_x: int, grid_y: int, avg_hpwl: float = None, min_hpwl: float = None, max_hpwl: float = None):
        """Draw a CLB block at grid position (grid_x, grid_y)"""
        cx, cy = self.clb_center(grid_x, grid_y)
        
        # Odredimo boju bloka
        if avg_hpwl is not None and min_hpwl is not None and max_hpwl is not None:
            facecolor = self._get_heatmap_color(avg_hpwl, min_hpwl, max_hpwl)
        else:
            facecolor = "#cccccc"  # Light gray
        
        rect = patches.Rectangle(
            (cx - self.CLB_SIZE/2, cy - self.CLB_SIZE/2),
            self.CLB_SIZE, self.CLB_SIZE,
            facecolor=facecolor, edgecolor="#999999", linewidth=2, zorder=2)
        self.ax.add_patch(rect)
        
        # Prikaži prosečnu HPWL vrednost ako postoji, inače "CLB"
        if avg_hpwl is not None:
            label = f"{avg_hpwl:.1f}"
            fontsize = 10
            text_color = "white"  # Uvek bela boja za tekst
        else:
            label = "CLB"
            fontsize = 12
            text_color = "black"
            
        self.ax.text(cx, cy, label, color=text_color, ha="center", va="center",
                    fontsize=fontsize, weight='bold', zorder=10)  # zorder=10 iznad heat mape
    
    def _draw_io_block_at_grid(self, grid_x: int, grid_y: int, avg_hpwl: float = None, min_hpwl: float = None, max_hpwl: float = None):
        """Draw an IO block at grid position (grid_x, grid_y)"""
        cx, cy = self.clb_center(grid_x, grid_y)  # Use same positioning as CLB
        
        # Odredimo boju bloka
        if avg_hpwl is not None and min_hpwl is not None and max_hpwl is not None:
            facecolor = self._get_heatmap_color(avg_hpwl, min_hpwl, max_hpwl)
        else:
            facecolor = "#666666"  # Darker gray
        
        rect = patches.Rectangle(
            (cx - self.IO_SIZE/2, cy - self.IO_SIZE/2),
            self.IO_SIZE, self.IO_SIZE,
            facecolor=facecolor, edgecolor="#333333", linewidth=2, zorder=2)
        self.ax.add_patch(rect)
        
        # Prikaži prosečnu HPWL vrednost ako postoji, inače "IO"
        if avg_hpwl is not None:
            label = f"{avg_hpwl:.1f}"
            fontsize = 9
            text_color = "white"  # Uvek bela boja za tekst
        else:
            label = "IO"
            fontsize = 11
            text_color = "white"
            
        self.ax.text(cx, cy, label, color=text_color, ha="center", va="center",
                    fontsize=fontsize, weight='bold', zorder=10)  # zorder=10 iznad heat mape

    def _draw_io_block(self, cx: int, cy: int):
        rect = patches.Rectangle(
            (cx - self.IO_SIZE/2, cy - self.IO_SIZE/2),
            self.IO_SIZE, self.IO_SIZE,
            facecolor="#666666", edgecolor="#333333", linewidth=2, zorder=2)  # Darker gray with border
        self.ax.add_patch(rect)
        self.ax.text(cx, cy, "IO", color="white", ha="center", va="center",
                    fontsize=11, weight='bold', zorder=3)

    def _draw_tracks(self, width: int, height: int):
        """Crta routing kanale (CHANX i CHANY) između blokova - kratke trake u svakom gap-u"""
        gap_size = self.TILE_SIZE - self.CLB_SIZE
        # Better track spacing - use 80% of gap for tracks, 20% for margins
        usable_gap = gap_size * 0.8
        track_spacing = usable_gap / (self.TRACK_COUNT + 1)  # More space between tracks

        # Get IO block positions if architecture is available
        io_positions = set()
        if self.architecture and hasattr(self.architecture, 'logic_blocks'):
            for block in self.architecture.logic_blocks:
                if block.type == "IO":
                    io_positions.add((block.x, block.y))
        else:
            # Fallback: IO blocks are on edges (excluding corners) in standard FPGA layout
            corners = {(0, 0), (0, height-1), (width-1, 0), (width-1, height-1)}
            for x in range(width):
                for y in range(height):
                    if (x, y) in corners:
                        continue  # Skip corners
                    is_edge = (x == 0 or x == width-1 or y == 0 or y == height-1)
                    if is_edge:
                        io_positions.add((x, y))

        # Horizontalni trackovi (CHANX) - kratke trake u svakom horizontalnom gap-u
        for row in range(height - 1):  # Between adjacent rows
            for col in range(width):   # For each column position
                # Check if we should draw tracks in this gap
                top_pos = (col, row + 1)
                bottom_pos = (col, row)
                
                # Check block types
                top_is_io = top_pos in io_positions
                bottom_is_io = bottom_pos in io_positions
                
                # Skip if both blocks are IO (no tracks between IO blocks)
                if top_is_io and bottom_is_io:
                    continue
                
                # Also skip if either block doesn't exist (corner positions)
                corners = {(0, 0), (0, height-1), (width-1, 0), (width-1, height-1)}
                if top_pos in corners or bottom_pos in corners:
                    continue
                
                # Only draw tracks between: CLB-CLB, CLB-IO, or IO-CLB
                top_is_clb = not top_is_io and top_pos not in corners
                bottom_is_clb = not bottom_is_io and bottom_pos not in corners
                
                # Skip if we don't have valid block combination
                if not ((top_is_clb and bottom_is_clb) or (top_is_clb and bottom_is_io) or (top_is_io and bottom_is_clb)):
                    continue
                

                
                # Calculate gap position and track length based on block types
                gap_center_y = (row + 1) * self.TILE_SIZE
                
                # Use different track lengths based on block combination
                if top_is_clb and bottom_is_clb:
                    # CLB-CLB: full track length (normal CLB_SIZE length)
                    track_start_x = col * self.TILE_SIZE + (self.TILE_SIZE - self.CLB_SIZE) / 2
                    track_end_x = track_start_x + self.CLB_SIZE
                else:
                    # CLB-IO or IO-CLB: shortened tracks to avoid visual connection to IO
                    block_edge_margin = (self.TILE_SIZE - self.CLB_SIZE) / 2 + self.CLB_SIZE / 2
                    track_start_x = col * self.TILE_SIZE + block_edge_margin
                    track_end_x = (col + 1) * self.TILE_SIZE - block_edge_margin
                
                # Draw horizontal tracks with CLB length
                track_area_start = gap_center_y - usable_gap / 2
                for t in range(self.TRACK_COUNT):
                    y = track_area_start + (t + 1) * track_spacing
                    self.ax.plot([track_start_x, track_end_x], [y, y], 
                                color="#000000", linewidth=1.0, alpha=0.7, zorder=1)

        # Vertikalni trackovi (CHANY) - kratke trake u svakom vertikalnom gap-u  
        for col in range(width - 1):  # Between adjacent columns
            for row in range(height):  # For each row position
                # Check if we should draw tracks in this gap
                right_pos = (col + 1, row)
                left_pos = (col, row)
                
                # Check block types
                right_is_io = right_pos in io_positions
                left_is_io = left_pos in io_positions
                
                # Skip if both blocks are IO (no tracks between IO blocks)
                if right_is_io and left_is_io:
                    continue
                
                # Also skip if either block doesn't exist (corner positions)
                corners = {(0, 0), (0, height-1), (width-1, 0), (width-1, height-1)}
                if right_pos in corners or left_pos in corners:
                    continue
                
                # Only draw tracks between: CLB-CLB, CLB-IO, or IO-CLB
                right_is_clb = not right_is_io and right_pos not in corners
                left_is_clb = not left_is_io and left_pos not in corners
                
                # Skip if we don't have valid block combination
                if not ((right_is_clb and left_is_clb) or (right_is_clb and left_is_io) or (right_is_io and left_is_clb)):
                    continue
                
                # Calculate gap position and track length based on block types
                gap_center_x = (col + 1) * self.TILE_SIZE
                
                # Use different track lengths based on block combination
                if right_is_clb and left_is_clb:
                    # CLB-CLB: full track length (normal CLB_SIZE length)
                    track_start_y = row * self.TILE_SIZE + (self.TILE_SIZE - self.CLB_SIZE) / 2
                    track_end_y = track_start_y + self.CLB_SIZE
                else:
                    # CLB-IO or IO-CLB: shortened tracks to avoid visual connection to IO
                    block_edge_margin = (self.TILE_SIZE - self.CLB_SIZE) / 2 + self.CLB_SIZE / 2
                    track_start_y = row * self.TILE_SIZE + block_edge_margin
                    track_end_y = (row + 1) * self.TILE_SIZE - block_edge_margin
                
                # Draw vertical tracks with CLB length
                track_area_start = gap_center_x - usable_gap / 2
                for t in range(self.TRACK_COUNT):
                    x = track_area_start + (t + 1) * track_spacing
                    self.ax.plot([x, x], [track_start_y, track_end_y],
                                color="#000000", linewidth=1.0, alpha=0.7, zorder=1)

        # Switch blokovi (SB) - beli kvadrati na presecima
        # Avoid drawing on outside edges and between IO blocks
        intersection_size = (self.TILE_SIZE - self.CLB_SIZE) * 0.8
        for row in range(height + 1):
            # Skip switch blocks on outside edges
            if row == 0 or row == height:
                continue
                
            gap_center_y = row * self.TILE_SIZE
            for col in range(width + 1):
                # Skip switch blocks on outside edges
                if col == 0 or col == width:
                    continue
                    
                # Check if this intersection is surrounded by IO blocks
                surrounding_positions = [
                    (col - 1, row - 1), (col, row - 1),     # bottom-left, bottom-right
                    (col - 1, row),     (col, row)          # top-left, top-right
                ]
                
                surrounding_io_count = 0
                for pos in surrounding_positions:
                    if pos in io_positions:
                        surrounding_io_count += 1
                
                # Skip if intersection is primarily surrounded by IO blocks
                if surrounding_io_count >= 2:
                    continue
                
                gap_center_x = col * self.TILE_SIZE
                rect = patches.Rectangle(
                    (gap_center_x - intersection_size/2, gap_center_y - intersection_size/2),
                    intersection_size, intersection_size,
                    facecolor='white', edgecolor='none', linewidth=0.5, zorder=1.5)
                self.ax.add_patch(rect)

    def _draw_routes(self, routing: RoutingResult, architecture: FPGAArchitecture, 
                 show_segment_ids: bool, show_directions: bool, show_signal_labels: bool):
        """Iterira kroz rute bez obzira da li objekt ima 'routes' ili 'nets'."""
        if not routing:
            return

        nets = getattr(routing, 'routes', None)
        if nets is None:
            nets = getattr(routing, 'nets', None)
        if not nets:
            return

        for ridx, route in enumerate(nets):
            base_color = self.ROUTE_COLORS[ridx % len(self.ROUTE_COLORS)]
            net_name = getattr(route, 'net_name', getattr(route, 'name', f'net_{ridx}'))

            root = getattr(route, 'root', None)
            if root and hasattr(route, 'get_all_source_to_sink_paths'):
                all_paths = route.get_all_source_to_sink_paths()
                for path_idx,path in enumerate(all_paths):
                    route_label = f"{net_name}[{path_idx}]" if show_signal_labels else ""
                    self._draw_vpr_path(path, base_color, show_directions, route_label)
            else:
                segments = getattr(route, 'segments', [])
                route_label = f"{net_name}[0]" if show_signal_labels else ""
                self._draw_vpr_path(segments, base_color, show_directions, route_label)

    def _draw_vpr_path(self, segments: List[RouteSegment], base_color: str, show_directions: bool, route_label: str = ""):
        """
        Draw VPR routing path with connecting lines between CHANX/CHANY segments
        """
        if not segments:
            return

        color = base_color
        linewidth = 3.0
        
        # Track segment endpoints for connecting lines
        segment_endpoints = []
        
        # Initialize arrows_drawn set if it doesn't exist
        if not hasattr(self, 'arrows_drawn'):
            self.arrows_drawn = set()
        
        for i, seg in enumerate(segments):
            seg_type = seg.node_type.upper()
            
            # Draw CHANX segments as horizontal lines on their tracks
            if seg_type == 'CHANX':
                gx, gy = seg.x, seg.y
                track = seg.track
                
                # Use corrected positioning
                track_y = self.chanx_y_for_track(gy, track)
                
                # CHANX should be half a CLB block to the left
                gap_start_x = gx * self.TILE_SIZE + self.CLB_SIZE - (self.CLB_SIZE / 2)
                gap_end_x = (gx + 1) * self.TILE_SIZE - (self.CLB_SIZE / 2)
                

                
                # Store endpoints for connecting lines
                start_point = (gap_start_x, track_y)  # Left end
                end_point = (gap_end_x, track_y)      # Right end
                segment_endpoints.append((start_point, end_point))
                
                # Draw connecting line from previous segment if exists (CHANX rules)
                if len(segment_endpoints) > 1:
                    prev_segment = segments[i-1]
                    prev_seg_type = prev_segment.node_type.upper()
                    
                    if prev_seg_type == 'CHANX':
                        prev_x, prev_y = prev_segment.x, prev_segment.y
                        curr_x, curr_y = seg.x, seg.y
                        
                        # CHANX to CHANX rules
                        if curr_x > prev_x:  # prev: chanX (a,b) curr: chanX(a+1,b) -> prevEnd-currStart
                            prev_connect_point = segment_endpoints[-2][1]  # prevEnd
                            curr_connect_point = segment_endpoints[-1][0]  # currStart
                        elif curr_x < prev_x:  # prev: chanX (a,b) curr: chanX(a-1,b) -> prevStart-currEnd
                            prev_connect_point = segment_endpoints[-2][0]  # prevStart
                            curr_connect_point = segment_endpoints[-1][1]  # currEnd
                        else:
                            # Same x, use default
                            prev_connect_point = segment_endpoints[-2][1]  # prevEnd
                            curr_connect_point = segment_endpoints[-1][0]  # currStart
                            
                    elif prev_seg_type == 'CHANY':
                        prev_x, prev_y = prev_segment.x, prev_segment.y
                        curr_x, curr_y = seg.x, seg.y
                        
                        # CHANY to CHANX rules - more specific conditions first
                        if curr_y < prev_y and curr_x > prev_x:  # prev: chanY (a,b) curr: chanX(a+1,b-1) -> prevEnd-currStart  
                            prev_connect_point = segment_endpoints[-2][0]  # prevEnd (bottom of CHANY)
                            curr_connect_point = segment_endpoints[-1][0]  # currStart (left of CHANX)
                        elif curr_y < prev_y:  # prev: chanY (a,b) curr: chanX(a,b-1) -> currEnd-prevStart  
                            prev_connect_point = segment_endpoints[-1][1]  # currEnd (right of CHANX)
                            curr_connect_point = segment_endpoints[-2][0]  # prevStart (top of CHANY)
                        elif curr_y == prev_y and curr_x == prev_x:  # prev: chanY (a,b) curr: chanX(a,b) -> prevEnd-currEnd
                            prev_connect_point = segment_endpoints[-2][1]  # prevEnd
                            curr_connect_point = segment_endpoints[-1][1]  # currEnd
                        elif curr_y == prev_y and curr_x > prev_x:  # prev: chanY (a,b) curr: chanX(a+1,b) -> prevEnd-currStart
                            prev_connect_point = segment_endpoints[-2][1]  # prevEnd
                            curr_connect_point = segment_endpoints[-1][0]  # currStart
                        else:
                            # Default case
                            prev_connect_point = segment_endpoints[-2][1]  # prevEnd
                            curr_connect_point = segment_endpoints[-1][0]  # currStart
                    else:
                        # Non-routing segments
                        prev_connect_point = segment_endpoints[-2][1]  # prevEnd
                        curr_connect_point = segment_endpoints[-1][0]  # currStart
                    
                    self.ax.plot([prev_connect_point[0], curr_connect_point[0]], [prev_connect_point[1], curr_connect_point[1]], 
                                '-', color=color, linewidth=linewidth-1, alpha=0.8, zorder=7)
                
                self.ax.plot([gap_start_x, gap_end_x], [track_y, track_y], '-', 
                            color=color, linewidth=linewidth, alpha=0.95, zorder=8)
                
                # Add direction arrow for CHANX based on signal flow
                if show_directions:
                    # Create unique identifier for this segment
                    seg_id = f"CHANX_{seg.x}_{seg.y}_{seg.track}"
                    if seg_id not in self.arrows_drawn:
                        self._draw_signal_direction_arrow(segments, i, gap_start_x, track_y, gap_end_x, track_y, color, 'CHANX')
                        self.arrows_drawn.add(seg_id)
            
            # Draw CHANY segments as vertical lines on their tracks
            elif seg_type == 'CHANY':
                gx, gy = seg.x, seg.y
                track = seg.track
                
                # Use corrected positioning
                track_x = self.chany_x_for_track(gx, track)
                
                # CHANY should be half a CLB block lower
                gap_start_y = gy * self.TILE_SIZE + self.CLB_SIZE - (self.CLB_SIZE / 2)
                gap_end_y = (gy + 1) * self.TILE_SIZE - (self.CLB_SIZE / 2)
                
                # Store endpoints for connecting lines
                start_point = (track_x, gap_start_y)
                end_point = (track_x, gap_end_y)
                segment_endpoints.append((start_point, end_point))
                
                # Draw connecting line from previous segment if exists (CHANY rules)
                if len(segment_endpoints) > 1:
                    prev_segment = segments[i-1]
                    prev_seg_type = prev_segment.node_type.upper()
                    
                    if prev_seg_type == 'CHANX':
                        prev_x, prev_y = prev_segment.x, prev_segment.y
                        curr_x, curr_y = seg.x, seg.y
                        
                        # CHANX to CHANY rules
                        if curr_y > prev_y and curr_x == prev_x:  # prev: chanX (a,b) curr: chanY(a,b+1) -> prevEnd-currStart
                            prev_connect_point = segment_endpoints[-2][1]  # prevEnd
                            curr_connect_point = segment_endpoints[-1][0]  # currStart
                        elif curr_y > prev_y and curr_x < prev_x:  # prev: chanX (a,b) curr: chanY(a-1,b+1) -> prevStart-currStart
                            prev_connect_point = segment_endpoints[-2][0]  # prevStart
                            curr_connect_point = segment_endpoints[-1][0]  # currStart
                        elif curr_y == prev_y and curr_x == prev_x:  # prev: chanX (a,b) curr: chanY(a,b) -> prevEnd-currEnd
                            prev_connect_point = segment_endpoints[-2][1]  # prevEnd
                            curr_connect_point = segment_endpoints[-1][1]  # currEnd
                        elif curr_y == prev_y and curr_x < prev_x:  # prev: chanX (a,b) curr: chanY(a-1,b) -> prevStart-currEnd
                            prev_connect_point = segment_endpoints[-2][0]  # prevStart
                            curr_connect_point = segment_endpoints[-1][1]  # currEnd
                        else:
                            # Default case
                            prev_connect_point = segment_endpoints[-2][1]  # prevEnd
                            curr_connect_point = segment_endpoints[-1][0]  # currStart
                            
                    elif prev_seg_type == 'CHANY':
                        prev_x, prev_y = prev_segment.x, prev_segment.y
                        curr_x, curr_y = seg.x, seg.y
                        
                        # CHANY to CHANY rules
                        if curr_y < prev_y:  # prev: chanY (a,b) curr: chanY(a,b-1) -> prevStart-currEnd
                            prev_connect_point = segment_endpoints[-2][0]  # prevStart
                            curr_connect_point = segment_endpoints[-1][1]  # currEnd
                        elif curr_y > prev_y:  # prev: chanY (a,b) curr: chanY(a,b+1) -> prevEnd-currStart
                            prev_connect_point = segment_endpoints[-2][1]  # prevEnd
                            curr_connect_point = segment_endpoints[-1][0]  # currStart
                        else:
                            # Default case
                            prev_connect_point = segment_endpoints[-2][1]  # prevEnd
                            curr_connect_point = segment_endpoints[-1][0]  # currStart
                    else:
                        # Non-routing segments
                        prev_connect_point = segment_endpoints[-2][1]  # prevEnd
                        curr_connect_point = segment_endpoints[-1][0]  # currStart
                    
                    self.ax.plot([prev_connect_point[0], curr_connect_point[0]], [prev_connect_point[1], curr_connect_point[1]], 
                                '-', color=color, linewidth=linewidth-1, alpha=0.8, zorder=7)
                
                self.ax.plot([track_x, track_x], [gap_start_y, gap_end_y], '-', 
                            color=color, linewidth=linewidth, alpha=0.95, zorder=8)
                
                # Add direction arrow for CHANY based on signal flow
                if show_directions:
                    # Create unique identifier for this segment
                    seg_id = f"CHANY_{seg.x}_{seg.y}_{seg.track}"
                    if seg_id not in self.arrows_drawn:
                        self._draw_signal_direction_arrow(segments, i, track_x, gap_start_y, track_x, gap_end_y, color, 'CHANY')
                        self.arrows_drawn.add(seg_id)
            
            # Draw SOURCE markers
            elif seg_type == 'SOURCE':
                pos = self._get_node_position(seg)
                if pos[0] >= 0 and pos[1] >= 0:
                    self.ax.plot(pos[0], pos[1], 's', color='red', markersize=8, zorder=15)
                    
                    # Connect SOURCE to next routing segment (CHANX or CHANY) if exists
                    if i + 1 < len(segments):
                        # Skip OPIN and look for first routing segment (CHANX or CHANY)
                        routing_seg = None
                        for j in range(i + 1, len(segments)):
                            seg_type = segments[j].node_type.upper()
                            if seg_type in ['CHANX', 'CHANY']:
                                routing_seg = segments[j]
                                break
                        
                        if routing_seg:
                            routing_type = routing_seg.node_type.upper()
                            if routing_type == 'CHANX':
                                # Vertical connection to CHANX
                                track_y = self.chanx_y_for_track(routing_seg.y, routing_seg.track)
                                chanx_center_x = (routing_seg.x + 0.5) * self.TILE_SIZE
                                self.ax.plot([pos[0], chanx_center_x], [pos[1], track_y], 
                                            '-', color=color, linewidth=linewidth-1, alpha=0.8, zorder=7)
                            elif routing_type == 'CHANY':
                                # Horizontal connection to CHANY
                                track_x = self.chany_x_for_track(routing_seg.x, routing_seg.track)
                                chany_center_y = (routing_seg.y + 0.5) * self.TILE_SIZE
                                self.ax.plot([pos[0], track_x], [pos[1], chany_center_y], 
                                            '-', color=color, linewidth=linewidth-1, alpha=0.8, zorder=7)
            
            # Draw SINK markers  
            elif seg_type == 'SINK':
                pos = self._get_node_position(seg)
                if pos[0] >= 0 and pos[1] >= 0:
                    self.ax.plot(pos[0], pos[1], '^', color='#00e400', markersize=8, zorder=15)
                    
                    # Connect SINK to previous routing segment (CHANX or CHANY) if exists
                    if i > 0:
                        # Look backwards for last routing segment (CHANX or CHANY), skip IPIN
                        routing_seg = None
                        for j in range(i - 1, -1, -1):
                            seg_type = segments[j].node_type.upper()
                            if seg_type in ['CHANX', 'CHANY']:
                                routing_seg = segments[j]
                                break
                        
                        if routing_seg:
                            routing_type = routing_seg.node_type.upper()
                            if routing_type == 'CHANX':
                                # Vertical connection from CHANX
                                track_y = self.chanx_y_for_track(routing_seg.y, routing_seg.track)
                                chanx_center_x = (routing_seg.x + 0.5) * self.TILE_SIZE
                                self.ax.plot([chanx_center_x, pos[0]], [track_y, pos[1]], 
                                            '-', color=color, linewidth=linewidth-1, alpha=0.8, zorder=7)
                            elif routing_type == 'CHANY':
                                # Horizontal connection from CHANY
                                track_x = self.chany_x_for_track(routing_seg.x, routing_seg.track)
                                chany_center_y = (routing_seg.y + 0.5) * self.TILE_SIZE
                                self.ax.plot([track_x, pos[0]], [pos[1], chany_center_y], 
                                            '-', color=color, linewidth=linewidth-1, alpha=0.8, zorder=7)
        
        # Crta labelu signala ako je route_label prosleđen
        if route_label:
            # Nađi SOURCE poziciju (prvi segment) za postavljanje labele
            source_seg = None
            for seg in segments:
                if seg.node_type.upper() == 'SOURCE':
                    source_seg = seg
                    break
            
            if source_seg:
                pos = self._get_node_position(source_seg)
                if pos[0] >= 0 and pos[1] >= 0:
                    # Postavi labelu iznad SOURCE markera
                    self.ax.text(
                        pos[0], pos[1] + 15,  # Offset iznad SOURCE-a
                        route_label,
                        color=color,
                        fontsize=9,
                        weight='bold',
                        ha='center',
                        va='bottom',
                        bbox=dict(
                            boxstyle='round,pad=0.3',
                            facecolor='white',
                            edgecolor=color,
                            alpha=0.9
                        ),
                        zorder=20  # Visok zorder da bude iznad svega
                    )

    


    def _is_valid_position(self, x: int, y: int) -> bool:
        """Check if position is within valid grid bounds"""
        return 0 <= x < self.grid_width and 0 <= y < self.grid_height

    def _build_manhattan_path(self, segments: List[RouteSegment]) -> List[Dict]:
        """
        Pretvara segment listu u Manhattan putanju koja prati grid:
        
        SOURCE (CLB) → OPIN → CHANX (horizontal) → CHANY (vertical) → IPIN → SINK (CLB)
        
        Pravilo: Linija može biti samo horizontalna ILI vertikalna, nikad dijagonalna
        """
        path = []
        
        for i in range(len(segments) - 1):
            curr_seg = segments[i]
            next_seg = segments[i + 1]
            
            x1, y1 = self._get_node_position(curr_seg)
            x2, y2 = self._get_node_position(next_seg)
            
            if x1 < 0 or y1 < 0 or x2 < 0 or y2 < 0:
                continue
            
            curr_type = curr_seg.node_type.upper()
            next_type = next_seg.node_type.upper()
            
            # PRAVILO 1: OPIN → CHANX/CHANY (izlaz iz CLB-a na kanal)
            if curr_type == 'OPIN' and next_type in ['CHANX', 'CHANY']:
                # Kratka linija od OPIN do najbližeg track-a
                path.append({
                    'points': [(x1, y1), (x2, y2)],
                    'type': next_type,
                    'color': self.NODE_COLORS.get(next_type, '#666666')
                })
            
            # PRAVILO 2: CHANX → CHANX (horizontalno kretanje)
            elif curr_type == 'CHANX' and next_type == 'CHANX':
                # Mora biti na istoj Y koordinati (isti track)
                if abs(y1 - y2) < 1:  # Isti track
                    path.append({
                        'points': [(x1, y1), (x2, y2)],
                        'type': 'CHANX',
                        'color': self.NODE_COLORS['CHANX']
                    })
            
            # PRAVILO 3: CHANY → CHANY (vertikalno kretanje)
            elif curr_type == 'CHANY' and next_type == 'CHANY':
                # Mora biti na istoj X koordinati (isti track)
                if abs(x1 - x2) < 1:  # Isti track
                    path.append({
                        'points': [(x1, y1), (x2, y2)],
                        'type': 'CHANY',
                        'color': self.NODE_COLORS['CHANY']
                    })
            
            # PRAVILO 4: CHANX → CHANY ili CHANY → CHANX (switch block)
            elif (curr_type == 'CHANX' and next_type == 'CHANY') or \
                (curr_type == 'CHANY' and next_type == 'CHANX'):
                # Plava dijagonalna linija u switch bloku (kao na referentnoj slici)
                path.append({
                    'points': [(x1, y1), (x2, y2)],
                    'type': 'SWITCH',
                    'color': '#1f77b4'  # Plava boja kao na slici
                })
            
            # PRAVILO 5: CHANX/CHANY → IPIN (ulaz u CLB)
            elif curr_type in ['CHANX', 'CHANY'] and next_type == 'IPIN':
                path.append({
                    'points': [(x1, y1), (x2, y2)],
                    'type': curr_type,
                    'color': self.NODE_COLORS.get(curr_type, '#666666')
                })
            
            # PRAVILO 6: IPIN → SINK (unutar CLB-a)
            elif curr_type == 'IPIN' and next_type == 'SINK':
                path.append({
                    'points': [(x1, y1), (x2, y2)],
                    'type': 'LOCAL',
                    'color': '#333333'
                })
            
            # PRAVILO 7: SOURCE → OPIN (unutar CLB-a)
            elif curr_type == 'SOURCE' and next_type == 'OPIN':
                path.append({
                    'points': [(x1, y1), (x2, y2)],
                    'type': 'LOCAL',
                    'color': '#333333'
                })
            
            else:
                # Default: pravougaona linija (fallback)
                path.append({
                    'points': [(x1, y1), (x2, y2)],
                    'type': 'OTHER',
                    'color': '#666666'
                })
        
        return path

    def _draw_segment_group(self, seg_group: Dict, base_color: str, show_directions: bool):
        """Crta jedan logički segment (može biti linija ili L-shape)"""
        points = seg_group['points']
        seg_type = seg_group['type']
        color = seg_group['color']
        
        if len(points) < 2:
            return
        
        # Debljina linije prema tipu
        if seg_type in ['CHANX', 'CHANY']:
            linewidth = 2.5
            alpha = 0.8
        elif seg_type == 'SWITCH':
            # Plave switch linije kao na referentnoj slici - srednje debljine
            linewidth = 2.0
            alpha = 0.9
        else:
            linewidth = 1.5
            alpha = 0.6
        
        # Crtaj linije između svih tačaka
        for i in range(len(points) - 1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            
            self.ax.plot([x1, x2], [y1, y2], '-', 
                        color=color, linewidth=linewidth, alpha=alpha, zorder=7)
            
            # Strelica samo za CHANX/CHANY
            if show_directions and seg_type in ['CHANX', 'CHANY']:
                self._draw_direction_arrow(x1, y1, x2, y2, color, seg_type)
                
    def _get_node_position(self, seg: RouteSegment) -> Tuple[float, float]:
        """
        Vraća (x, y) poziciju čvora
        """
        node_type = seg.node_type.upper()
        gx = seg.x
        gy = seg.y
        
        if gx < 0 or gy < 0:
            return -1, -1
        
        
        # SOURCE/SINK - check if position is on IO block
        if node_type in ['SOURCE', 'SINK']:
            # First check if seg has is_io_pad method and use it
            if hasattr(seg, 'is_io_pad') and seg.is_io_pad():
                return self._get_io_position(gx, gy)
            # Fallback: check if position is on IO block based on coordinates
            elif self._is_io_block(gx, gy):
                return self._get_io_position(gx, gy)
            else:
                return self.clb_center(gx, gy)
        
        # OPIN/IPIN
        elif node_type in ['OPIN', 'IPIN']:
            # First check if seg has is_io_pad method and use it
            if hasattr(seg, 'is_io_pad') and seg.is_io_pad():
                return self._get_io_position(gx, gy)
            # Fallback: check if position is on IO block based on coordinates
            elif self._is_io_block(gx, gy):
                return self._get_io_position(gx, gy)
            else:
                return self.clb_center(gx, gy)
        
        # CHANX
        elif node_type == 'CHANX':
            track = seg.track if 0 <= seg.track < self.TRACK_COUNT else self.TRACK_COUNT // 2
            x = (gx + 1) * self.TILE_SIZE
            y = self.chanx_y_for_track(gy, track)
            return x, y
        
        # CHANY
        elif node_type == 'CHANY':
            track = seg.track if 0 <= seg.track < self.TRACK_COUNT else self.TRACK_COUNT // 2
            x = self.chany_x_for_track(gx, track)
            y = (gy + 1) * self.TILE_SIZE
            return x, y
        
        else:
            return self.clb_center(gx, gy)

    def _get_io_position(self, gx: int, gy: int) -> Tuple[float, float]:
        """
        Vraća poziciju IO bloka na osnovu koordinata iz našeg layout-a
        Koristimo stvarno pozicioniranje IO blokova iz arhitekture
        """
        # First check if we have architecture info and this position actually has an IO block
        if self.architecture and hasattr(self.architecture, 'logic_blocks'):
            for block in self.architecture.logic_blocks:
                if block.x == gx and block.y == gy and block.type == "IO":
                    # Found matching IO block - return its center position
                    cx = (gx + 0.5) * self.TILE_SIZE
                    cy = (gy + 0.5) * self.TILE_SIZE
                    return cx, cy
        
        # Fallback: use same positioning logic as regular blocks
        # IO blocks are positioned the same way as CLB blocks - in the center of their grid position
        cx = (gx + 0.5) * self.TILE_SIZE
        cy = (gy + 0.5) * self.TILE_SIZE
        return cx, cy

    def _is_io_block(self, gx: int, gy: int) -> bool:
        """
        Detektuje da li je (gx, gy) pozicija IO bloka
        """
        width = self.architecture.width if self.architecture else 8
        height = self.architecture.height if self.architecture else 8
        
        # PRAVILO 1: Gornja ivica (y == 0)
        if gy == 0:
            return True
        
        # PRAVILO 2: Donja ivica (y == height - 1 ili y >= height)
        if gy >= height - 1:
            return True
        
        # PRAVILO 3: Leva ivica (x == 0)
        if gx == 0:
            return True
        
        # PRAVILO 4: Desna ivica (x == width - 1 ili x >= width)
        if gx >= width - 1:
            return True
        
        return False

    def _draw_signal_direction_arrow(self, segments, current_index, start_x, start_y, end_x, end_y, color, seg_type):
        """Crta strelicu u sredini segmenta na osnovu smera ka sledećem segmentu"""
        if current_index >= len(segments) - 1:
            return  # Nema sledećeg segmenta
            
        current_seg = segments[current_index]
        next_seg = segments[current_index + 1]
        
        # Debug ispis samo za krajnje segmente
        connects_result = self._connects_to_start(current_seg, next_seg, seg_type)
        if next_seg.node_type.upper() in ['IPIN', 'SINK']:
            print(f"FINAL SEGMENT: {seg_type}({current_seg.x},{current_seg.y}) -> {next_seg.node_type.upper()}({next_seg.x},{next_seg.y}), connects_to_start={connects_result}")
        
        # Sredina trenutnog segmenta
        mid_x = (start_x + end_x) / 2
        mid_y = (start_y + end_y) / 2
        
        # Određuje smer strelice na osnovu sledećeg segmenta
        if seg_type == 'CHANX':
            # Za CHANX: horizontalna strelica u sredini
            if self._connects_to_start(current_seg, next_seg, seg_type):
                # Signal ide ka početku (levi kraj) -> strelica ka levo
                arrow_length = 15
                self.ax.annotate('', xy=(mid_x - arrow_length, mid_y),
                                xytext=(mid_x, mid_y),
                                arrowprops=dict(arrowstyle='->', color=color, lw=2.5),
                                zorder=9)
            else:
                # Signal ide ka kraju (desni kraj) -> strelica ka desno
                arrow_length = 15
                self.ax.annotate('', xy=(mid_x + arrow_length, mid_y),
                                xytext=(mid_x, mid_y),
                                arrowprops=dict(arrowstyle='->', color=color, lw=2.5),
                                zorder=9)
                
        elif seg_type == 'CHANY':
            # Za CHANY: vertikalna strelica u sredini
            connects_to_start = self._connects_to_start(current_seg, next_seg, seg_type)
            if connects_to_start:
                # Signal ide ka početku (gornji kraj) -> strelica ka gore (vizuelno nadole)
                arrow_length = 15
                self.ax.annotate('', xy=(mid_x, mid_y + arrow_length),  
                                xytext=(mid_x, mid_y),
                                arrowprops=dict(arrowstyle='->', color=color, lw=2.5),
                                zorder=9)
            else:
                # Signal ide ka kraju (donji kraj) -> strelica ka dole (vizuelno nagore)
                arrow_length = 15
                self.ax.annotate('', xy=(mid_x, mid_y - arrow_length),  
                                xytext=(mid_x, mid_y),
                                arrowprops=dict(arrowstyle='->', color=color, lw=2.5),
                                zorder=9)

    def _connects_to_start(self, current_seg, next_seg, seg_type):
        """Određuje smer strelice na osnovu analize stvarnih slučajeva"""
        curr_seg_type = current_seg.node_type.upper()
        next_seg_type = next_seg.node_type.upper()
        curr_x, curr_y = current_seg.x, current_seg.y
        next_x, next_y = next_seg.x, next_seg.y
        
        # Debug za Net 0 problematične segmente
        if ((curr_seg_type == 'CHANY' and curr_x == 1 and curr_y == 3) or
            (curr_seg_type == 'CHANY' and curr_x == 4 and curr_y == 1) or
            (curr_seg_type == 'CHANX' and curr_x == 3 and curr_y == 3) or
            (curr_seg_type == 'CHANX' and curr_x == 5 and curr_y == 1)):
            print(f"NET0 DEBUG: {curr_seg_type}({curr_x},{curr_y}) -> {next_seg_type}({next_x},{next_y})")
        
        # Analizirajmo svaki slučaj iz Net 10 primera:
        
        if curr_seg_type == 'CHANX':
            if next_seg_type == 'CHANY':
                # CHANX(5,6) -> CHANY(5,6): desno = False
                if next_x == curr_x and next_y == curr_y:
                    return False  # desno
                # Ostali slučajevi kao što su već definisani
                elif next_x == curr_x and next_y == curr_y + 1:
                    return False  # desno  
                elif next_x == curr_x - 1 and next_y == curr_y + 1:
                    return True   # levo
                elif next_x == curr_x - 1 and next_y == curr_y:
                    return True   # levo
            elif next_seg_type == 'CHANX':
                if next_x == curr_x + 1:
                    return False  # desno
                elif next_x == curr_x - 1:
                    return True   # levo
            elif next_seg_type in ['IPIN', 'SINK']:
                # CHANX -> IPIN/SINK: analiziraj poziciju
                # Za Net 0 test slučaj:
                # CHANX (3,3,0) -> IPIN (3,3,0) - netačno (trenutno levo)
                # CHANX (5,1,0) -> IPIN (5,1,0) - netačno (trenutno levo)
                
                # Koristimo X koordinatu da odredimo smer
                if curr_x >= 4:  # Desni blokovi - strelica levo
                    return True   # levo
                else:  # Levi blokovi - strelica desno
                    return False  # desno
                    
        elif curr_seg_type == 'CHANY':
            if next_seg_type == 'CHANX':
                # Svi CHANY -> CHANX slučajevi u Net 10 trebaju dole
                # CHANY(5,5) -> CHANX(6,4): dole
                # CHANY(6,4) -> CHANX(6,3): gore (ali u Net 10 je pogrešno označeno)
                if next_x == curr_x + 1 and next_y == curr_y - 1:
                    return False  # dole
                elif next_x == curr_x and next_y == curr_y - 1:
                    return False  # dole
                elif next_x == curr_x and next_y == curr_y:
                    return True  # ISPRAVKA: chanY(a,b) -> chanX(a,b) = gore
                elif next_x == curr_x + 1 and next_y == curr_y:
                    return False  # PROMENIO: trebalo bi dole umesto gore
            elif next_seg_type == 'CHANY':
                # CHANY(5,6) -> CHANY(5,5): dole
                # CHANY(5,5) -> CHANY(5,4): dole  
                if next_y == curr_y - 1:
                    return False  # dole
                elif next_y == curr_y + 1:
                    return True   # gore
            elif next_seg_type in ['IPIN', 'SINK']:
                # CHANY -> IPIN/SINK: analiziraj poziciju
                # Ako je CHANY na istoj poziciji kao IPIN, onda zavisi od konteksta
                if next_x == curr_x and next_y == curr_y:
                    # Ovo je CHANY segment koji se direktno povezuje na blok
                    # Potrebno je analizirati iz kog smera dolazi signal
                    # Privremeno koristimo analizu koordinata
                    # Ako je Y koordinata CHANY veća, strelica ide dole
                    # Ako je Y koordinata CHANY manja, strelica ide gore
                    
                    # Za Net 0 test slučaj:
                    # CHANY (1,3,0) -> netačno (treba da ide dole umesto gore)
                    # CHANY (4,1,0) -> netačno (treba da ide dole umesto gore)
                    
                    # Koristimo Y koordinatu da odredimo smer
                    if curr_y >= 2:  # Viši blokovi - strelica dole
                        return False  # dole
                    else:  # Niži blokovi - strelica gore
                        return True   # gore
                else:
                    return True  # gore (default)
        
        # Default
        return False

    def _draw_direction_arrow(self, x1, y1, x2, y2, color, node_type):
        """Crta strelicu u sredini žice koja pokazuje smer"""
        mid_x = (x1 + x2) / 2
        mid_y = (y1 + y2) / 2
        
        dx = x2 - x1
        dy = y2 - y1
        
        # Normalizuj vektor
        length = (dx**2 + dy**2)**0.5
        if length < 1:
            return
        
        dx /= length
        dy /= length
        
        # Veličina strelice - povećana da se bolje vidi
        arrow_size = 15
        
        self.ax.annotate('', xy=(mid_x + dx*arrow_size, mid_y + dy*arrow_size),
                        xytext=(mid_x, mid_y),
                        arrowprops=dict(arrowstyle='->', color=color, lw=2.5),
                        zorder=9)

    def _extract_all_paths(self, root_node) -> List[List[RouteSegment]]:
        """
        Ekstraktuje sve putanje od ROOT do SINK čvorova (tree traversal)
        """
        all_paths = []
        
        def traverse(node, current_path):
            """Rekurzivna DFS traversal"""
            if not node:
                return
            
            # ✅ node JE već RouteSegment (ne node.segment)
            new_path = current_path + [node]
            
            # Ako je SINK, završi putanju
            node_type = getattr(node, 'node_type', '').upper()
            if node_type == 'SINK':
                all_paths.append(new_path)
                return
            
            # Rekurzivno obiđi decu
            children = getattr(node, 'children', [])
            if children:
                for child in children:
                    traverse(child, new_path)
        
        traverse(root_node, [])
        return all_paths if all_paths else [[]]


    def _draw_bounding_boxes_heatmap(self, routing: RoutingResult):
        """
        Crta crne bounding boxove sa malom alpha vrednošću za heat mapu.
        Preklapanja se vide kao tamnija siva područja.
        """
        nets = getattr(routing, 'routes', getattr(routing, 'nets', []))
        
        for ridx, net in enumerate(nets):
            # ✅ Dobavi segmente (tree ili flat lista)
            segments = []
            
            if hasattr(net, 'root') and net.root:
                # Tree struktura - koristi _extract_all_paths
                paths = self._extract_all_paths(net.root)
                for path in paths:
                    segments.extend(path)
            elif hasattr(net, 'get_all_source_to_sink_paths'):
                # Ako postoji direktna metoda
                paths = net.get_all_source_to_sink_paths()
                for path in paths:
                    segments.extend(path)
            else:
                # Flat lista segmenata
                segments = getattr(net, 'segments', [])
            
            if not segments:
                continue
            
            # ✅ Filtriraj validne koordinate
            valid_segments = [s for s in segments 
                            if hasattr(s, 'x') and hasattr(s, 'y') 
                            and s.x >= 0 and s.y >= 0]
            
            if not valid_segments:
                continue
            
            # ✅ Nađi bounding box koordinate
            min_x = min(s.x for s in valid_segments)
            max_x = max(s.x for s in valid_segments)
            min_y = min(s.y for s in valid_segments)
            max_y = max(s.y for s in valid_segments)
            
            # ✅ Konvertuj u piksel koordinate (pomereno za pola CLB bloka gore i desno)
            offset_x = self.CLB_SIZE / 2  # Pola CLB bloka desno
            offset_y = self.CLB_SIZE / 2  # Pola CLB bloka gore
            
            x1 = min_x * self.TILE_SIZE + offset_x
            x2 = (max_x + 1) * self.TILE_SIZE + offset_x
            y1 = min_y * self.TILE_SIZE + offset_y
            y2 = (max_y + 1) * self.TILE_SIZE + offset_y
            
            # ✅ Crni bounding box sa malom alpha za heat map
            rect = patches.Rectangle(
                (x1, y1), 
                x2 - x1, 
                y2 - y1,
                linewidth=0,           
                edgecolor='none',        
                facecolor='black',         # Crna boja
                alpha=0.08,               # Mala alpha vrednost - preklapanja će biti tamnija
                zorder=3
            )
            self.ax.add_patch(rect)

    def _draw_bounding_boxes(self, routing: RoutingResult, show_labels: bool = False):
        """
        Crta bounding box (HPWL) za svaki signal
        
        HPWL (Half-Perimeter Wire Length) = (max_x - min_x + 1) + (max_y - min_y + 1)
        """
        nets = getattr(routing, 'routes', getattr(routing, 'nets', []))
        
        for ridx, net in enumerate(nets):
            # ✅ Dobavi segmente (tree ili flat lista)
            segments = []
            
            if hasattr(net, 'root') and net.root:
                # Tree struktura - koristi _extract_all_paths
                paths = self._extract_all_paths(net.root)
                for path in paths:
                    segments.extend(path)
            elif hasattr(net, 'get_all_source_to_sink_paths'):
                # Ako postoji direktna metoda
                paths = net.get_all_source_to_sink_paths()
                for path in paths:
                    segments.extend(path)
            else:
                # Flat lista segmenata
                segments = getattr(net, 'segments', [])
            
            if not segments:
                continue
            
            # ✅ Filtriraj validne koordinate
            valid_segments = [s for s in segments 
                            if hasattr(s, 'x') and hasattr(s, 'y') 
                            and s.x >= 0 and s.y >= 0]
            
            if not valid_segments:
                continue
            
            # ✅ Nađi bounding box koordinate
            min_x = min(s.x for s in valid_segments)
            max_x = max(s.x for s in valid_segments)
            min_y = min(s.y for s in valid_segments)
            max_y = max(s.y for s in valid_segments)
            
            # ✅ Konvertuj u piksel koordinate (pomereno za pola CLB bloka gore i desno)
            offset_x = self.CLB_SIZE / 2  # Pola CLB bloka desno
            offset_y = self.CLB_SIZE / 2  # Pola CLB bloka gore
            
            x1 = min_x * self.TILE_SIZE + offset_x
            x2 = (max_x + 1) * self.TILE_SIZE + offset_x
            y1 = min_y * self.TILE_SIZE + offset_y
            y2 = (max_y + 1) * self.TILE_SIZE + offset_y
            
            # ✅ Boja signala
            signal_color = self.ROUTE_COLORS[ridx % len(self.ROUTE_COLORS)]
            
            # ✅ Crta isprekidani pravougaonik
            rect = patches.Rectangle(
                (x1, y1), 
            x2 - x1, 
            y2 - y1,
            linewidth=0,           
            edgecolor='none',        
            facecolor=signal_color,  # Boja signala
            alpha=0.15,               
            zorder=3
            )
            self.ax.add_patch(rect)
            
            # ✅ HPWL tekst (gornji levi ugao) - prikaži samo ako je show_labels=True
            if show_labels:
                hpwl = (max_x - min_x + 1) + (max_y - min_y + 1)
                net_name = getattr(net, 'net_name', getattr(net, 'name', f'net_{ridx}'))
                
                self.ax.text(
                    x1 + 5, y2 - 5,  # Gornji levi ugao + offset
                    f"{net_name}\nHPWL={hpwl}",
                    color=signal_color,  # Boja signala za tekst
                    fontsize=8,
                    weight='bold',
                    bbox=dict(
                        boxstyle='round,pad=0.4',
                        facecolor='white',
                        edgecolor=signal_color,  # Boja signala za ivicu
                        alpha=0.85
                    ),
                    zorder=12
                )

    def _draw_legend(self, routing: RoutingResult):
        """
        Legenda sa SOURCE/SINK markerima u bojama signala
        """
        legend_elements = []
        
        nets = getattr(routing, 'routes', getattr(routing, 'nets', []))
        
        for i, net in enumerate(nets[:8]):  # Prvih 8 signala
            net_name = getattr(net, 'net_name', getattr(net, 'name', f'net_{i}'))
            color = self.ROUTE_COLORS[i % len(self.ROUTE_COLORS)]
            
            # ✅ SOURCE marker (kvadrat) + linija
            legend_elements.append(
                Line2D([0], [0], 
                    marker='s',              # Kvadrat
                    color=color,             # Boja linije
                    linewidth=2,
                    markersize=8,
                    markerfacecolor=color,   # Boja kvadrata
                    markeredgecolor='white',
                    markeredgewidth=1,
                    label=net_name)
            )
        
        # Separator
        legend_elements.append(Line2D([0], [0], color='none', label=''))
        
        legend_elements.extend ([
            Line2D([0], [0], marker='s', color='w', markerfacecolor=self.NODE_COLORS['SOURCE'],
                markersize=8, label='SOURCE', markeredgecolor='none'),  #
            Line2D([0], [0], marker='^', color='w', markerfacecolor=self.NODE_COLORS['SINK'],
                markersize=8, label='SINK', markeredgecolor='none')
        ])
        
        self.ax.legend(handles=legend_elements, loc='upper right', fontsize=8, framealpha=0.9)

    def _add_title_and_subtitle(self, show_heatmap: bool, show_signals: bool, 
                                show_bounding_boxes: bool, architecture_file: str, 
                                routing_file: str, filter_type: str, filter_value: int):
        """
        Dodaje naslov i podnaslov na osnovu prikazanih opcija i filtera
        """
        # Odredi glavni naslov
        if show_heatmap:
            title = "HEAT MAPA"
        elif show_signals and not show_bounding_boxes:
            title = "PRIKAZ SIGNALA"
        elif show_bounding_boxes:
            title = "BOUNDING BOXOVI"
        else:
            title = "FPGA VIZUALIZACIJA"
        
        # Postavi naslov (gornji deo slike)
        self.fig.suptitle(title, fontsize=20, fontweight='bold', y=0.98)
        
        # GORNJI LEVI ĆOŠAK - Nazivi fajlova
        file_info_lines = []
        if architecture_file:
            arch_name = os.path.basename(architecture_file)
            file_info_lines.append(f"Arhitektura: {arch_name}")
        
        if routing_file:
            route_name = os.path.basename(routing_file)
            file_info_lines.append(f"Routing: {route_name}")
        
        if file_info_lines:
            file_info_text = "\n".join(file_info_lines)
            self.ax.text(0.02, 0.98, file_info_text, 
                        transform=self.ax.transAxes,
                        fontsize=11, 
                        ha='left', 
                        va='top',
                        color='#2c3e50',
                        weight='bold',
                        bbox=dict(
                            boxstyle='round,pad=0.6',
                            facecolor='white',
                            edgecolor='#3498db',
                            linewidth=2,
                            alpha=0.95
                        ),
                        zorder=100)
        
        # DONJI DEO SLIKE - Filter informacije
        if filter_type and filter_value is not None:
            if filter_type == "first":
                filter_text = f"Filter: Prvih {filter_value} signala"
            elif filter_type == "last":
                filter_text = f"Filter: Poslednjih {filter_value} signala"
            elif filter_type == "less_than":
                filter_text = f"Filter: Signali sa manje od {filter_value} segmenata"
            elif filter_type == "more_than":
                filter_text = f"Filter: Signali sa više od {filter_value} segmenata"
            else:
                filter_text = None
            
            if filter_text:
                self.ax.text(0.5, 0.02, filter_text, 
                            transform=self.ax.transAxes,
                            fontsize=12, 
                            ha='center', 
                            va='bottom',
                            color='white',
                            weight='bold',
                            bbox=dict(
                                boxstyle='round,pad=0.5',
                                facecolor='#e74c3c',
                                edgecolor='#c0392b',
                                linewidth=2,
                                alpha=0.95
                            ),
                            zorder=100)

    def _save(self, path: str, dpi: int):
        # Only create directory if path contains a directory component
        dir_path = os.path.dirname(path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        
        self.fig.savefig(path, format='png', dpi=dpi, facecolor="white", 
                        pad_inches=0, bbox_inches=None)
        plt.close(self.fig)
        self.fig = None
        self.ax = None