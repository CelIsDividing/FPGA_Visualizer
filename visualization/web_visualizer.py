import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import numpy as np
from typing import Dict, List, Optional
import json

from models.fpga_architecture import FPGAArchitecture, Point
from models.circuit import Circuit, Signal
from models.routing import RoutingResult
from config.settings import settings

class WebVisualizer:
    """Klasa za interaktivnu web vizuelizaciju koristeći Plotly"""
    
    def __init__(self):
        self.colors = px.colors.qualitative.Set3
    
    def create_interactive_fpga_visualization(self, 
                                            architecture: FPGAArchitecture,
                                            circuit: Circuit,
                                            routing_result: Optional[RoutingResult] = None) -> go.Figure:
        """
        Kreira interaktivnu vizuelizaciju FPGA sa Plotly
        """
        fig = make_subplots(rows=1, cols=1)
        
        # Dodaj FPGA grid
        self._add_fpga_grid(fig, architecture)
        
        # Dodaj logic blocks
        self._add_logic_blocks(fig, architecture)
        
        # Dodaj signale ako postoje
        if circuit and circuit.signals:
            self._add_signals(fig, circuit, architecture)
        
        # Dodaj zagušenje ako postoje podaci
        if routing_result and routing_result.congestion_map:
            self._add_congestion_heatmap(fig, architecture, routing_result)
        
        # Podešavanje layouta
        self._setup_interactive_layout(fig, architecture)
        
        return fig
    
    def _add_fpga_grid(self, fig: go.Figure, architecture: FPGAArchitecture):
        """Dodaje FPGA grid na plot"""
        cell_size = settings.CELL_SIZE
        
        # Horizontalne linije
        for y in range(architecture.height + 1):
            fig.add_trace(go.Scatter(
                x=[0, architecture.width * cell_size],
                y=[y * cell_size, y * cell_size],
                mode='lines',
                line=dict(color='gray', width=1, dash='dot'),
                showlegend=False,
                hoverinfo='skip'
            ))
        
        # Vertikalne linije
        for x in range(architecture.width + 1):
            fig.add_trace(go.Scatter(
                x=[x * cell_size, x * cell_size],
                y=[0, architecture.height * cell_size],
                mode='lines',
                line=dict(color='gray', width=1, dash='dot'),
                showlegend=False,
                hoverinfo='skip'
            ))
    
    def _add_logic_blocks(self, fig: go.Figure, architecture: FPGAArchitecture):
        """Dodaje logic blocks na plot"""
        cell_size = settings.CELL_SIZE
        
        for block in architecture.logic_blocks:
            x = block.x * cell_size + cell_size / 2
            y = block.y * cell_size + cell_size / 2
            
            # Različite boje za različite tipove blokova
            if block.type == 'CLB':
                color = 'lightblue'
                symbol = 'square'
            elif block.type == 'BRAM':
                color = 'lightgreen'
                symbol = 'circle'
            elif block.type == 'DSP':
                color = 'lightyellow'
                symbol = 'diamond'
            elif block.type == 'IOB':
                color = 'lightcoral'
                symbol = 'triangle-up'
            else:
                color = 'lightgray'
                symbol = 'square'
            
            fig.add_trace(go.Scatter(
                x=[x],
                y=[y],
                mode='markers+text',
                marker=dict(
                    size=cell_size - 10,
                    color=color,
                    line=dict(width=2, color='darkblue')
                ),
                text=[block.name[:4] if block.name else block.type],
                textposition="middle center",
                name=f"{block.type} ({block.x},{block.y})",
                hoverinfo='text',
                hovertext=(
                    f"Tip: {block.type}<br>"
                    f"Pozicija: ({block.x}, {block.y})<br>"
                    f"Ulazi: {block.inputs}<br>"
                    f"Izlazi: {block.outputs}<br>"
                    f"Ime: {block.name}"
                )
            ))
    
    def _add_signals(self, fig: go.Figure, circuit: Circuit, architecture: FPGAArchitecture):
        """Dodaje signale na plot"""
        cell_size = settings.CELL_SIZE
        active_signals = circuit.get_active_signals()
        
        for i, signal in enumerate(active_signals[:10]):  # Ograniči na prvih 10 signala
            color = self.colors[i % len(self.colors)]
            
            if signal.route and len(signal.route) > 1:
                # Prikaz rute signala
                x_vals = [p.x * cell_size + cell_size / 2 for p in signal.route]
                y_vals = [p.y * cell_size + cell_size / 2 for p in signal.route]
                
                fig.add_trace(go.Scatter(
                    x=x_vals,
                    y=y_vals,
                    mode='lines+markers',
                    line=dict(color=color, width=3),
                    marker=dict(size=6),
                    name=f"Signal: {signal.name}",
                    hoverinfo='text',
                    hovertext=(
                        f"Signal: {signal.name}<br>"
                        f"Dužina: {signal.length:.2f}<br>"
                        f"Tačaka: {len(signal.route)}"
                    ),
                    showlegend=True
                ))
            
            # Tačke za source i destination
            if signal.source:
                fig.add_trace(go.Scatter(
                    x=[signal.source.x * cell_size + cell_size / 2],
                    y=[signal.source.y * cell_size + cell_size / 2],
                    mode='markers',
                    marker=dict(size=12, color='green', symbol='star'),
                    name=f"Source: {signal.name}",
                    hoverinfo='text',
                    hovertext=f"Source: {signal.name}",
                    showlegend=False
                ))
            
            if signal.destination:
                fig.add_trace(go.Scatter(
                    x=[signal.destination.x * cell_size + cell_size / 2],
                    y=[signal.destination.y * cell_size + cell_size / 2],
                    mode='markers',
                    marker=dict(size=12, color='red', symbol='x'),
                    name=f"Destination: {signal.name}",
                    hoverinfo='text',
                    hovertext=f"Destination: {signal.name}",
                    showlegend=False
                ))
    
    def _add_congestion_heatmap(self, fig: go.Figure, architecture: FPGAArchitecture,
                              routing_result: RoutingResult):
        """Dodaje heat map zagušenja"""
        if not routing_result.congestion_map:
            return
        
        # Pripremi podatke za heat map
        congestion_grid = np.zeros((architecture.height, architecture.width))
        
        for segment_key, congestion in routing_result.congestion_map.items():
            try:
                if ',' in segment_key:
                    x, y = map(int, segment_key.split(','))
                    if 0 <= x < architecture.width and 0 <= y < architecture.height:
                        congestion_grid[y, x] = congestion
            except (ValueError, IndexError):
                continue
        
        # Kreiraj heat map
        fig.add_trace(go.Heatmap(
            z=congestion_grid,
            colorscale='Reds',
            opacity=0.6,
            hoverinfo='z',
            name='Zagušenje',
            colorbar=dict(title='Nivo zagušenja')
        ))
    
    def _setup_interactive_layout(self, fig: go.Figure, architecture: FPGAArchitecture):
        """Podešava interaktivni layout"""
        cell_size = settings.CELL_SIZE
        
        fig.update_layout(
            title=dict(
                text='Interaktivna FPGA Vizuelizacija',
                x=0.5,
                xanchor='center'
            ),
            xaxis=dict(
                title='X Koordinata',
                range=[0, architecture.width * cell_size],
                scaleanchor="y",
                constrain='domain'
            ),
            yaxis=dict(
                title='Y Koordinata', 
                range=[0, architecture.height * cell_size],
                constrain='domain'
            ),
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            ),
            hovermode='closest',
            width=800,
            height=600,
            template='plotly_white'
        )
    
    def create_congestion_chart(self, routing_result: RoutingResult) -> go.Figure:
        """Kreira bar chart distribucije zagušenja"""
        if not routing_result.congestion_map:
            return self._create_empty_chart("Nema podataka o zagušenju")
        
        congestion_values = list(routing_result.congestion_map.values())
        
        # Grupiši vrednosti zagušenja
        bins = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
        labels = ['0.0-0.2', '0.2-0.4', '0.4-0.6', '0.6-0.8', '0.8-1.0']
        
        counts = []
        for i in range(len(bins) - 1):
            count = len([v for v in congestion_values if bins[i] <= v < bins[i+1]])
            counts.append(count)
        
        fig = go.Figure(data=[
            go.Bar(
                x=labels,
                y=counts,
                marker_color=['green', 'lightgreen', 'yellow', 'orange', 'red'],
                text=counts,
                textposition='auto',
            )
        ])
        
        fig.update_layout(
            title='Distribucija zagušenja po segmentima',
            xaxis_title='Nivo zagušenja',
            yaxis_title='Broj segmenata',
            template='plotly_white'
        )
        
        return fig
    
    def create_signal_length_chart(self, circuit: Circuit) -> go.Figure:
        """Kreira histogram dužina signala"""
        if not circuit or not circuit.signals:
            return self._create_empty_chart("Nema podataka o signalima")
        
        signal_lengths = [signal.calculate_length() for signal in circuit.get_active_signals()]
        
        fig = go.Figure(data=[
            go.Histogram(
                x=signal_lengths,
                nbinsx=20,
                marker_color='lightblue',
                opacity=0.7
            )
        ])
        
        fig.update_layout(
            title='Distribucija dužina signala',
            xaxis_title='Dužina signala',
            yaxis_title='Broj signala',
            template='plotly_white'
        )
        
        return fig
    
    def create_conflict_graph_plotly(self, conflict_data: Dict) -> go.Figure:
        """Kreira interaktivni prikaz konflikt grafa"""
        import networkx as nx
        
        if 'graph' not in conflict_data or not conflict_data['graph'].nodes():
            return self._create_empty_chart("Nema podataka o konfliktima")
        
        G = conflict_data['graph']
        pos = nx.spring_layout(G, seed=42)
        
        # Pripremi podatke za čvorove
        node_x = []
        node_y = []
        node_text = []
        node_size = []
        node_color = []
        
        hubs = set(conflict_data.get('hubs', []))
        
        for node in G.nodes():
            x, y = pos[node]
            node_x.append(x)
            node_y.append(y)
            node_text.append(f"Signal: {node}<br>Stepen: {G.degree(node)}")
            
            # Veći čvorovi za habove
            if node in hubs:
                node_size.append(20)
                node_color.append('red')
            else:
                node_size.append(10)
                node_color.append('lightblue')
        
        # Pripremi podatke za grane
        edge_x = []
        edge_y = []
        
        for edge in G.edges():
            x0, y0 = pos[edge[0]]
            x1, y1 = pos[edge[1]]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])
        
        # Kreiraj plot
        fig = go.Figure()
        
        # Dodaj grane
        fig.add_trace(go.Scatter(
            x=edge_x, y=edge_y,
            line=dict(width=1, color='gray'),
            hoverinfo='none',
            mode='lines',
            showlegend=False
        ))
        
        # Dodaj čvorove
        fig.add_trace(go.Scatter(
            x=node_x, y=node_y,
            mode='markers+text',
            marker=dict(
                size=node_size,
                color=node_color,
                line=dict(width=2, color='darkblue')
            ),
            text=[node.split('_')[-1] for node in G.nodes()],  # Skraćena imena
            textposition="middle center",
            hovertext=node_text,
            hoverinfo='text',
            showlegend=False
        ))
        
        fig.update_layout(
            title='Interaktivni Konflikt Graf',
            showlegend=False,
            hovermode='closest',
            margin=dict(b=20, l=5, r=5, t=40),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            width=600,
            height=400,
            template='plotly_white'
        )
        
        return fig
    
    def _create_empty_chart(self, message: str) -> go.Figure:
        """Kreira prazan chart sa porukom"""
        fig = go.Figure()
        fig.update_layout(
            title=message,
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            annotations=[dict(
                text=message,
                xref="paper", yref="paper",
                showarrow=False,
                font=dict(size=16)
            )]
        )
        return fig
    
    def export_to_html(self, fig: go.Figure, filename: str):
        """Izvozi Plotly fig u HTML fajl"""
        fig.write_html(filename, include_plotlyjs='cdn')
    
    def get_plotly_json(self, fig: go.Figure) -> str:
        """Vraća Plotly fig kao JSON string"""
        return fig.to_json()