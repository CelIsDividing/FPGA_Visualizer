#!/usr/bin/env python3
"""
Enhanced main.py with signal highlighting capability
Allows highlighting specific signals for better visualization
"""

import os
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash
from werkzeug.utils import secure_filename
import logging

from parsers.architecture_parser import ArchitectureParser
from parsers.routing_parser import RoutingParser
from parsers.circuit_parser import CircuitParser
from visualization.signal_visualizer import SignalVisualizer
from visualization.congestion_visualizer import CongestionVisualizer
from config.settings import settings
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Enhanced SignalVisualizer with highlighting
class HighlightedSignalVisualizer(SignalVisualizer):
    """Visualizer that highlights specific signals with special colors and thickness."""
    
    def __init__(self, target_signals=None):
        super().__init__()
        self.target_signals = target_signals or []  # List of node IDs to highlight
        self.highlight_linewidth = 5.0  # Extra thick for target signals
        
    def _draw_vpr_path(self, path, base_color, show_directions=True, route_label=""):
        """Override to highlight target signals with special colors and thickness."""
        
        # Check if any node in this path is a target signal
        is_target_path = False
        target_node_id = None
        for segment in path:
            node_id = getattr(segment, 'node_id', None)
            if node_id and int(node_id) in self.target_signals:
                is_target_path = True
                target_node_id = node_id
                break
        
        # If this path contains a target signal, use special highlighting
        if is_target_path:
            print(f"🎯 HIGHLIGHTING TARGET PATH containing node {target_node_id}")
            
            # Use bright, distinct colors for target signals
            if int(target_node_id) == 1683:
                highlight_color = '#FF0000'  # Bright Red
            elif int(target_node_id) == 1271:
                highlight_color = '#00FF00'  # Bright Green  
            else:
                highlight_color = '#FFFF00'  # Bright Yellow
                
            # Call parent method with highlight color
            super()._draw_vpr_path(path, highlight_color, show_directions, f"TARGET-{target_node_id}")
        else:
            # Normal drawing for non-target paths
            super()._draw_vpr_path(path, base_color, show_directions, route_label)
            
    def _draw_segment_group(self, seg_group, base_color, show_directions):
        """Override to use thicker lines for highlighted signals."""
        points = seg_group['points']
        seg_type = seg_group['type']
        color = seg_group['color']
        
        if len(points) < 2:
            return
        
        # Check if this is a highlighted signal (red or green color means it's a target)
        is_highlighted = (color == '#FF0000' or color == '#00FF00' or color == '#FFFF00')
        
        # Debljina linije prema tipu
        if seg_type in ['CHANX', 'CHANY']:
            linewidth = self.highlight_linewidth if is_highlighted else 2.5
            alpha = 1.0 if is_highlighted else 0.8
        else:
            linewidth = self.highlight_linewidth * 0.7 if is_highlighted else 1.5
            alpha = 1.0 if is_highlighted else 0.6
        
        # Crtaj linije između svih tačaka
        for i in range(len(points) - 1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            
            # Higher zorder for highlighted signals to draw them on top
            zorder = 10 if is_highlighted else 7
            
            self.ax.plot([x1, x2], [y1, y2], '-', 
                        color=color, linewidth=linewidth, alpha=alpha, zorder=zorder)
            
            # Strelica samo za CHANX/CHANY
            if show_directions and seg_type in ['CHANX', 'CHANY']:
                self._draw_direction_arrow(x1, y1, x2, y2, color, seg_type)


app = Flask(__name__)
app.secret_key = 'fpga_visualizer_secret_key'

# Ensure upload directory exists
os.makedirs('uploads', exist_ok=True)
os.makedirs('output', exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_files():
    try:
        arch_file = request.files.get('architecture_file')
        routing_file = request.files.get('routing_file')
        
        if not arch_file or not routing_file:
            flash('Please upload both architecture and routing files')
            return redirect(url_for('index'))
        
        # Save uploaded files
        arch_filename = secure_filename(arch_file.filename)
        routing_filename = secure_filename(routing_file.filename)
        
        arch_path = os.path.join('uploads', arch_filename)
        routing_path = os.path.join('uploads', routing_filename)
        
        arch_file.save(arch_path)
        routing_file.save(routing_path)
        
        # Store file paths in session
        session['arch_file'] = arch_path
        session['routing_file'] = routing_path
        
        return redirect(url_for('visualize'))
        
    except Exception as e:
        flash(f'Error uploading files: {str(e)}')
        return redirect(url_for('index'))

@app.route('/visualize')
def visualize():
    try:
        arch_path = session.get('arch_file', 'uploads/rrg.xml')
        routing_path = session.get('routing_file', 'test_net10.route')
        
        # Get highlighting parameters from query
        highlight_signals = request.args.get('highlight', '')
        show_heatmap = request.args.get('heatmap', '').lower() == 'true'
        target_signals = []
        if highlight_signals:
            try:
                target_signals = [int(x.strip()) for x in highlight_signals.split(',') if x.strip()]
            except ValueError:
                flash('Invalid signal IDs for highlighting')
        
        # Parse architecture
        arch_parser = ArchitectureParser()
        architecture = arch_parser.parse_xml(arch_path)
        
        # Parse routing  
        routing_parser = RoutingParser()
        routing_result = routing_parser.parse_routing_file(routing_path, architecture)
        
        # Create visualizer (with or without highlighting)
        if show_heatmap:
            visualizer = SignalVisualizer()
            output_filename = "routing_heatmap.png"
            print("🔥 Creating bounding boxes heatmap visualization")
        elif target_signals:
            visualizer = HighlightedSignalVisualizer(target_signals=target_signals)
            output_filename = f"routing_visualization_highlighted_{'-'.join(map(str, target_signals))}.png"
            print(f"🎯 Creating visualization with highlighted signals: {target_signals}")
        else:
            visualizer = SignalVisualizer()
            output_filename = "routing_visualization.png"
        
        output_path = os.path.join('output', output_filename)
        
        # Generate visualization
        plt.figure(figsize=(16, 12))
        
        if show_heatmap:
            # Heatmap mode - samo crni bounding boxovi
            visualizer.visualize_routing(
                architecture=architecture,
                routing=routing_result,
                output_path=output_path,
                show_signal_labels=False,   # Nema labela u heatmap
                show_directions=False,      # Nema strelica u heatmap
                show_bounding_boxes=False,  # Nema obojene bounding boxove
                show_legend=False,          # Nema legend u heatmap
                show_heatmap=True          # Omogući crne bounding boxove
            )
        else:
            # Normalan režim
            visualizer.visualize_routing(
                architecture=architecture,
                routing=routing_result,
                output_path=output_path,
                show_signal_labels=True,
                show_directions=True
            )
        
        # Return image path
        return render_template('web_visualization.html', 
                             image_path=output_filename,
                             highlighted_signals=target_signals)
        
    except Exception as e:
        logging.exception("Error in visualization")
        flash(f'Visualization error: {str(e)}')
        return redirect(url_for('index'))

@app.route('/heatmap')
def generate_heatmap():
    """Generate bounding box heatmap visualization"""
    print("🔥 /heatmap route called")
    try:
        arch_path = session.get('arch_file', 'uploads/rrg.xml')
        routing_path = session.get('routing_file', 'test_net10.route')
        
        # Parse architecture
        arch_parser = ArchitectureParser()
        architecture = arch_parser.parse_xml(arch_path)
        
        # Parse routing  
        routing_parser = RoutingParser()
        routing_result = routing_parser.parse_routing_file(routing_path, architecture)
        
        # Create visualizer for heatmap
        visualizer = SignalVisualizer()
        output_filename = "routing_heatmap.png"
        print("🔥 Creating bounding boxes heatmap visualization")
        
        output_path = os.path.join('output', output_filename)
        
        # Generate heatmap visualization
        plt.figure(figsize=(16, 12))
        
        visualizer.visualize_routing(
            architecture=architecture,
            routing=routing_result,
            output_path=output_path,
            show_signal_labels=False,   # Nema labela u heatmap
            show_directions=False,      # Nema strelica u heatmap
            show_bounding_boxes=False,  # Nema obojene bounding boxove
            show_legend=False,          # Nema legend u heatmap
            show_heatmap=True          # Omogući crne bounding boxove
        )
        
        # Return image path
        return render_template('web_visualization.html', 
                             image_path=output_filename,
                             highlighted_signals=[])
        
    except Exception as e:
        logging.exception("Error in heatmap generation")
        flash(f'Heatmap error: {str(e)}')
        return redirect(url_for('index'))

@app.route('/highlight')
def highlight_form():
    """Show form for highlighting specific signals"""
    return render_template('highlight_form.html')

if __name__ == '__main__':
    print("🚀 Starting FPGA Visualizer with signal highlighting support...")
    print("💡 Usage examples:")
    print("   - Normal visualization: http://localhost:5000/visualize")
    print("   - Highlight signal 1683: http://localhost:5000/visualize?highlight=1683")
    print("   - Highlight signals 1683,1271: http://localhost:5000/visualize?highlight=1683,1271")
    print("   - Interactive highlighting: http://localhost:5000/highlight")
    print("   - Heatmap visualization: http://localhost:5000/heatmap")
    
    # Debug: prikaži sve registrovane rute
    print("\n📋 Registered routes:")
    for rule in app.url_map.iter_rules():
        print(f"   {rule.endpoint}: {rule.rule}")
    print()
    
    app.run(debug=True)