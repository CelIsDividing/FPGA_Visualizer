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
    - IPIN (black dot) at the junction of wire and cluster
    - OPIN (gray dot) at the junction of cluster and wire
    - CHANX (blue line with arrow →)
    - CHANY (red line with arrow ↑)
    - SOURCE (red square)
    - SINK (green triangle)
    - SB (thin lines at intersections)
    """

    # Colors by node type
    NODE_COLORS = {
        'SOURCE': '#d62728',    # Red
        'SINK': "#00e400",      # Green
        'OPIN': '#7f7f7f',      # Gray
        'IPIN': '#000000',      # Black
        'CHANX': '#1f77b4',     # Blue
        'CHANY': '#ff7f0e',     # Orange/red
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

        # Calculate HPWL statistics for each block if the heat map is enabled
        block_hpwl_stats = None
        if show_heatmap and routing:
            block_hpwl_stats = self._calculate_block_hpwl_coverage(routing, w, h)

        self._draw_blocks(w, h, block_hpwl_stats)
        self._draw_tracks(w, h)
        
        # Show colored bounding boxes if the checkbox is enabled
        if show_bounding_boxes:
            self._draw_bounding_boxes(routing, show_bounding_box_labels)
        
        # Show signals (routes and nodes) only if the checkbox is enabled
        if show_signals:
            self._draw_routes(routing, architecture, show_segment_ids, show_directions, show_signal_labels)

        if show_legend and routing and routing.routes and show_signals:
            self._draw_legend(routing)
        
        # Add title and subtitle based on the options
        self._add_title_and_subtitle(show_heatmap, show_signals, show_bounding_boxes, 
                                     architecture_file, routing_file, filter_type, filter_value)
        
        self._save(output_path, dpi)
        return self.fig
    
    def _calculate_block_hpwl_coverage(self, routing: RoutingResult, width: int, height: int) -> Dict:
        """
        Calculates the average HPWL value for each block based on the bounding boxes covering it
        Returns: Dict[(x, y)] = average_hpwl
        """
        block_hpwl_sums = {}  # (x, y) -> [list of HPWL values]
        
        nets = getattr(routing, 'routes', getattr(routing, 'nets', []))
        
        for ridx, net in enumerate(nets):
            # Fetch segments
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
            
            # Filter valid coordinates
            valid_segments = [s for s in segments 
                            if hasattr(s, 'x') and hasattr(s, 'y') 
                            and s.x >= 0 and s.y >= 0]
            
            if not valid_segments:
                continue
            
            # Find bounding box coordinates
            min_x = min(s.x for s in valid_segments)
            max_x = max(s.x for s in valid_segments)
            min_y = min(s.y for s in valid_segments)
            max_y = max(s.y for s in valid_segments)
            
            # Calculate HPWL
            hpwl = (max_x - min_x + 1) + (max_y - min_y + 1)
            
            # For each block covered by this bounding box, add the HPWL value
            for x in range(min_x, max_x + 1):
                for y in range(min_y, max_y + 1):
                    if 0 <= x < width and 0 <= y < height:
                        if (x, y) not in block_hpwl_sums:
                            block_hpwl_sums[(x, y)] = []
                        block_hpwl_sums[(x, y)].append(hpwl)
        
        # Calculate the average for each block
        block_avg_hpwl = {}
        for (x, y), hpwl_list in block_hpwl_sums.items():
            block_avg_hpwl[(x, y)] = sum(hpwl_list) / len(hpwl_list)
        
        return block_avg_hpwl
    
    def _get_heatmap_color(self, value: float, min_val: float, max_val: float) -> str:
        """
        Calculates the color on a gradient from yellow (smallest value) through orange to red (largest value)
        """
        if min_val == max_val:
            return "#FFA500"  # Orange if all values are equal
        
        # Normalize the value between 0 and 1
        normalized = (value - min_val) / (max_val - min_val)
        
        # Gradient: yellow (0) -> orange (0.5) -> red (1)
        if normalized < 0.5:
            # Yellow (#FFFF00) -> Orange (#FFA500)
            t = normalized * 2  # 0 to 1
            r = 255
            g = int(255 - (85 * t))  # 255 -> 170
            b = int(0 + (0 * t))     # 0 -> 0
        else:
            # Orange (#FFA500) -> Red (#FF0000)
            t = (normalized - 0.5) * 2  # 0 to 1
            r = 255
            g = int(165 - (165 * t))  # 165 -> 0
            b = 0
        
        return f"#{r:02X}{g:02X}{b:02X}"
    
    # ---------- Geometry helpers ----------
    def io_center(self, gx: int, gy: int) -> Tuple[float, float]:
        """Alias for _get_io_position() - for compatibility"""
        return self._get_io_position(gx, gy)
    
    def clb_center(self, x: int, y: int):
        """CLB/IO block center - now works directly with grid coordinates"""
        return (x + 0.5) * self.TILE_SIZE, (y + 0.5) * self.TILE_SIZE

    def chanx_y_for_track(self, row: int, track: int):
        """Y coordinate of the horizontal track - matching track drawing exactly"""
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
        """X coordinate of the vertical track - matching track drawing exactly"""
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
        
        # Find the minimum and maximum HPWL values for the color gradient
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
                
                # Fetch the average HPWL value for this block if it exists
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
        
        # Determine the block color
        if avg_hpwl is not None and min_hpwl is not None and max_hpwl is not None:
            facecolor = self._get_heatmap_color(avg_hpwl, min_hpwl, max_hpwl)
        else:
            facecolor = "#cccccc"  # Light gray
        
        rect = patches.Rectangle(
            (cx - self.CLB_SIZE/2, cy - self.CLB_SIZE/2),
            self.CLB_SIZE, self.CLB_SIZE,
            facecolor=facecolor, edgecolor="#999999", linewidth=2, zorder=2)
        self.ax.add_patch(rect)
        
        # Show the average HPWL value if it exists, otherwise "CLB"
        if avg_hpwl is not None:
            label = f"{avg_hpwl:.1f}"
            fontsize = 10
            text_color = "white"  # Always white color for text
        else:
            label = "CLB"
            fontsize = 12
            text_color = "black"
            
        self.ax.text(cx, cy, label, color=text_color, ha="center", va="center",
                    fontsize=fontsize, weight='bold', zorder=10)  # zorder=10 above the heat map
    
    def _draw_io_block_at_grid(self, grid_x: int, grid_y: int, avg_hpwl: float = None, min_hpwl: float = None, max_hpwl: float = None):
        """Draw an IO block at grid position (grid_x, grid_y)"""
        cx, cy = self.clb_center(grid_x, grid_y)  # Use same positioning as CLB
        
        # Determine the block color
        if avg_hpwl is not None and min_hpwl is not None and max_hpwl is not None:
            facecolor = self._get_heatmap_color(avg_hpwl, min_hpwl, max_hpwl)
        else:
            facecolor = "#666666"  # Darker gray
        
        rect = patches.Rectangle(
            (cx - self.IO_SIZE/2, cy - self.IO_SIZE/2),
            self.IO_SIZE, self.IO_SIZE,
            facecolor=facecolor, edgecolor="#333333", linewidth=2, zorder=2)
        self.ax.add_patch(rect)
        
        # Show the average HPWL value if it exists, otherwise "IO"
        if avg_hpwl is not None:
            label = f"{avg_hpwl:.1f}"
            fontsize = 9
            text_color = "white"  # Always white color for text
        else:
            label = "IO"
            fontsize = 11
            text_color = "white"
            
        self.ax.text(cx, cy, label, color=text_color, ha="center", va="center",
                    fontsize=fontsize, weight='bold', zorder=10)  # zorder=10 above the heat map

    def _draw_io_block(self, cx: int, cy: int):
        rect = patches.Rectangle(
            (cx - self.IO_SIZE/2, cy - self.IO_SIZE/2),
            self.IO_SIZE, self.IO_SIZE,
            facecolor="#666666", edgecolor="#333333", linewidth=2, zorder=2)  # Darker gray with border
        self.ax.add_patch(rect)
        self.ax.text(cx, cy, "IO", color="white", ha="center", va="center",
                    fontsize=11, weight='bold', zorder=3)

    def _draw_tracks(self, width: int, height: int):
        """Draws routing channels (CHANX and CHANY) between blocks - short strips in each gap"""
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

        # Horizontal tracks (CHANX) - short strips in each horizontal gap
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

        # Vertical tracks (CHANY) - short strips in each vertical gap  
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

        # Switch blocks (SB) - white squares at intersections
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
        """Iterates through routes regardless of whether the object has 'routes' or 'nets'."""
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
        
        # Draws the signal label if route_label was passed
        if route_label:
            # Find the SOURCE position (first segment) to place the label
            source_seg = None
            for seg in segments:
                if seg.node_type.upper() == 'SOURCE':
                    source_seg = seg
                    break
            
            if source_seg:
                pos = self._get_node_position(source_seg)
                if pos[0] >= 0 and pos[1] >= 0:
                    # Place the label above the SOURCE marker
                    self.ax.text(
                        pos[0], pos[1] + 15,  # Offset above the SOURCE
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
                        zorder=20  # High zorder so it stays above everything
                    )

    


    def _is_valid_position(self, x: int, y: int) -> bool:
        """Check if position is within valid grid bounds"""
        return 0 <= x < self.grid_width and 0 <= y < self.grid_height

    def _build_manhattan_path(self, segments: List[RouteSegment]) -> List[Dict]:
        """
        Converts the segment list into a Manhattan path that follows the grid:
        
        SOURCE (CLB) → OPIN → CHANX (horizontal) → CHANY (vertical) → IPIN → SINK (CLB)
        
        Rule: The line can be only horizontal OR vertical, never diagonal
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
            
            # RULE 1: OPIN → CHANX/CHANY (exit from the CLB to the channel)
            if curr_type == 'OPIN' and next_type in ['CHANX', 'CHANY']:
                # Short line from OPIN to the nearest track
                path.append({
                    'points': [(x1, y1), (x2, y2)],
                    'type': next_type,
                    'color': self.NODE_COLORS.get(next_type, '#666666')
                })
            
            # RULE 2: CHANX → CHANX (horizontal movement)
            elif curr_type == 'CHANX' and next_type == 'CHANX':
                # Must be at the same Y coordinate (same track)
                if abs(y1 - y2) < 1:  # Same track
                    path.append({
                        'points': [(x1, y1), (x2, y2)],
                        'type': 'CHANX',
                        'color': self.NODE_COLORS['CHANX']
                    })
            
            # RULE 3: CHANY → CHANY (vertical movement)
            elif curr_type == 'CHANY' and next_type == 'CHANY':
                # Must be at the same X coordinate (same track)
                if abs(x1 - x2) < 1:  # Same track
                    path.append({
                        'points': [(x1, y1), (x2, y2)],
                        'type': 'CHANY',
                        'color': self.NODE_COLORS['CHANY']
                    })
            
            # RULE 4: CHANX → CHANY or CHANY → CHANX (switch block)
            elif (curr_type == 'CHANX' and next_type == 'CHANY') or \
                (curr_type == 'CHANY' and next_type == 'CHANX'):
                # Blue diagonal line in the switch block (as in the reference image)
                path.append({
                    'points': [(x1, y1), (x2, y2)],
                    'type': 'SWITCH',
                    'color': '#1f77b4'  # Blue color as in the image
                })
            
            # RULE 5: CHANX/CHANY → IPIN (input to the CLB)
            elif curr_type in ['CHANX', 'CHANY'] and next_type == 'IPIN':
                path.append({
                    'points': [(x1, y1), (x2, y2)],
                    'type': curr_type,
                    'color': self.NODE_COLORS.get(curr_type, '#666666')
                })
            
            # RULE 6: IPIN → SINK (inside the CLB)
            elif curr_type == 'IPIN' and next_type == 'SINK':
                path.append({
                    'points': [(x1, y1), (x2, y2)],
                    'type': 'LOCAL',
                    'color': '#333333'
                })
            
            # RULE 7: SOURCE → OPIN (inside the CLB)
            elif curr_type == 'SOURCE' and next_type == 'OPIN':
                path.append({
                    'points': [(x1, y1), (x2, y2)],
                    'type': 'LOCAL',
                    'color': '#333333'
                })
            
            else:
                # Default: rectangular line (fallback)
                path.append({
                    'points': [(x1, y1), (x2, y2)],
                    'type': 'OTHER',
                    'color': '#666666'
                })
        
        return path

    def _draw_segment_group(self, seg_group: Dict, base_color: str, show_directions: bool):
        """Draws one logical segment (can be a line or L-shape)"""
        points = seg_group['points']
        seg_type = seg_group['type']
        color = seg_group['color']
        
        if len(points) < 2:
            return
        
        # Line thickness by type
        if seg_type in ['CHANX', 'CHANY']:
            linewidth = 2.5
            alpha = 0.8
        elif seg_type == 'SWITCH':
            # Blue switch lines as in the reference image - medium thickness
            linewidth = 2.0
            alpha = 0.9
        else:
            linewidth = 1.5
            alpha = 0.6
        
        # Draw lines between all points
        for i in range(len(points) - 1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            
            self.ax.plot([x1, x2], [y1, y2], '-', 
                        color=color, linewidth=linewidth, alpha=alpha, zorder=7)
            
            # Arrow only for CHANX/CHANY
            if show_directions and seg_type in ['CHANX', 'CHANY']:
                self._draw_direction_arrow(x1, y1, x2, y2, color, seg_type)
                
    def _get_node_position(self, seg: RouteSegment) -> Tuple[float, float]:
        """
        Returns the (x, y) position of the node
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
        Returns the position of the IO block based on coordinates from our layout
        We use the actual positioning of IO blocks from the architecture
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
        Detects whether (gx, gy) is the position of an IO block
        """
        width = self.architecture.width if self.architecture else 8
        height = self.architecture.height if self.architecture else 8
        
        # RULE 1: Top edge (y == 0)
        if gy == 0:
            return True
        
        # RULE 2: Bottom edge (y == height - 1 or y >= height)
        if gy >= height - 1:
            return True
        
        # RULE 3: Left edge (x == 0)
        if gx == 0:
            return True
        
        # RULE 4: Right edge (x == width - 1 or x >= width)
        if gx >= width - 1:
            return True
        
        return False

    def _draw_signal_direction_arrow(self, segments, current_index, start_x, start_y, end_x, end_y, color, seg_type):
        """Draws an arrow in the middle of the segment based on the direction toward the next segment"""
        if current_index >= len(segments) - 1:
            return  # No next segment
            
        current_seg = segments[current_index]
        next_seg = segments[current_index + 1]
        
        # Debug print only for final segments
        connects_result = self._connects_to_start(current_seg, next_seg, seg_type)
        if next_seg.node_type.upper() in ['IPIN', 'SINK']:
            print(f"FINAL SEGMENT: {seg_type}({current_seg.x},{current_seg.y}) -> {next_seg.node_type.upper()}({next_seg.x},{next_seg.y}), connects_to_start={connects_result}")
        
        # Middle of the current segment
        mid_x = (start_x + end_x) / 2
        mid_y = (start_y + end_y) / 2
        
        # Determines the arrow direction based on the next segment
        if seg_type == 'CHANX':
            # For CHANX: horizontal arrow in the middle
            if self._connects_to_start(current_seg, next_seg, seg_type):
                # Signal goes toward the start (left end) -> arrow to the left
                arrow_length = 15
                self.ax.annotate('', xy=(mid_x - arrow_length, mid_y),
                                xytext=(mid_x, mid_y),
                                arrowprops=dict(arrowstyle='->', color=color, lw=2.5),
                                zorder=9)
            else:
                # Signal goes toward the end (right end) -> arrow to the right
                arrow_length = 15
                self.ax.annotate('', xy=(mid_x + arrow_length, mid_y),
                                xytext=(mid_x, mid_y),
                                arrowprops=dict(arrowstyle='->', color=color, lw=2.5),
                                zorder=9)
                
        elif seg_type == 'CHANY':
            # For CHANY: vertical arrow in the middle
            connects_to_start = self._connects_to_start(current_seg, next_seg, seg_type)
            if connects_to_start:
                # Signal goes toward the start (upper end) -> arrow up (visually downward)
                arrow_length = 15
                self.ax.annotate('', xy=(mid_x, mid_y + arrow_length),  
                                xytext=(mid_x, mid_y),
                                arrowprops=dict(arrowstyle='->', color=color, lw=2.5),
                                zorder=9)
            else:
                # Signal goes toward the end (lower end) -> arrow down (visually upward)
                arrow_length = 15
                self.ax.annotate('', xy=(mid_x, mid_y - arrow_length),  
                                xytext=(mid_x, mid_y),
                                arrowprops=dict(arrowstyle='->', color=color, lw=2.5),
                                zorder=9)

    def _connects_to_start(self, current_seg, next_seg, seg_type):
        """Determines the arrow direction based on analysis of real cases"""
        curr_seg_type = current_seg.node_type.upper()
        next_seg_type = next_seg.node_type.upper()
        curr_x, curr_y = current_seg.x, current_seg.y
        next_x, next_y = next_seg.x, next_seg.y
        
        # Debug for Net 0 problematic segments
        if ((curr_seg_type == 'CHANY' and curr_x == 1 and curr_y == 3) or
            (curr_seg_type == 'CHANY' and curr_x == 4 and curr_y == 1) or
            (curr_seg_type == 'CHANX' and curr_x == 3 and curr_y == 3) or
            (curr_seg_type == 'CHANX' and curr_x == 5 and curr_y == 1)):
            print(f"NET0 DEBUG: {curr_seg_type}({curr_x},{curr_y}) -> {next_seg_type}({next_x},{next_y})")
        
        # Let's analyze each case from the Net 10 example:
        
        if curr_seg_type == 'CHANX':
            if next_seg_type == 'CHANY':
                # CHANX(5,6) -> CHANY(5,6): right = False
                if next_x == curr_x and next_y == curr_y:
                    return False  # right
                # Other cases as already defined
                elif next_x == curr_x and next_y == curr_y + 1:
                    return False  # right  
                elif next_x == curr_x - 1 and next_y == curr_y + 1:
                    return True   # left
                elif next_x == curr_x - 1 and next_y == curr_y:
                    return True   # left
            elif next_seg_type == 'CHANX':
                if next_x == curr_x + 1:
                    return False  # right
                elif next_x == curr_x - 1:
                    return True   # left
            elif next_seg_type in ['IPIN', 'SINK']:
                # CHANX -> IPIN/SINK: analyze the position
                # For the Net 0 test case:
                # CHANX (3,3,0) -> IPIN (3,3,0) - incorrect (currently left)
                # CHANX (5,1,0) -> IPIN (5,1,0) - incorrect (currently left)
                
                # We use the X coordinate to determine the direction
                if curr_x >= 4:  # Right blocks - arrow to the left
                    return True   # left
                else:  # Left blocks - arrow to the right
                    return False  # right
                    
        elif curr_seg_type == 'CHANY':
            if next_seg_type == 'CHANX':
                # All CHANY -> CHANX cases in Net 10 need down
                # CHANY(5,5) -> CHANX(6,4): down
                # CHANY(6,4) -> CHANX(6,3): up (but in Net 10 it is marked incorrectly)
                if next_x == curr_x + 1 and next_y == curr_y - 1:
                    return False  # down
                elif next_x == curr_x and next_y == curr_y - 1:
                    return False  # down
                elif next_x == curr_x and next_y == curr_y:
                    return True  # FIX: chanY(a,b) -> chanX(a,b) = up
                elif next_x == curr_x + 1 and next_y == curr_y:
                    return False  # CHANGED: should be down instead of up
            elif next_seg_type == 'CHANY':
                # CHANY(5,6) -> CHANY(5,5): down
                # CHANY(5,5) -> CHANY(5,4): down  
                if next_y == curr_y - 1:
                    return False  # down
                elif next_y == curr_y + 1:
                    return True   # up
            elif next_seg_type in ['IPIN', 'SINK']:
                # CHANY -> IPIN/SINK: analyze the position
                # If CHANY is at the same position as IPIN, it depends on the context
                if next_x == curr_x and next_y == curr_y:
                    # This is a CHANY segment that connects directly to the block
                    # We need to analyze from which direction the signal comes
                    # We temporarily use coordinate analysis
                    # If the Y coordinate of CHANY is larger, the arrow goes down
                    # If the Y coordinate of CHANY is smaller, the arrow goes up
                    
                    # For the Net 0 test case:
                    # CHANY (1,3,0) -> incorrect (should go down instead of up)
                    # CHANY (4,1,0) -> incorrect (should go down instead of up)
                    
                    # We use the Y coordinate to determine the direction
                    if curr_y >= 2:  # Higher blocks - arrow down
                        return False  # down
                    else:  # Lower blocks - arrow up
                        return True   # up
                else:
                    return True  # up (default)
        
        # Default
        return False

    def _draw_direction_arrow(self, x1, y1, x2, y2, color, node_type):
        """Draws an arrow in the middle of the wire showing the direction"""
        mid_x = (x1 + x2) / 2
        mid_y = (y1 + y2) / 2
        
        dx = x2 - x1
        dy = y2 - y1
        
        # Normalize the vector
        length = (dx**2 + dy**2)**0.5
        if length < 1:
            return
        
        dx /= length
        dy /= length
        
        # Arrow size - increased for better visibility
        arrow_size = 15
        
        self.ax.annotate('', xy=(mid_x + dx*arrow_size, mid_y + dy*arrow_size),
                        xytext=(mid_x, mid_y),
                        arrowprops=dict(arrowstyle='->', color=color, lw=2.5),
                        zorder=9)

    def _extract_all_paths(self, root_node) -> List[List[RouteSegment]]:
        """
        Extracts all paths from ROOT to SINK nodes (tree traversal)
        """
        all_paths = []
        
        def traverse(node, current_path):
            """Recursive DFS traversal"""
            if not node:
                return
            
            # ✅ node IS already a RouteSegment (not node.segment)
            new_path = current_path + [node]
            
            # If it is SINK, finish the path
            node_type = getattr(node, 'node_type', '').upper()
            if node_type == 'SINK':
                all_paths.append(new_path)
                return
            
            # Recursively traverse the children
            children = getattr(node, 'children', [])
            if children:
                for child in children:
                    traverse(child, new_path)
        
        traverse(root_node, [])
        return all_paths if all_paths else [[]]


    def _draw_bounding_boxes_heatmap(self, routing: RoutingResult):
        """
        Draws black bounding boxes with a small alpha value for the heat map.
        Overlaps appear as darker gray areas.
        """
        nets = getattr(routing, 'routes', getattr(routing, 'nets', []))
        
        for ridx, net in enumerate(nets):
            # ✅ Fetch segments (tree or flat list)
            segments = []
            
            if hasattr(net, 'root') and net.root:
                # Tree structure - uses _extract_all_paths
                paths = self._extract_all_paths(net.root)
                for path in paths:
                    segments.extend(path)
            elif hasattr(net, 'get_all_source_to_sink_paths'):
                # If a direct method exists
                paths = net.get_all_source_to_sink_paths()
                for path in paths:
                    segments.extend(path)
            else:
                # Flat list of segments
                segments = getattr(net, 'segments', [])
            
            if not segments:
                continue
            
            # ✅ Filter valid coordinates
            valid_segments = [s for s in segments 
                            if hasattr(s, 'x') and hasattr(s, 'y') 
                            and s.x >= 0 and s.y >= 0]
            
            if not valid_segments:
                continue
            
            # ✅ Find bounding box coordinates
            min_x = min(s.x for s in valid_segments)
            max_x = max(s.x for s in valid_segments)
            min_y = min(s.y for s in valid_segments)
            max_y = max(s.y for s in valid_segments)
            
            # ✅ Convert to pixel coordinates (shifted by half a CLB block up and right)
            offset_x = self.CLB_SIZE / 2  # Half a CLB block to the right
            offset_y = self.CLB_SIZE / 2  # Half a CLB block up
            
            x1 = min_x * self.TILE_SIZE + offset_x
            x2 = (max_x + 1) * self.TILE_SIZE + offset_x
            y1 = min_y * self.TILE_SIZE + offset_y
            y2 = (max_y + 1) * self.TILE_SIZE + offset_y
            
            # ✅ Black bounding box with small alpha for the heat map
            rect = patches.Rectangle(
                (x1, y1), 
                x2 - x1, 
                y2 - y1,
                linewidth=0,           
                edgecolor='none',        
                facecolor='black',         # Black color
                alpha=0.08,               # Small alpha value - overlaps will be darker
                zorder=3
            )
            self.ax.add_patch(rect)

    def _draw_bounding_boxes(self, routing: RoutingResult, show_labels: bool = False):
        """
        Draws the bounding box (HPWL) for each signal
        
        HPWL (Half-Perimeter Wire Length) = (max_x - min_x + 1) + (max_y - min_y + 1)
        """
        nets = getattr(routing, 'routes', getattr(routing, 'nets', []))
        
        for ridx, net in enumerate(nets):
            # ✅ Fetch segments (tree or flat list)
            segments = []
            
            if hasattr(net, 'root') and net.root:
                # Tree structure - uses _extract_all_paths
                paths = self._extract_all_paths(net.root)
                for path in paths:
                    segments.extend(path)
            elif hasattr(net, 'get_all_source_to_sink_paths'):
                # If a direct method exists
                paths = net.get_all_source_to_sink_paths()
                for path in paths:
                    segments.extend(path)
            else:
                # Flat list of segments
                segments = getattr(net, 'segments', [])
            
            if not segments:
                continue
            
            # ✅ Filter valid coordinates
            valid_segments = [s for s in segments 
                            if hasattr(s, 'x') and hasattr(s, 'y') 
                            and s.x >= 0 and s.y >= 0]
            
            if not valid_segments:
                continue
            
            # ✅ Find bounding box coordinates
            min_x = min(s.x for s in valid_segments)
            max_x = max(s.x for s in valid_segments)
            min_y = min(s.y for s in valid_segments)
            max_y = max(s.y for s in valid_segments)
            
            # ✅ Convert to pixel coordinates (shifted by half a CLB block up and right)
            offset_x = self.CLB_SIZE / 2  # Half a CLB block to the right
            offset_y = self.CLB_SIZE / 2  # Half a CLB block up
            
            x1 = min_x * self.TILE_SIZE + offset_x
            x2 = (max_x + 1) * self.TILE_SIZE + offset_x
            y1 = min_y * self.TILE_SIZE + offset_y
            y2 = (max_y + 1) * self.TILE_SIZE + offset_y
            
            # ✅ Signal color
            signal_color = self.ROUTE_COLORS[ridx % len(self.ROUTE_COLORS)]
            
            # ✅ Draws a dashed rectangle
            rect = patches.Rectangle(
                (x1, y1), 
            x2 - x1, 
            y2 - y1,
            linewidth=0,           
            edgecolor='none',        
            facecolor=signal_color,  # Signal color
            alpha=0.15,               
            zorder=3
            )
            self.ax.add_patch(rect)
            
            # ✅ HPWL text (top-left corner) - show only if show_labels=True
            if show_labels:
                hpwl = (max_x - min_x + 1) + (max_y - min_y + 1)
                net_name = getattr(net, 'net_name', getattr(net, 'name', f'net_{ridx}'))
                
                self.ax.text(
                    x1 + 5, y2 - 5,  # Top-left corner + offset
                    f"{net_name}\nHPWL={hpwl}",
                    color=signal_color,  # Signal color for text
                    fontsize=8,
                    weight='bold',
                    bbox=dict(
                        boxstyle='round,pad=0.4',
                        facecolor='white',
                        edgecolor=signal_color,  # Signal color for the edge
                        alpha=0.85
                    ),
                    zorder=12
                )

    def _draw_legend(self, routing: RoutingResult):
        """
        Legend with SOURCE/SINK markers in the signal colors
        """
        legend_elements = []
        
        nets = getattr(routing, 'routes', getattr(routing, 'nets', []))
        
        for i, net in enumerate(nets[:8]):  # First 8 signals
            net_name = getattr(net, 'net_name', getattr(net, 'name', f'net_{i}'))
            color = self.ROUTE_COLORS[i % len(self.ROUTE_COLORS)]
            
            # ✅ SOURCE marker (square) + line
            legend_elements.append(
                Line2D([0], [0], 
                    marker='s',              # Square
                    color=color,             # Line color
                    linewidth=2,
                    markersize=8,
                    markerfacecolor=color,   # Square color
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
        Adds title and subtitle based on the displayed options and filter
        """
        # Determine the main title
        if show_heatmap:
            title = "HEAT MAP"
        elif show_signals and not show_bounding_boxes:
            title = "SIGNAL VIEW"
        elif show_bounding_boxes:
            title = "BOUNDING BOXES"
        else:
            title = "FPGA VISUALIZATION"
        
        # Set the title (upper part of the image)
        self.fig.suptitle(title, fontsize=20, fontweight='bold', y=0.98)
        
        # TOP-LEFT CORNER - File names
        file_info_lines = []
        if architecture_file:
            arch_name = os.path.basename(architecture_file)
            file_info_lines.append(f"Architecture: {arch_name}")
        
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
        
        # BOTTOM OF IMAGE - Filter information
        if filter_type and filter_value is not None:
            if filter_type == "first":
                filter_text = f"Filter: First {filter_value} signals"
            elif filter_type == "last":
                filter_text = f"Filter: Last {filter_value} signals"
            elif filter_type == "less_than":
                filter_text = f"Filter: Signals with fewer than {filter_value} segments"
            elif filter_type == "more_than":
                filter_text = f"Filter: Signals with more than {filter_value} segments"
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