import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
from matplotlib.figure import Figure
from typing import Dict, List, Optional, Tuple
import matplotlib.patches as patches

from models.fpga_architecture import FPGAArchitecture, RoutingChannel, Point
from models.routing import RoutingResult
from config.settings import settings

class CongestionVisualizer:
    """Klasa za vizuelizaciju zagušenja na FPGA čipu"""
    
    def __init__(self):
        self.fig = None
        self.ax = None
        self.cmap = plt.cm.Reds  # Color map za zagušenje
    
    def visualize_congestion(self, 
                           architecture: FPGAArchitecture,
                           routing_result: RoutingResult,
                           visualization_type: str = "current",
                           iteration: int = -1) -> Figure:
        """
        Vizuelizuje zagušenje na FPGA čipu
        
        Args:
            architecture: FPGA arhitektura
            routing_result: Rezultati rutiranja
            visualization_type: Tip vizuelizacije 
                              ("current", "historical", "segment_max", "segment_utilization")
            iteration: Iteracija za prikaz (ako je -1, poslednja iteracija)
        """
        self.fig, self.ax = plt.subplots(figsize=(14, 12))
        
        # Podešavanje pozadine
        self.ax.set_facecolor('white')
        self.fig.patch.set_facecolor('white')
        
        # Crtanje osnovne FPGA mreže
        self._draw_fpga_grid(architecture)
        
        # Vizuelizacija zagušenja prema tipu
        if visualization_type == "current":
            self._visualize_current_congestion(architecture, routing_result)
        elif visualization_type == "historical":
            self._visualize_historical_congestion(architecture, routing_result, iteration)
        elif visualization_type == "segment_max":
            self._visualize_segment_max_congestion(architecture, routing_result)
        elif visualization_type == "segment_utilization":
            self._visualize_segment_utilization(architecture, routing_result)
        
        self._setup_congestion_plot(architecture, visualization_type)
        return self.fig
    
    def _draw_fpga_grid(self, architecture: FPGAArchitecture):
        """Crtanje osnovne FPGA mreže"""
        cell_size = settings.CELL_SIZE
        offset_x = settings.CANVAS_PADDING
        offset_y = settings.CANVAS_PADDING
        
        # Crtanje horizontalnih linija
        for y in range(architecture.height + 1):
            self.ax.plot(
                [offset_x, offset_x + architecture.width * cell_size],
                [offset_y + y * cell_size, offset_y + y * cell_size],
                'gray', linewidth=0.5, alpha=0.3
            )
        
        # Crtanje vertikalnih linija
        for x in range(architecture.width + 1):
            self.ax.plot(
                [offset_x + x * cell_size, offset_x + x * cell_size],
                [offset_y, offset_y + architecture.height * cell_size],
                'gray', linewidth=0.5, alpha=0.3
            )
        
        # Crtanje logic blocks
        for block in architecture.logic_blocks:
            x = offset_x + block.x * cell_size + 2
            y = offset_y + block.y * cell_size + 2
            width = cell_size - 4
            height = cell_size - 4
            
            # Različite boje za različite tipove blokova
            if block.type == 'CLB':
                color = 'lightblue'
            elif block.type == 'BRAM':
                color = 'lightgreen'
            elif block.type == 'DSP':
                color = 'lightyellow'
            elif block.type == 'IOB':
                color = 'lightcoral'
            else:
                color = 'lightgray'
            
            rect = patches.Rectangle(
                (x, y), width, height,
                linewidth=1, edgecolor='blue',
                facecolor=color, alpha=0.7
            )
            self.ax.add_patch(rect)
    
    def _visualize_current_congestion(self, architecture: FPGAArchitecture, 
                                    routing_result: RoutingResult):
        """Vizuelizacija trenutnog zagušenja"""
        if not routing_result.congestion_map:
            print("⚠️ Nema podataka o zagušenju")
            return
        
        cell_size = settings.CELL_SIZE
        offset_x = settings.CANVAS_PADDING
        offset_y = settings.CANVAS_PADDING
        
        # Pripremi podatke za heat map
        congestion_grid = np.zeros((architecture.height, architecture.width))
        
        # Popuni grid sa vrednostima zagušenja
        for segment_key, congestion in routing_result.congestion_map.items():
            try:
                # Parsiranje segment key (format: "x,y" ili slično)
                if ',' in segment_key:
                    x, y = map(int, segment_key.split(','))
                    if 0 <= x < architecture.width and 0 <= y < architecture.height:
                        congestion_grid[y, x] = congestion
            except (ValueError, IndexError):
                continue
        
        # Prikaz heat map
        im = self.ax.imshow(congestion_grid, cmap=self.cmap, alpha=0.7,
                           extent=[offset_x, offset_x + architecture.width * cell_size,
                                  offset_y, offset_y + architecture.height * cell_size],
                           origin='lower', vmin=0, vmax=1)
        
        # Dodaj colorbar
        cbar = self.fig.colorbar(im, ax=self.ax, shrink=0.8)
        cbar.set_label('Nivo zagušenja', rotation=270, labelpad=15)
        
        # Anotacije za visoko zagušenje
        self._add_congestion_annotations(congestion_grid, architecture)
    
    def _visualize_historical_congestion(self, architecture: FPGAArchitecture,
                                       routing_result: RoutingResult, iteration: int):
        """Vizuelizacija istorijskog zagušenja kroz iteracije"""
        # Ovo bi zahtevalo čuvanje istorije zagušenja po iteracijama
        # Za sada koristimo trenutno zagušenje
        self._visualize_current_congestion(architecture, routing_result)
        
        # Dodaj informaciju o iteraciji
        self.ax.text(0.02, 0.98, f'Iteracija: {iteration}', 
                    transform=self.ax.transAxes, fontsize=12,
                    bbox=dict(boxstyle="round", facecolor='wheat', alpha=0.8))
    
    def _visualize_segment_max_congestion(self, architecture: FPGAArchitecture,
                                        routing_result: RoutingResult):
        """Vizuelizacija maksimalnog zagušenja po segmentima"""
        if not routing_result.congestion_map:
            return
        
        cell_size = settings.CELL_SIZE
        offset_x = settings.CANVAS_PADDING
        offset_y = settings.CANVAS_PADDING
        
        # Grupiši zagušenje po segmentima i pronađi maksimum
        segment_congestion = {}
        for segment_key, congestion in routing_result.congestion_map.items():
            segment_id = segment_key.split('_')[0] if '_' in segment_key else segment_key
            if segment_id not in segment_congestion:
                segment_congestion[segment_id] = congestion
            else:
                segment_congestion[segment_id] = max(segment_congestion[segment_id], congestion)
        
        # Vizuelizacija maksimalnog zagušenja
        for channel in architecture.routing_channels:
            segment_id = str(channel.segment_id)
            if segment_id in segment_congestion:
                congestion = segment_congestion[segment_id]
                self._draw_congested_segment(channel, congestion, architecture)
    
    def _visualize_segment_utilization(self, architecture: FPGAArchitecture,
                                     routing_result: RoutingResult):
        """Vizuelizacija iskorišćenja čitavog segmenta"""
        # Ovo bi zahtevalo dodatne podatke o kapacitetu segmenta
        # Za sada koristimo trenutno zagušenje kao proxy za utilization
        self._visualize_current_congestion(architecture, routing_result)
        
        # Dodaj labelu da je ovo utilization vizuelizacija
        self.ax.text(0.02, 0.02, 'Prikaz: Iskorišćenje segmenta', 
                    transform=self.ax.transAxes, fontsize=10,
                    bbox=dict(boxstyle="round", facecolor='lightblue', alpha=0.8))
    
    def _draw_congested_segment(self, channel: RoutingChannel, congestion: float,
                              architecture: FPGAArchitecture):
        """Crtanje zagušenog segmenta"""
        cell_size = settings.CELL_SIZE
        offset_x = settings.CANVAS_PADDING
        offset_y = settings.CANVAS_PADDING
        
        # Odredi boju na osnovu nivoa zagušenja
        color = self.cmap(congestion)
        
        # Pojednostavljena vizuelizacija - u praksi bi ovo zavisilo od tačne pozicije segmenta
        x = offset_x + (channel.segment_id % architecture.width) * cell_size
        y = offset_y + (channel.segment_id // architecture.width) * cell_size
        
        if channel.direction == 'horizontal':
            # Horizontalni segment
            rect = patches.Rectangle(
                (x, y + cell_size/2 - 2), cell_size, 4,
                linewidth=0, facecolor=color, alpha=0.8
            )
        else:
            # Vertikalni segment
            rect = patches.Rectangle(
                (x + cell_size/2 - 2, y), 4, cell_size,
                linewidth=0, facecolor=color, alpha=0.8
            )
        
        self.ax.add_patch(rect)
    
    def _add_congestion_annotations(self, congestion_grid: np.ndarray,
                                  architecture: FPGAArchitecture):
        """Dodaje anotacije za oblasti sa visokim zagušenjem"""
        cell_size = settings.CELL_SIZE
        offset_x = settings.CANVAS_PADDING
        offset_y = settings.CANVAS_PADDING
        
        high_congestion_threshold = 0.8
        
        for y in range(architecture.height):
            for x in range(architecture.width):
                if congestion_grid[y, x] > high_congestion_threshold:
                    # Oznaci oblast sa visokim zagušenjem
                    rect_x = offset_x + x * cell_size
                    rect_y = offset_y + y * cell_size
                    
                    rect = patches.Rectangle(
                        (rect_x, rect_y), cell_size, cell_size,
                        linewidth=2, edgecolor='red', facecolor='none',
                        alpha=0.8
                    )
                    self.ax.add_patch(rect)
                    
                    # Dodaj tekst sa vrednošću zagušenja
                    self.ax.text(rect_x + cell_size/2, rect_y + cell_size/2,
                               f'{congestion_grid[y, x]:.2f}',
                               ha='center', va='center', fontsize=8,
                               bbox=dict(boxstyle="round", facecolor='white', alpha=0.8))
    
    def _setup_congestion_plot(self, architecture: FPGAArchitecture, vis_type: str):
        """Podešavanje izgleda grafikona za zagušenje"""
        cell_size = settings.CELL_SIZE
        offset_x = settings.CANVAS_PADDING
        offset_y = settings.CANVAS_PADDING
        
        self.ax.set_xlim(0, offset_x * 2 + architecture.width * cell_size)
        self.ax.set_ylim(0, offset_y * 2 + architecture.height * cell_size)
        self.ax.set_aspect('equal')
        
        # Naslov zavisi od tipa vizuelizacije
        titles = {
            "current": "Trenutno zagušenje",
            "historical": "Istorijsko zagušenje",
            "segment_max": "Maksimalno zagušenje po segmentima", 
            "segment_utilization": "Iskorišćenje segmenta"
        }
        
        title = titles.get(vis_type, "Vizuelizacija zagušenja")
        self.ax.set_title(f'FPGA {title}', fontsize=14, pad=20)
        self.ax.set_xlabel('X Koordinata')
        self.ax.set_ylabel('Y Koordinata')
        
        # Legenda za tipove blokova
        self._add_legend()
    
    def _add_legend(self):
        """Dodaje legendu za tipove blokova"""
        from matplotlib.patches import Patch
        
        legend_elements = [
            Patch(facecolor='lightblue', edgecolor='blue', label='CLB'),
            Patch(facecolor='lightgreen', edgecolor='green', label='BRAM'),
            Patch(facecolor='lightyellow', edgecolor='orange', label='DSP'),
            Patch(facecolor='lightcoral', edgecolor='red', label='IOB'),
        ]
        
        self.ax.legend(handles=legend_elements, loc='upper right',
                      bbox_to_anchor=(1, 1))
    
    def generate_congestion_report(self, architecture: FPGAArchitecture,
                                 routing_result: RoutingResult) -> Dict:
        """Generiše izveštaj o zagušenju"""
        if not routing_result.congestion_map:
            return {"error": "Nema podataka o zagušenju"}
        
        congestion_values = list(routing_result.congestion_map.values())
        
        report = {
            "max_congestion": max(congestion_values) if congestion_values else 0,
            "avg_congestion": sum(congestion_values) / len(congestion_values) if congestion_values else 0,
            "high_congestion_segments": len([v for v in congestion_values if v > 0.8]),
            "total_segments": len(congestion_values),
            "congestion_distribution": {
                "0.0-0.2": len([v for v in congestion_values if 0.0 <= v < 0.2]),
                "0.2-0.4": len([v for v in congestion_values if 0.2 <= v < 0.4]),
                "0.4-0.6": len([v for v in congestion_values if 0.4 <= v < 0.6]),
                "0.6-0.8": len([v for v in congestion_values if 0.6 <= v < 0.8]),
                "0.8-1.0": len([v for v in congestion_values if 0.8 <= v <= 1.0]),
            }
        }
        
        return report
    
    def save_visualization(self, filename: str, dpi: int = 300):
        """Čuva vizuelizaciju u fajl"""
        if self.fig:
            self.fig.savefig(filename, dpi=dpi, bbox_inches='tight', 
                           facecolor='white', edgecolor='none')