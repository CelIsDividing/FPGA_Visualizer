#!/usr/bin/env python3
"""
FPGA Visualization Tool - Main application
Information Systems Development Process 2025
"""

import os
import sys
import re
import json
import time
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from flask_cors import CORS
from typing import Dict, List, Optional
from flask import Flask, render_template, request, jsonify, send_file

# Adding path for module import
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config.settings import settings
from models.fpga_architecture import FPGAArchitecture
from models.circuit import Circuit
from models.routing import RoutingResult
from parsers.architecture_parser import ArchitectureParser
from parsers.circuit_parser import CircuitParser
from parsers.routing_parser import RoutingParser
from visualization.signal_visualizer import SignalVisualizer
from analysis.conflict_graph import ConflictGraphBuilder

# Global variables for cached data
cached_routing = None
cached_architecture = None
cached_architecture_filename = None
cached_routing_filename = None

class FPGAVisualizationApp:
    """Main class of the FPGA visualization tool"""
    
    def __init__(self):
        self.app = Flask(__name__)
        self.app.config['UPLOAD_FOLDER'] = settings.UPLOAD_FOLDER
        
        CORS(self.app)

        # Component initialization
        self.architecture_parser = ArchitectureParser()
        self.circuit_parser = CircuitParser()
        self.routing_parser = RoutingParser()
        self.signal_visualizer = SignalVisualizer()
        self.conflict_builder = ConflictGraphBuilder()
        
        # Application data
        self.current_architecture: Optional[FPGAArchitecture] = None
        self.current_circuit: Optional[Circuit] = None
        self.current_routing: Optional[RoutingResult] = None
        
        # Names of loaded files
        self.architecture_filename: Optional[str] = None
        self.routing_filename: Optional[str] = None
        
        self._setup_routes()
    
    def _setup_routes(self):
        """Sets up Flask routes"""
        
        @self.app.route('/')
        def index():
            return render_template('index.html')
        
        @self.app.route('/upload/architecture', methods=['POST'])
        def upload_architecture():
            """Route for uploading FPGA architecture"""
            if 'file' not in request.files:
                return jsonify({'error': 'No file uploaded'}), 400

            file = request.files['file']
            if file.filename == '':
                return jsonify({'error': 'No file selected'}), 400

            filename = file.filename
            if not filename.lower().endswith('.xml'):
                return jsonify({'error': 'Unsupported file type; expected .xml'}), 400

            os.makedirs(self.app.config.get('UPLOAD_FOLDER', settings.UPLOAD_FOLDER), exist_ok=True)
            filepath = os.path.join(self.app.config.get('UPLOAD_FOLDER', settings.UPLOAD_FOLDER), filename)
            file.save(filepath)

            try:
                    # Attempt to call common parser methods (parse / parse_xml / parse_architecture_file)
                    parser = self.architecture_parser
                    arch = None
                    if hasattr(parser, 'parse'):
                        arch = parser.parse(filepath)
                    elif hasattr(parser, 'parse_xml'):
                        arch = parser.parse_xml(filepath)
                    elif hasattr(parser, 'parse_architecture_file'):
                        arch = parser.parse_architecture_file(filepath)
                    else:
                        raise RuntimeError('ArchitectureParser has no supported method for parsing')

                    # The parser is expected to return an FPGAArchitecture instance
                    self.current_architecture = arch
                    self.architecture_filename = filename  # Save the file name
                    
                    # Update global caches for visualization
                    global cached_architecture, cached_architecture_filename
                    cached_architecture = arch
                    cached_architecture_filename = filename

                    # If the object has to_dict, return it to the client for display
                    arch_dict = {}
                    if arch is not None and hasattr(arch, 'to_dict'):
                        arch_dict = arch.to_dict()

                    return jsonify({'success': True, 'architecture': arch_dict})
            except Exception as e:
                import traceback
                traceback.print_exc()  # print stack trace in server console
                # If we are in debug mode, also return the trace in JSON for easier diagnostics
                if getattr(settings, 'DEBUG', False):
                    return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 400
                return jsonify({'error': str(e)}), 400
        
        @self.app.route('/upload/routing', methods=['POST'])
        def upload_routing():
            """Route for uploading routing results (.route)"""
            print("=" * 50)
            print("📥 UPLOAD REQUEST RECEIVED FOR ROUTING")
            
            if 'file' not in request.files:
                print("❌ NO FILE IN THE REQUEST")
                return jsonify({'error': 'No file uploaded'}), 400

            file = request.files['file']
            print(f"📄 FILE: {file.filename}")
            print(f"📊 SIZE: {len(file.read()) if file else 0} bytes")
            file.seek(0)  # Reset file pointer
            
            if file.filename == '':
                print("❌ EMPTY FILE NAME")
                return jsonify({'error': 'No file selected'}), 400
                
            if not file.filename.endswith('.route'):
                print("❌ WRONG EXTENSION")
                return jsonify({'error': 'Invalid file type - must be .route'}), 400

            try:
                # Save uploaded file
                os.makedirs(settings.UPLOAD_FOLDER, exist_ok=True)
                filepath = os.path.join(settings.UPLOAD_FOLDER, file.filename)
                file.save(filepath)
                print(f"💾 FILE SAVED: {filepath}")

                # Require architecture to be loaded first
                if not self.current_architecture:
                    print("❌ ARCHITECTURE NOT LOADED")
                    return jsonify({'error': 'Upload architecture (.xml) before routing file'}), 400

                print("🔍 STARTING PARSING OF ROUTING FILE...")
                # Parse routing file
                self.current_routing = self.routing_parser.parse_routing_file(
                    filepath,
                    self.current_architecture,
                    self.current_circuit  # Optional
                )
                self.routing_filename = file.filename  # Save the file name
                print("✅ ROUTING PARSED SUCCESSFULLY")

                routing_dict = self.current_routing.to_dict() if self.current_routing else {}
                print(f"📊 ROUTE COUNT: {len(routing_dict.get('routes', []))}")

                return jsonify({
                    'success': True,
                    'routing': routing_dict
                })

            except Exception as e:
                print(f"💥 ERROR DURING PARSING: {str(e)}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': str(e)}), 400
        
        @self.app.route('/api/parse_routing', methods=['POST'])
        def parse_routing():
            """Parse .route file and return a list of signals"""
            global cached_routing, cached_architecture, cached_routing_filename, cached_architecture_filename
            
            try:
                if 'routing_file' not in request.files:
                    return jsonify({'success': False, 'error': 'No file'}), 400
                
                file = request.files['routing_file']
                if file.filename == '':
                    return jsonify({'success': False, 'error': 'Empty file'}), 400
                
                import tempfile
                
                with tempfile.NamedTemporaryFile(delete=False, suffix='.route') as tmp:
                    file.save(tmp.name)
                    tmp_path = tmp.name
                
                try:
                    width, height = 4, 4  # Default
            
                    with open(tmp_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            # Search for: "Array size: 10 x 10 logic blocks"
                            match = re.search(r'Array\s+size:\s+(\d+)\s+x\s+(\d+)', line, re.IGNORECASE)
                            if match:
                                width = int(match.group(1))
                                height = int(match.group(2))
                                print(f"✅ Dimensions read from .route: {width}×{height}")
                                break
                    
                    parser = RoutingParser()
                    
                    # CREATE ARCHITECTURE WITH ACTUAL DIMENSIONS
                    # If the architecture does not exist or the dimensions do not match
                    if cached_architecture is None or \
                    cached_architecture.width != width or \
                    cached_architecture.height != height:
                        from models.fpga_architecture import FPGAArchitecture
                        cached_architecture = FPGAArchitecture(width=width, height=height)
                        # Only set the auto-generated name if there was no manually loaded architecture
                        if cached_architecture_filename is None or cached_architecture_filename.startswith("Auto-generated"):
                            cached_architecture_filename = f"Auto-generated {width}x{height}"
                        print(f"🏗️ Architecture created: {width}×{height}")
                    
                    routing_result = parser.parse_routing_file(
                        tmp_path, 
                        architecture=cached_architecture,
                        circuit=None
                    )
                    
                    # CACHING
                    cached_routing = routing_result
                    cached_routing_filename = file.filename
                    
                    # Extract signals
                    signals = []
                    for route in routing_result.routes:
                        signals.append({
                            'net_name': route.net_name,
                            'segment_count': len(route.segments),
                            'fanout': len(route.get_all_source_to_sink_paths()) if route.root else 1
                        })
                    
                    return jsonify({
                        'success': True,
                        'signals': signals,
                        'total_nets': len(signals),
                        'architecture': {
                            'width': width,
                            'height': height
                        }
                    })
                    
                finally:
                    os.unlink(tmp_path)
            
            except Exception as e:
                import traceback
                traceback.print_exc()
                return jsonify({'success': False, 'error': str(e)}), 500
            
        @self.app.route('/upload/circuit', methods=['POST'])
        def upload_circuit():
            """Route for uploading a circuit"""
            print("=" * 50)
            print("📥 UPLOAD REQUEST RECEIVED FOR CIRCUIT")
            
            if 'file' not in request.files:
                print("❌ NO FILE IN THE REQUEST")
                return jsonify({'error': 'No file uploaded'}), 400
            
            file = request.files['file']
            print(f"📄 FILE: {file.filename}")
            print(f"📊 SIZE: {len(file.read()) if file else 0} bytes")
            
            # Return to the beginning of the file
            file.seek(0)
            
            if file.filename == '':
                print("❌ EMPTY FILE NAME")
                return jsonify({'error': 'No file selected'}), 400
            
            # Create the uploads folder if it does not exist
            os.makedirs(settings.UPLOAD_FOLDER, exist_ok=True)
            filepath = os.path.join(settings.UPLOAD_FOLDER, file.filename)
            
            try:
                file.save(filepath)
                print(f"💾 FILE SAVED: {filepath}")
                
                if file.filename.endswith('.v'):
                    print("🔧 PARSING VERILOG...")
                    self.current_circuit = self.circuit_parser.parse_verilog(filepath)
                elif file.filename.endswith('.blif'):
                    print("🔧 PARSING BLIF...")
                    self.current_circuit = self.circuit_parser.parse_blif(filepath)
                else:
                    print("❌ UNSUPPORTED FORMAT")
                    return jsonify({'error': 'Unsupported file format. Use .v or .blif'}), 400
                
                print(f"✅ CIRCUIT PARSED: {self.current_circuit.name}")
                print(f"📈 SIGNALS: {len(self.current_circuit.signals)}")
                print(f"🔧 COMPONENTS: {len(self.current_circuit.components)}")
                
                return jsonify({
                    'success': True,
                    'circuit': self.current_circuit.to_dict()
                })
                
            except Exception as e:
                print(f"💥 ERROR DURING PARSING: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': str(e)}), 400
        
        @self.app.route('/api/visualize', methods=['POST'])
        def visualize_selected_signals():
            """Visualize only the selected signals"""
            global cached_routing, cached_architecture, cached_architecture_filename, cached_routing_filename
            
            try:
                if cached_routing is None:
                    return jsonify({'success': False, 'error': 'Load the .route file first'}), 400
                
                if cached_architecture is None:
                    return jsonify({'success': False, 'error': 'Load the architecture first'}), 400
                
                data = request.get_json()
                
                selected_signals = data.get('signals', [])
                show_signals = data.get('show_signals', True)
                show_grid = data.get('show_grid', True)
                show_directions = data.get('show_directions', True)
                show_bounding_boxes = data.get('show_bounding_boxes', True)
                show_bounding_box_labels = data.get('show_bounding_box_labels', False)
                show_signal_labels = data.get('show_signal_labels', True)
                show_heatmap = data.get('show_heatmap', True)
                
                # Fetch filter information
                filter_type = data.get('filter_type', None)
                filter_value = data.get('filter_value', None)
                
                print("=" * 60)
                print("📊 VISUALIZATION REQUEST")
                print(f"Selected signals: {selected_signals}")
                print(f"Total cached routes: {len(cached_routing.routes)}")
                print("=" * 60)
                
                if not selected_signals:
                    return jsonify({'success': False, 'error': 'No signals selected'}), 400
                
                # Filter routes
                filtered_routes = [
                    route for route in cached_routing.routes 
                    if route.net_name in selected_signals
                ]
                
                print(f"Filtered routes: {len(filtered_routes)}")
                for route in filtered_routes:
                    print(f"  - {route.net_name}")
                
                if not filtered_routes:
                    return jsonify({'success': False, 'error': 'Selected signals do not exist'}), 400
                
                # Create filtered routing
                filtered_routing = RoutingResult(
                    routes=filtered_routes,
                    congestion=cached_routing.congestion,
                    architecture=cached_architecture,
                    circuit=cached_routing.circuit,
                    successful=True
                )
                
                # Visualization
                visualizer = SignalVisualizer()
                
                # IMPORTANT: Correct path
                output_filename = 'routing_visualization.png'
                output_path = os.path.join(settings.OUTPUT_FOLDER, output_filename)
                
                # Create the folder if it does not exist
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                
                print(f"📁 Saving image to: {output_path}")
                
                visualizer.visualize_routing(
                    architecture=cached_architecture,
                    routing=filtered_routing,
                    output_path=output_path,
                    show_grid=show_grid,
                    show_signals=show_signals,
                    show_directions=show_directions,
                    show_bounding_boxes=show_bounding_boxes,
                    show_bounding_box_labels=show_bounding_box_labels,
                    show_signal_labels=show_signal_labels,
                    show_heatmap=show_heatmap,
                    show_legend=True,
                    architecture_file=cached_architecture_filename,
                    routing_file=cached_routing_filename,
                    filter_type=filter_type,
                    filter_value=filter_value
                )
                
                # CHECK: Does the file exist?
                if not os.path.exists(output_path):
                    print(f"❌ ERROR: File was not created!")
                    return jsonify({'success': False, 'error': 'Image was not generated'}), 500
                
                print(f"✅ Image created successfully: {os.path.getsize(output_path)} bytes")
                print("=" * 60)
                
                # IMPORTANT: Return only the filename, not the whole path
                return jsonify({
                    'success': True,
                    'image_path': output_filename,  # Only the file name
                    'signals_visualized': len(filtered_routes)
                })
            
            except Exception as e:
                import traceback
                traceback.print_exc()
                return jsonify({'success': False, 'error': str(e)}), 500
            
        @self.app.route('/visualize/signals', methods=['POST'])
        def visualize_signals():
            """Endpoint for routing visualization (saves the image in the OUTPUT folder)"""
            try:
                if not self.current_architecture:
                    return jsonify({'error': 'Architecture not loaded'}), 400
                if not self.current_routing:
                    return jsonify({'error': 'No routing loaded. Upload a .route file first.'}), 400

                data = request.get_json(silent=True) or {}
                show_grid = data.get('show_grid', True)
                show_segment_ids = data.get('show_segment_ids', True)

                # OUTPUT folder
                output_folder = getattr(settings, 'OUTPUT_FOLDER', os.path.join(os.getcwd(), 'output'))
                os.makedirs(output_folder, exist_ok=True)

                # filename and absolute path
                ts = int(time.time())
                filename = f"routing_visualization_{ts}.png"
                abs_path = os.path.join(output_folder, filename)

                # generate the image
                if not hasattr(self, 'signal_visualizer'):
                    self.signal_visualizer = SignalVisualizer()

                self.signal_visualizer.visualize_routing(
                    self.current_architecture,
                    self.current_routing,
                    abs_path,
                    show_grid=show_grid,
                    show_segment_ids=show_segment_ids,
                    architecture_file=self.architecture_filename,
                    routing_file=self.routing_filename
                )

                # frontend expects image_path and uses /download/<path>
                # return a path relative to OUTPUT (e.g. "output/filename.png")
                rel_path = f"output/{filename}"
                return jsonify({'success': True, 'image_path': rel_path})

            except Exception as e:
                import traceback
                traceback.print_exc()
                return jsonify({'error': str(e)}), 400
        
        @self.app.route('/analysis/conflicts', methods=['POST'])
        def analyze_conflicts():
            """Route for conflict analysis - works with routing or circuit data"""
            global cached_routing
            
            data = request.get_json(silent=True) or {}
            selected_signals = data.get('selected_signals', [])
            
            if cached_routing:
                try:
                    if selected_signals:
                        filtered_routing = RoutingResult(
                            routes=[route for route in cached_routing.routes 
                                   if route.net_name in selected_signals]
                        )
                    else:
                        filtered_routing = cached_routing
                    
                    if not filtered_routing.routes:
                        return jsonify({'error': 'No signals selected for analysis'}), 400
                    
                    conflict_graph = self.conflict_builder.build_conflict_graph(filtered_routing)
                    hubs = self.conflict_builder.identify_hubs()
                    metrics = self.conflict_builder.calculate_graph_metrics()
                    
                    fig = self.conflict_builder.visualize_conflict_graph()
                    os.makedirs(settings.OUTPUT_FOLDER, exist_ok=True)
                    
                    ts = int(time.time())
                    filename = f'conflict_graph_{ts}.png'
                    conflict_viz_path = os.path.join(settings.OUTPUT_FOLDER, filename)
                    fig.savefig(conflict_viz_path, bbox_inches='tight', dpi=150)
                    plt.close(fig)
                    
                    return jsonify({
                        'success': True,
                        'hubs': hubs,
                        'metrics': metrics,
                        'conflict_viz_path': f'output/{filename}',
                        'num_signals': len(filtered_routing.routes)
                    })
                    
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    return jsonify({'error': str(e)}), 400
            
            elif self.current_circuit:
                try:
                    conflict_graph = self.conflict_builder.build_conflict_graph(self.current_circuit)
                    hubs = self.conflict_builder.identify_hubs()
                    metrics = self.conflict_builder.calculate_graph_metrics()
                    
                    # Conflict graph visualization
                    fig = self.conflict_builder.visualize_conflict_graph()
                    os.makedirs(settings.OUTPUT_FOLDER, exist_ok=True)
                    
                    ts = int(time.time())
                    filename = f'conflict_graph_{ts}.png'
                    conflict_viz_path = os.path.join(settings.OUTPUT_FOLDER, filename)
                    fig.savefig(conflict_viz_path, bbox_inches='tight', dpi=150)
                    plt.close(fig)
                    
                    return jsonify({
                        'success': True,
                        'hubs': hubs,
                        'metrics': metrics,
                        'conflict_viz_path': f'output/{filename}'
                    })
                    
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    return jsonify({'error': str(e)}), 400
            else:
                return jsonify({'error': 'No routing or circuit data loaded. Upload a .route file first.'}), 400
        
        @self.app.route('/analysis/statistics', methods=['GET'])
        def get_statistics():
            """Route for statistical analysis"""
            if not self.current_circuit or not self.current_architecture:
                return jsonify({'error': 'No circuit or architecture loaded'}), 400
            
            try:
                stats = self.stats_calculator.calculate_comprehensive_stats(
                    self.current_circuit, 
                    self.current_architecture
                )
                
                return jsonify({
                    'success': True,
                    'statistics': stats
                })
                
            except Exception as e:
                return jsonify({'error': str(e)}), 400
        
        @self.app.route('/demo', methods=['GET'])
        def create_demo():
            """Route for creating demo data"""
            try:
                # Creating demo architecture
                self.current_architecture = self.architecture_parser.parse_simple_architecture(3, 10)
                
                # Creating demo circuit
                self.current_circuit = self.circuit_parser.create_test_circuit(14)
                
                return jsonify({
                    'success': True,
                    'message': 'Demo data created successfully',
                    'architecture': self.current_architecture.to_dict(),
                    'circuit': self.current_circuit.to_dict()
                })
                
            except Exception as e:
                return jsonify({'error': str(e)}), 400
        
        @self.app.route('/download/<path:filename>')
        def download_file(filename):
            """Route for downloading generated files"""
            try:
                # Security: check that filename does not contain '..' or '/'
                if '..' in filename or filename.startswith('/'):
                    return jsonify({'error': 'Invalid filename'}), 400
            
                file_path = os.path.join(settings.OUTPUT_FOLDER, filename)
                if os.path.exists(file_path):
                    return send_file(file_path, as_attachment=False)  # as_attachment=False for display in the browser
                else:
                    return jsonify({'error': 'File not found'}), 404
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @self.app.route('/static/output/<path:filename>')
        def static_output_file(filename):
            """Route for static files from the output folder"""
            try:
                file_path = os.path.join(settings.OUTPUT_FOLDER, filename)
                if os.path.exists(file_path):
                    return send_file(file_path)
                else:
                    return jsonify({'error': 'File not found'}), 404
            except Exception as e:
                return jsonify({'error': str(e)}), 500
            
        @self.app.route('/visualize/congestion', methods=['POST'])
        def visualize_congestion():
            """Route for congestion visualization"""
            if not self.current_architecture or not self.current_routing:
                return jsonify({'error': 'No architecture or routing results loaded'}), 400
            
            data = request.get_json() or {}
            vis_type = data.get('visualization_type', 'current')
            
            try:
                fig = self.congestion_visualizer.visualize_congestion(
                    self.current_architecture,
                    self.current_routing,
                    vis_type
                )
                
                output_path = os.path.join(settings.OUTPUT_FOLDER, 'congestion_visualization.png')
                self.congestion_visualizer.save_visualization(output_path)
                
                # Generate a congestion report
                report = self.congestion_visualizer.generate_congestion_report(
                    self.current_architecture,
                    self.current_routing
                )
                
                return jsonify({
                    'success': True,
                    'image_path': output_path,
                    'report': report
                })
                
            except Exception as e:
                return jsonify({'error': str(e)}), 400

        @self.app.route('/web/data', methods=['GET'])
        def get_web_data():
            """Route for web visualization data"""
            if not self.current_architecture or not self.current_circuit:
                return jsonify({'error': 'No architecture or circuit loaded'}), 400
            
            try:
                data = self.web_visualizer.create_simple_visualization_data(
                    self.current_architecture,
                    self.current_circuit,
                    self.current_routing
                )
                
                return jsonify({
                    'success': True,
                    'data': data
                })
                
            except Exception as e:
                return jsonify({'error': str(e)}), 400
            
        
            
    
    def run(self, host: str = None, port: int = None, debug: bool = None):
        """Starts the Flask application"""
        host = host or settings.HOST
        port = port or settings.PORT
        debug = debug or settings.DEBUG
        
        print(f"Starting FPGA Visualization Tool...")
        print(f"Server running on http://{host}:{port}")
        print(f"Debug mode: {debug}")
        
        # Creating the output directory if it does not exist
        os.makedirs(settings.OUTPUT_FOLDER, exist_ok=True)
        os.makedirs(settings.UPLOAD_FOLDER, exist_ok=True)
        
        print(f"📁 Output folder: {os.path.abspath(settings.OUTPUT_FOLDER)}")
        print(f"📁 Upload folder: {os.path.abspath(settings.UPLOAD_FOLDER)}")
        
        # Check permissions
        try:
            test_file = os.path.join(settings.OUTPUT_FOLDER, 'test.txt')
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            print("✅ Output folder is writable")
        except Exception as e:
            print(f"❌ Problem with the output folder: {e}")
        
        # Print all registered routes
        print("\n📋 Registered routes:")
        for rule in self.app.url_map.iter_rules():
            methods = ', '.join(sorted(rule.methods - {'HEAD', 'OPTIONS'}))
            print(f"  {rule.endpoint:30s} {methods:20s} {rule.rule}")
        print()
        
        self.app.run(host=host, port=port, debug=debug)

def main():
    """Main function for starting the application"""
    app = FPGAVisualizationApp()
    app.run()

if __name__ == "__main__":
    main()