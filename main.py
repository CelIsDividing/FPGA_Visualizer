#!/usr/bin/env python3
"""
FPGA Vizuelizacioni Alat - Glavna aplikacija
Proces razvoja informacionih sistema 2025
"""

import os
import sys
import re
import json
import time
import matplotlib.pyplot as plt
from visualization.congestion_visualizer import CongestionVisualizer
from visualization.web_visualizer import WebVisualizer
from flask_cors import CORS
from typing import Dict, List, Optional
from flask import Flask, render_template, request, jsonify, send_file

# Dodavanje putanje za import modula
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
from analysis.statistics_calculator import StatisticsCalculator

# Globalne promenljive za keširane podatke
cached_routing = None
cached_architecture = None
cached_architecture_filename = None
cached_routing_filename = None

class FPGAVisualizationApp:
    """Glavna klasa FPGA vizuelizacionog alata"""
    
    def __init__(self):
        self.app = Flask(__name__)
        self.app.config['UPLOAD_FOLDER'] = settings.UPLOAD_FOLDER
        self.congestion_visualizer = CongestionVisualizer()
        self.web_visualizer = WebVisualizer()
        
        CORS(self.app)

        # Inicijalizacija komponenti
        self.architecture_parser = ArchitectureParser()
        self.circuit_parser = CircuitParser()
        self.routing_parser = RoutingParser()
        self.signal_visualizer = SignalVisualizer()
        self.conflict_builder = ConflictGraphBuilder()
        self.stats_calculator = StatisticsCalculator()
        
        # Podaci aplikacije
        self.current_architecture: Optional[FPGAArchitecture] = None
        self.current_circuit: Optional[Circuit] = None
        self.current_routing: Optional[RoutingResult] = None
        
        # Imena učitanih fajlova
        self.architecture_filename: Optional[str] = None
        self.routing_filename: Optional[str] = None
        
        self._setup_routes()
    
    def _setup_routes(self):
        """Podešava Flask rute"""
        
        @self.app.route('/')
        def index():
            return render_template('index.html')
        
        @self.app.route('/upload/architecture', methods=['POST'])
        def upload_architecture():
            """Ruta za upload FPGA arhitekture"""
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
                    # Pokušaj poziva uobičajenih metoda parsera (parse / parse_xml / parse_architecture_file)
                    parser = self.architecture_parser
                    arch = None
                    if hasattr(parser, 'parse'):
                        arch = parser.parse(filepath)
                    elif hasattr(parser, 'parse_xml'):
                        arch = parser.parse_xml(filepath)
                    elif hasattr(parser, 'parse_architecture_file'):
                        arch = parser.parse_architecture_file(filepath)
                    else:
                        raise RuntimeError('ArchitectureParser nema podržanu metodu za parsiranje')

                    # Očekuje se da parser vrati instancu FPGAArchitecture
                    self.current_architecture = arch
                    self.architecture_filename = filename  # Sačuvaj ime fajla
                    
                    # Ažuriraj globalne kešove za vizualizaciju
                    global cached_architecture, cached_architecture_filename
                    cached_architecture = arch
                    cached_architecture_filename = filename

                    # Ako objekat ima to_dict, vratiti ga klijentu radi prikaza
                    arch_dict = {}
                    if arch is not None and hasattr(arch, 'to_dict'):
                        arch_dict = arch.to_dict()

                    return jsonify({'success': True, 'architecture': arch_dict})
            except Exception as e:
                import traceback
                traceback.print_exc()  # ispisi stack trace u server konzoli
                # Ako smo u debug modu, vrati i trace u JSON radi lakše dijagnostike
                if getattr(settings, 'DEBUG', False):
                    return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 400
                return jsonify({'error': str(e)}), 400
        
        @self.app.route('/upload/routing', methods=['POST'])
        def upload_routing():
            """Route for uploading routing results (.route)"""
            print("=" * 50)
            print("📥 PRIMLJEN ZAHTEV ZA UPLOAD RUTIRANJA")
            
            if 'file' not in request.files:
                print("❌ NEMA FAJLA U ZAHTEVU")
                return jsonify({'error': 'No file uploaded'}), 400

            file = request.files['file']
            print(f"📄 FAJL: {file.filename}")
            print(f"📊 VELIČINA: {len(file.read()) if file else 0} bytes")
            file.seek(0)  # Reset file pointer
            
            if file.filename == '':
                print("❌ PRAZNO IME FAJLA")
                return jsonify({'error': 'No file selected'}), 400
                
            if not file.filename.endswith('.route'):
                print("❌ POGREŠNA EKSTENZIJA")
                return jsonify({'error': 'Invalid file type - must be .route'}), 400

            try:
                # Save uploaded file
                os.makedirs(settings.UPLOAD_FOLDER, exist_ok=True)
                filepath = os.path.join(settings.UPLOAD_FOLDER, file.filename)
                file.save(filepath)
                print(f"💾 FAJL SAČUVAN: {filepath}")

                # Require architecture to be loaded first
                if not self.current_architecture:
                    print("❌ NIJE UČITANA ARHITEKTURA")
                    return jsonify({'error': 'Upload architecture (.xml) before routing file'}), 400

                print("🔍 POČINJEM PARSIRANJE ROUTING FAJLA...")
                # Parse routing file
                self.current_routing = self.routing_parser.parse_routing_file(
                    filepath,
                    self.current_architecture,
                    self.current_circuit  # Optional
                )
                self.routing_filename = file.filename  # Sačuvaj ime fajla
                print("✅ ROUTING USPEŠNO PARSIRAN")

                routing_dict = self.current_routing.to_dict() if self.current_routing else {}
                print(f"📊 BROJ RUTA: {len(routing_dict.get('routes', []))}")

                return jsonify({
                    'success': True,
                    'routing': routing_dict
                })

            except Exception as e:
                print(f"💥 GREŠKA PRI PARSIRANJU: {str(e)}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': str(e)}), 400
        
        @self.app.route('/api/parse_routing', methods=['POST'])
        def parse_routing():
            """Parse .route fajl i vrati listu signala"""
            global cached_routing, cached_architecture, cached_routing_filename, cached_architecture_filename
            
            try:
                if 'routing_file' not in request.files:
                    return jsonify({'success': False, 'error': 'Nema fajla'}), 400
                
                file = request.files['routing_file']
                if file.filename == '':
                    return jsonify({'success': False, 'error': 'Prazan fajl'}), 400
                
                import tempfile
                
                with tempfile.NamedTemporaryFile(delete=False, suffix='.route') as tmp:
                    file.save(tmp.name)
                    tmp_path = tmp.name
                
                try:
                    width, height = 4, 4  # Default
            
                    with open(tmp_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            # Traži: "Array size: 10 x 10 logic blocks"
                            match = re.search(r'Array\s+size:\s+(\d+)\s+x\s+(\d+)', line, re.IGNORECASE)
                            if match:
                                width = int(match.group(1))
                                height = int(match.group(2))
                                print(f"✅ Pročitane dimenzije iz .route: {width}×{height}")
                                break
                    
                    parser = RoutingParser()
                    
                    # KREIRAJ ARHITEKTURU SA PRAVIM DIMENZIJAMA
                    # Ako arhitektura ne postoji ili dimenzije ne odgovaraju
                    if cached_architecture is None or \
                    cached_architecture.width != width or \
                    cached_architecture.height != height:
                        from models.fpga_architecture import FPGAArchitecture
                        cached_architecture = FPGAArchitecture(width=width, height=height)
                        # Samo postavi auto-generated ime ako nije bilo ručno učitane arhitekture
                        if cached_architecture_filename is None or cached_architecture_filename.startswith("Auto-generated"):
                            cached_architecture_filename = f"Auto-generated {width}x{height}"
                        print(f"🏗️ Kreirana arhitektura: {width}×{height}")
                    
                    routing_result = parser.parse_routing_file(
                        tmp_path, 
                        architecture=cached_architecture,
                        circuit=None
                    )
                    
                    # KEŠIRANJE
                    cached_routing = routing_result
                    cached_routing_filename = file.filename
                    
                    # Izvuci signale
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
            """Ruta za upload kola"""
            print("=" * 50)
            print("📥 PRIMLJEN ZAHTEV ZA UPLOAD KOLA")
            
            if 'file' not in request.files:
                print("❌ NEMA FAJLA U ZAHTEVU")
                return jsonify({'error': 'No file uploaded'}), 400
            
            file = request.files['file']
            print(f"📄 FAJL: {file.filename}")
            print(f"📊 VELIČINA: {len(file.read()) if file else 0} bytes")
            
            # Vrati se na početak fajla
            file.seek(0)
            
            if file.filename == '':
                print("❌ PRAZNO IME FAJLA")
                return jsonify({'error': 'No file selected'}), 400
            
            # Kreiraj uploads folder ako ne postoji
            os.makedirs(settings.UPLOAD_FOLDER, exist_ok=True)
            filepath = os.path.join(settings.UPLOAD_FOLDER, file.filename)
            
            try:
                file.save(filepath)
                print(f"💾 FAJL SAČUVAN: {filepath}")
                
                if file.filename.endswith('.v'):
                    print("🔧 PARSIRAM VERILOG...")
                    self.current_circuit = self.circuit_parser.parse_verilog(filepath)
                elif file.filename.endswith('.blif'):
                    print("🔧 PARSIRAM BLIF...")
                    self.current_circuit = self.circuit_parser.parse_blif(filepath)
                else:
                    print("❌ NEPODRŽAN FORMAT")
                    return jsonify({'error': 'Unsupported file format. Use .v or .blif'}), 400
                
                print(f"✅ KOLO PARSIRANO: {self.current_circuit.name}")
                print(f"📈 SIGNALI: {len(self.current_circuit.signals)}")
                print(f"🔧 KOMPONENTE: {len(self.current_circuit.components)}")
                
                return jsonify({
                    'success': True,
                    'circuit': self.current_circuit.to_dict()
                })
                
            except Exception as e:
                print(f"💥 GREŠKA PRI PARSIRANJU: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': str(e)}), 400
        
        @self.app.route('/api/visualize', methods=['POST'])
        def visualize_selected_signals():
            """Vizuelizuj samo selektovane signale"""
            global cached_routing, cached_architecture, cached_architecture_filename, cached_routing_filename
            
            try:
                if cached_routing is None:
                    return jsonify({'success': False, 'error': 'Prvo učitaj .route fajl'}), 400
                
                if cached_architecture is None:
                    return jsonify({'success': False, 'error': 'Prvo učitaj arhitekturu'}), 400
                
                data = request.get_json()
                
                selected_signals = data.get('signals', [])
                show_signals = data.get('show_signals', True)
                show_grid = data.get('show_grid', True)
                show_directions = data.get('show_directions', True)
                show_bounding_boxes = data.get('show_bounding_boxes', True)
                show_bounding_box_labels = data.get('show_bounding_box_labels', False)
                show_signal_labels = data.get('show_signal_labels', True)
                show_heatmap = data.get('show_heatmap', True)
                
                # Dobavi filter informacije
                filter_type = data.get('filter_type', None)
                filter_value = data.get('filter_value', None)
                
                print("=" * 60)
                print("📊 VISUALIZATION REQUEST")
                print(f"Selected signals: {selected_signals}")
                print(f"Total cached routes: {len(cached_routing.routes)}")
                print("=" * 60)
                
                if not selected_signals:
                    return jsonify({'success': False, 'error': 'Nema selektovanih signala'}), 400
                
                # Filtriraj rute
                filtered_routes = [
                    route for route in cached_routing.routes 
                    if route.net_name in selected_signals
                ]
                
                print(f"Filtered routes: {len(filtered_routes)}")
                for route in filtered_routes:
                    print(f"  - {route.net_name}")
                
                if not filtered_routes:
                    return jsonify({'success': False, 'error': 'Selektovani signali ne postoje'}), 400
                
                # Kreiraj filtrirani routing
                filtered_routing = RoutingResult(
                    routes=filtered_routes,
                    congestion=cached_routing.congestion,
                    architecture=cached_architecture,
                    circuit=cached_routing.circuit,
                    successful=True
                )
                
                # Vizuelizacija
                visualizer = SignalVisualizer()
                
                # VAŽNO: Pravilna putanja
                output_filename = 'routing_visualization.png'
                output_path = os.path.join(settings.OUTPUT_FOLDER, output_filename)
                
                # Kreiraj folder ako ne postoji
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                
                print(f"📁 Čuvam sliku na: {output_path}")
                
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
                
                # PROVERA: Da li fajl postoji?
                if not os.path.exists(output_path):
                    print(f"❌ GREŠKA: Fajl nije kreiran!")
                    return jsonify({'success': False, 'error': 'Slika nije generisana'}), 500
                
                print(f"✅ Slika uspešno kreirana: {os.path.getsize(output_path)} bytes")
                print("=" * 60)
                
                # VAŽNO: Vrati samo filename, ne celu putanju
                return jsonify({
                    'success': True,
                    'image_path': output_filename,  # Samo ime fajla
                    'signals_visualized': len(filtered_routes)
                })
            
            except Exception as e:
                import traceback
                traceback.print_exc()
                return jsonify({'success': False, 'error': str(e)}), 500
            
        @self.app.route('/visualize/signals', methods=['POST'])
        def visualize_signals():
            """Endpoint za vizuelizaciju rutiranja (sliku čuva u OUTPUT folder)"""
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

                # filename i apsolutna putanja
                ts = int(time.time())
                filename = f"routing_visualization_{ts}.png"
                abs_path = os.path.join(output_folder, filename)

                # generiši sliku
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

                # frontend očekuje image_path i koristi /download/<path>
                # vrati relativno u odnosu na OUTPUT (npr. "output/filename.png")
                rel_path = f"output/{filename}"
                return jsonify({'success': True, 'image_path': rel_path})

            except Exception as e:
                import traceback
                traceback.print_exc()
                return jsonify({'error': str(e)}), 400
        
        @self.app.route('/analysis/conflicts', methods=['POST'])
        def analyze_conflicts():
            """Ruta za analizu konflikata - radi sa routing ili circuit podacima"""
            global cached_routing
            
            # Uzmi selektovane signale iz POST requesta
            data = request.get_json(silent=True) or {}
            selected_signals = data.get('selected_signals', [])
            
            # Prvo proveri da li postoji učitani routing (prioritet)
            if cached_routing:
                try:
                    # Filtriraj routing da sadrži samo selektovane signale
                    if selected_signals:
                        filtered_routing = RoutingResult(
                            routes=[route for route in cached_routing.routes 
                                   if route.net_name in selected_signals]
                        )
                    else:
                        filtered_routing = cached_routing
                    
                    if not filtered_routing.routes:
                        return jsonify({'error': 'Nema selektovanih signala za analizu'}), 400
                    
                    conflict_graph = self.conflict_builder.build_conflict_graph(filtered_routing)
                    hubs = self.conflict_builder.identify_hubs()
                    metrics = self.conflict_builder.calculate_graph_metrics()
                    
                    # Vizuelizacija konflikt grafa
                    fig = self.conflict_builder.visualize_conflict_graph()
                    os.makedirs(settings.OUTPUT_FOLDER, exist_ok=True)
                    
                    # Generiši jedinstveno ime sa timestamp
                    ts = int(time.time())
                    filename = f'conflict_graph_{ts}.png'
                    conflict_viz_path = os.path.join(settings.OUTPUT_FOLDER, filename)
                    fig.savefig(conflict_viz_path, bbox_inches='tight', dpi=150)
                    plt.close(fig)
                    
                    return jsonify({
                        'success': True,
                        'hubs': hubs,
                        'metrics': metrics,
                        'conflict_viz_path': f'output/{filename}',  # Relativna putanja za frontend
                        'num_signals': len(filtered_routing.routes)
                    })
                    
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    return jsonify({'error': str(e)}), 400
            
            # Fallback na circuit ako postoji
            elif self.current_circuit:
                try:
                    conflict_graph = self.conflict_builder.build_conflict_graph(self.current_circuit)
                    hubs = self.conflict_builder.identify_hubs()
                    metrics = self.conflict_builder.calculate_graph_metrics()
                    
                    # Vizuelizacija konflikt grafa
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
            """Ruta za statističku analizu"""
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
            """Ruta za kreiranje demo podataka"""
            try:
                # Kreiranje demo arhitekture
                self.current_architecture = self.architecture_parser.parse_simple_architecture(3, 10)
                
                # Kreiranje demo kola
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
            """Ruta za preuzimanje generisanih fajlova"""
            try:
                # Bezbednost: proveri da filename ne sadrži '..' ili '/'
                if '..' in filename or filename.startswith('/'):
                    return jsonify({'error': 'Invalid filename'}), 400
            
                file_path = os.path.join(settings.OUTPUT_FOLDER, filename)
                if os.path.exists(file_path):
                    return send_file(file_path, as_attachment=False)  # as_attachment=False za prikaz u browseru
                else:
                    return jsonify({'error': 'File not found'}), 404
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @self.app.route('/static/output/<path:filename>')
        def static_output_file(filename):
            """Ruta za statičke fajlove iz output foldera"""
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
            """Ruta za vizuelizaciju zagušenja"""
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
                
                # Generiši izveštaj o zagušenju
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
            """Ruta za web vizuelizacione podatke"""
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
        """Pokreće Flask aplikaciju"""
        host = host or settings.HOST
        port = port or settings.PORT
        debug = debug or settings.DEBUG
        
        print(f"Starting FPGA Visualization Tool...")
        print(f"Server running on http://{host}:{port}")
        print(f"Debug mode: {debug}")
        
        # Kreiranje output direktorijuma ako ne postoji
        os.makedirs(settings.OUTPUT_FOLDER, exist_ok=True)
        os.makedirs(settings.UPLOAD_FOLDER, exist_ok=True)
        
        print(f"📁 Output folder: {os.path.abspath(settings.OUTPUT_FOLDER)}")
        print(f"📁 Upload folder: {os.path.abspath(settings.UPLOAD_FOLDER)}")
        
        # Proveri permissions
        try:
            test_file = os.path.join(settings.OUTPUT_FOLDER, 'test.txt')
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            print("✅ Output folder je upisiv")
        except Exception as e:
            print(f"❌ Problem sa output folderom: {e}")
        
        # Ispis svih registrovanih ruta
        print("\n📋 Registrovane rute:")
        for rule in self.app.url_map.iter_rules():
            methods = ', '.join(sorted(rule.methods - {'HEAD', 'OPTIONS'}))
            print(f"  {rule.endpoint:30s} {methods:20s} {rule.rule}")
        print()
        
        self.app.run(host=host, port=port, debug=debug)

def main():
    """Glavna funkcija za pokretanje aplikacije"""
    app = FPGAVisualizationApp()
    app.run()

if __name__ == "__main__":
    main()