// FPGA Visualizer - JavaScript klijentski kod

class FPGAVisualizer {
    constructor() {
        this.currentArchitecture = null;
        this.currentCircuit = null;
        this.currentRouting = null;
        this.uploadInProgress = false;
        this.area = document.getElementById('visualizationArea');
        this.btnVisualize = document.getElementById('visualizeBtn');
        this.chkGrid = document.getElementById('showGrid');
        
        // Istorija učitanih fajlova
        this.architectureHistory = [];
        this.routingHistory = [];
        
        console.log("🔧 FPGA Visualizer inicijalizovan");
        this.initEventListeners();
    }

    initEventListeners() {
        console.log("🔧 Inicijalizujem event listenere...");
        
        // Ručno poveži sve dugmad - PREKIDAMO onclick atribute
        this.bindButton('.demo-btn', () => this.createDemo());
        this.bindButton('#uploadArchBtn', () => this.uploadArchitecture());
        this.bindButton('#uploadCircuitBtn', () => this.uploadCircuit());
        this.bindButton('#uploadRoutingBtn', () => this.uploadRouting());
        this.bindButton('#visualizeBtn', () => this.visualizeSelectedSignals());
        this.bindButton('#analyzeBtn', () => this.analyzeConflicts());
        this.bindButton('#statsBtn', () => this.showStatistics());
        
        // Poveži file input change event-e
        this.bindFileInput('archFile', () => this.onArchFileSelected());
        this.bindFileInput('circuitFile', () => this.onCircuitFileSelected());
        this.bindFileInput('routingFile', () => this.onRoutingFileSelected());

        this.bindButton('#selectAllSignals', () => this.selectAllSignals());
        this.bindButton('#deselectAllSignals', () => this.deselectAllSignals());
        
        // Filter dugme
        this.bindButton('#applyFilterBtn', () => this.applySignalFilter());
        
        // Heat mapa checkbox logika
        const heatmapCheckbox = document.getElementById('showHeatmap');
        if (heatmapCheckbox) {
            heatmapCheckbox.addEventListener('change', () => this.onHeatmapToggle());
        }
        
        // Ostali checkboxovi - ako se čekiraju, odčekiraj heat mapu
        const otherCheckboxes = ['showSignals', 'showDirections', 'showBoundingBoxes', 'showSignalLabels'];
        otherCheckboxes.forEach(id => {
            const checkbox = document.getElementById(id);
            if (checkbox) {
                checkbox.addEventListener('change', () => this.onOtherOptionToggle());
            }
        });

        console.log("✅ Event listeneri inicijalizovani");

        if (this.btnVisualize) {
            this.btnVisualize.addEventListener('click', () => this.visualizeSignals());
        }
    }

    bindButton(selector, handler) {
        const button = document.querySelector(selector);
        if (button) {
            button.addEventListener('click', () => {
                console.log(`🖱️ Kliknuto na dugme: ${selector}`);
                handler();
            });
            console.log(`✅ Povezan dugme: ${selector}`);
        } else {
            console.log(`❌ Dugme nije pronađeno: ${selector}`);
        }
    }

    bindFileInput(inputId, changeHandler) {
        const input = document.getElementById(inputId);
        if (input) {
            input.addEventListener('change', changeHandler);
            console.log(`✅ Povezan file input: ${inputId}`);
        }
    }

    onArchFileSelected() {
        const fileInput = document.getElementById('archFile');
        if (fileInput.files.length > 0) {
            console.log('🏗️ Izabrana arhitektura:', fileInput.files[0].name);
            // Automatski pokreni upload
            this.uploadArchitecture();
        }
    }

    onRoutingFileSelected() { 
        const fileInput = document.getElementById('routingFile');
        if (fileInput.files.length > 0) {
            console.log('🧭 Izabrano rutiranje:', fileInput.files[0].name);
            this.uploadRoutingAndParseSignals();
        }
    }

    async uploadRoutingAndParseSignals() {
        const fileInput = document.getElementById('routingFile');
        const file = fileInput.files[0];
        if (!file) return;

        this.uploadInProgress = true;
        this.showMessage('Učitavam .route fajl...', 'info');

        const formData = new FormData();
        formData.append('routing_file', file);

        try {
            const response = await fetch('/api/parse_routing', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            
            if (data.success) {
                this.loadedSignals = data.signals || [];
                this.populateSignalsList(this.loadedSignals);
                this.showMessage(`Učitano ${this.loadedSignals.length} signala`, 'success');
                
                // Dodaj u istoriju
                this.addToRoutingHistory(file.name);
                
                // Postavi currentRouting i currentArchitecture kao "učitano"
                // (potrebno za dugme "Analiziraj konflikte")
                this.currentRouting = { loaded: true };
                this.currentArchitecture = { loaded: true };
            } else {
                throw new Error(data.error || 'Nepoznata greška');
            }

        } catch (error) {
            console.error('Error loading routing file:', error);
            this.showMessage(`Greška: ${error.message}`, 'error');
        } finally {
            this.uploadInProgress = false;
        }
    }

    populateSignalsList(signals) {
        const panel = document.getElementById('signalsPanel');
        const list = document.getElementById('signalsList');
        const countSpan = document.getElementById('signalCount');
        
        if (!signals || signals.length === 0) {
            panel.style.display = 'none';
            return;
        }

        panel.style.display = 'block';
        countSpan.textContent = signals.length;
        list.innerHTML = '';

        const SIGNAL_COLORS = ["#e41a1c", "#377eb8", "#4daf4a", "#ff7f00", "#984ea3", "#00aa7f"];

        signals.forEach((signal, index) => {
            const color = SIGNAL_COLORS[index % SIGNAL_COLORS.length];
            
            const item = document.createElement('div');
            item.className = 'signal-item';
            
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.id = `signal-${index}`;
            checkbox.checked = true;
            checkbox.dataset.signalName = signal.net_name;
            checkbox.dataset.segmentCount = signal.segment_count || signal.fanout || 0;
            
            const label = document.createElement('label');
            label.htmlFor = `signal-${index}`;
            label.className = 'signal-name';
            label.textContent = signal.net_name;
            label.style.cursor = 'pointer';
            
            const info = document.createElement('span');
            info.className = 'signal-info';
            info.textContent = `${signal.segment_count || signal.fanout || '?'} čvorova`;
            
            
            item.appendChild(checkbox);
            item.appendChild(label);
            item.appendChild(info);
            
            list.appendChild(item);
        });
    }

    selectAllSignals() {
        document.querySelectorAll('#signalsList input[type="checkbox"]').forEach(cb => {
            cb.checked = true;
        });
    }

    deselectAllSignals() {
        document.querySelectorAll('#signalsList input[type="checkbox"]').forEach(cb => {
            cb.checked = false;
        });
    }
    
    getSelectedSignals() {
        return Array.from(
            document.querySelectorAll('#signalsList input[type="checkbox"]:checked')
        ).map(cb => cb.dataset.signalName);
    }
    
    addToArchitectureHistory(filename) {
        const timestamp = new Date().toLocaleString('sr-RS', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
        
        this.architectureHistory.push({
            filename: filename,
            timestamp: timestamp
        });
        
        this.updateFileHistory();
    }
    
    addToRoutingHistory(filename) {
        const timestamp = new Date().toLocaleString('sr-RS', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
        
        this.routingHistory.push({
            filename: filename,
            timestamp: timestamp
        });
        
        this.updateFileHistory();
    }
    
    updateFileHistory() {
        // Ažuriraj arhitekturu listu
        const archList = document.getElementById('archHistoryList');
        if (archList) {
            if (this.architectureHistory.length === 0) {
                archList.innerHTML = '<li class="history-empty">Nema učitanih fajlova</li>';
            } else {
                archList.innerHTML = this.architectureHistory.map(item => `
                    <li>
                        <span class="file-icon">�️</span>
                        <span class="file-name">${item.filename}</span>
                        <span class="file-time">${item.timestamp}</span>
                    </li>
                `).join('');
            }
        }
        
        // Ažuriraj routing listu
        const routeList = document.getElementById('routeHistoryList');
        if (routeList) {
            if (this.routingHistory.length === 0) {
                routeList.innerHTML = '<li class="history-empty">Nema učitanih fajlova</li>';
            } else {
                routeList.innerHTML = this.routingHistory.map(item => `
                    <li>
                        <span class="file-icon">�</span>
                        <span class="file-name">${item.filename}</span>
                        <span class="file-time">${item.timestamp}</span>
                    </li>
                `).join('');
            }
        }
    }

    applySignalFilter() {
        const filterType = document.getElementById('filterType').value;
        const filterValue = parseInt(document.getElementById('filterValue').value) || 10;
        
        const allCheckboxes = Array.from(document.querySelectorAll('#signalsList input[type="checkbox"]'));
        const totalSignals = allCheckboxes.length;
        
        if (filterType === 'none') {
            // Čekiraj sve signale
            allCheckboxes.forEach(cb => cb.checked = true);
            this.showMessage('Svi signali odabrani', 'success');
            return;
        }
        
        // Prvo odčekiraj sve
        allCheckboxes.forEach(cb => cb.checked = false);
        
        if (filterType === 'first') {
            // Čekiraj prvih N signala
            const toCheck = allCheckboxes.slice(0, filterValue);
            toCheck.forEach(cb => cb.checked = true);
            const unchecked = totalSignals - toCheck.length;
            this.showMessage(`Odabrano prvih ${toCheck.length} signala (odčekirano ${unchecked})`, 'success');
        }
        else if (filterType === 'last') {
            // Čekiraj poslednjih N signala
            const toCheck = allCheckboxes.slice(-filterValue);
            toCheck.forEach(cb => cb.checked = true);
            const unchecked = totalSignals - toCheck.length;
            this.showMessage(`Odabrano poslednjih ${toCheck.length} signala (odčekirano ${unchecked})`, 'success');
        }
        else if (filterType === 'less_than') {
            // Čekiraj signale sa manje od N segmenata
            const filtered = allCheckboxes.filter(cb => {
                const segmentCount = parseInt(cb.dataset.segmentCount) || 0;
                return segmentCount < filterValue;
            });
            filtered.forEach(cb => cb.checked = true);
            const unchecked = totalSignals - filtered.length;
            this.showMessage(`Odabrano ${filtered.length} signala sa manje od ${filterValue} segmenata (odčekirano ${unchecked})`, 'success');
        }
        else if (filterType === 'more_than') {
            // Čekiraj signale sa više od N segmenata
            const filtered = allCheckboxes.filter(cb => {
                const segmentCount = parseInt(cb.dataset.segmentCount) || 0;
                return segmentCount > filterValue;
            });
            filtered.forEach(cb => cb.checked = true);
            const unchecked = totalSignals - filtered.length;
            this.showMessage(`Odabrano ${filtered.length} signala sa više od ${filterValue} segmenata (odčekirano ${unchecked})`, 'success');
        }
    }

    onHeatmapToggle() {
        const heatmapCheckbox = document.getElementById('showHeatmap');
        
        if (heatmapCheckbox && heatmapCheckbox.checked) {
            // Ako je heat mapa čekirana, odčekiraj sve ostale opcije
            const showSignals = document.getElementById('showSignals');
            const showDirections = document.getElementById('showDirections');
            const showBoundingBoxes = document.getElementById('showBoundingBoxes');
            const showSignalLabels = document.getElementById('showSignalLabels');
            
            if (showSignals) showSignals.checked = false;
            if (showDirections) showDirections.checked = false;
            if (showBoundingBoxes) showBoundingBoxes.checked = false;
            if (showSignalLabels) showSignalLabels.checked = false;
        }
    }

    onOtherOptionToggle() {
        const heatmapCheckbox = document.getElementById('showHeatmap');
        
        // Ako je bilo koja druga opcija čekirana, odčekiraj heat mapu
        const showSignals = document.getElementById('showSignals');
        const showDirections = document.getElementById('showDirections');
        const showBoundingBoxes = document.getElementById('showBoundingBoxes');
        const showSignalLabels = document.getElementById('showSignalLabels');
        
        if ((showSignals && showSignals.checked) ||
            (showDirections && showDirections.checked) ||
            (showBoundingBoxes && showBoundingBoxes.checked) ||
            (showSignalLabels && showSignalLabels.checked)) {
            if (heatmapCheckbox) {
                heatmapCheckbox.checked = false;
            }
        }
    }

    async visualizeSelectedSignals() {
        const selectedSignals = Array.from(
            document.querySelectorAll('#signalsList input[type="checkbox"]:checked')
        ).map(cb => cb.dataset.signalName);

        console.log('Selected signals:', selectedSignals);

        if (selectedSignals.length === 0) {
            this.showMessage('Nema selektovanih signala', 'warning');
            return;
        }

        const showSignals = document.getElementById('showSignals');
        const showDirections = document.getElementById('showDirections');
        const showBoundingBoxes = document.getElementById('showBoundingBoxes');
        const showSignalLabels = document.getElementById('showSignalLabels');
        const showHeatmap = document.getElementById('showHeatmap');
        
        // Dobavi filter informacije
        const filterType = document.getElementById('filterType');
        const filterValue = document.getElementById('filterValue');

        try {
            this.showMessage('Generiše se vizuelizacija...', 'info');
            
            const response = await fetch('/api/visualize', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    signals: selectedSignals,
                    show_signals: showSignals ? showSignals.checked : true,
                    show_grid: false,
                    show_directions: showDirections ? showDirections.checked : true,
                    show_bounding_boxes: showBoundingBoxes ? showBoundingBoxes.checked : true,
                    show_bounding_box_labels: showBoundingBoxes ? showBoundingBoxes.checked : true,
                    show_signal_labels: showSignalLabels ? showSignalLabels.checked : true,
                    show_heatmap: showHeatmap ? showHeatmap.checked : true,
                    filter_type: filterType ? filterType.value : null,
                    filter_value: filterValue ? parseInt(filterValue.value) : null
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            
            if (data.success && data.image_path) {
                this.renderImage(data.image_path);
                this.showMessage(`Vizuelizovano ${data.signals_visualized} signala`, 'success');
            } else {
                throw new Error(data.error || 'Nepoznata greška');
            }

        } catch (error) {
            console.error('Visualization error:', error);
            this.showMessage(`Greška: ${error.message}`, 'error');
        }
    }

    onCircuitFileSelected() {
        const fileInput = document.getElementById('circuitFile');
        if (fileInput.files.length > 0) {
            console.log('🔌 Izabrano kolo:', fileInput.files[0].name);
            // Automatski pokreni upload
            this.uploadCircuit();
        }
    }

    async createDemo() {
        if (this.uploadInProgress) {
            this.showMessage('Upload je u toku, sačekajte...', 'info');
            return;
        }

        this.showMessage('Kreiram demo podatke...', 'info');
        
        try {
            const response = await fetch('/demo');
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            const data = await response.json();
            
            if (data.success) {
                this.showMessage('Demo podaci uspešno kreirani!', 'success');
                this.currentArchitecture = data.architecture;
                this.currentCircuit = data.circuit;
                this.currentRouting = data.routing;
                this.updateStatus();
            } else {
                this.showMessage(data.error, 'error');
            }
        } catch (error) {
            console.error('Greška:', error);
            this.showMessage('Greška: ' + error.message, 'error');
        }
    }

    async uploadArchitecture() {
        if (this.uploadInProgress) {
            this.showMessage('Upload je u toku, sačekajte...', 'info');
            return;
        }

        const fileInput = document.getElementById('archFile');
        if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
            this.showMessage('Molimo odaberite XML fajl', 'error');
            return;
        }

        const file = fileInput.files[0];
        
        // Proveri tip fajla
        if (!file.name.toLowerCase().endsWith('.xml')) {
            this.showMessage('Podržani format: .xml', 'error');
            this.resetFileInput('archFile');
            return;
        }

        this.uploadInProgress = true;
        this.showMessage('Učitavam arhitekturu...', 'info');

        const formData = new FormData();
        formData.append('file', file);

        try {
            console.log('📤 Šaljem arhitekturu:', file.name);
            
            const response = await fetch('/upload/architecture', {
                method: 'POST',
                body: formData
            });
            
            console.log('📥 Status:', response.status);
            
            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`Server error: ${response.status}`);
            }
            
            const data = await response.json();
            console.log('📊 Odgovor:', data);
            
            if (data.success) {
                this.showMessage('Arhitektura uspešno učitana!', 'success');
                this.currentArchitecture = data.architecture || { loaded: true };
                
                // Dodaj u istoriju
                this.addToArchitectureHistory(file.name);
                
                this.updateStatus();
            } else {
                this.showMessage(data.error, 'error');
            }
            
        } catch (error) {
            console.error('💥 Greška:', error);
            this.showMessage('💥 Greška: ' + error.message, 'error');
        } finally {
            this.uploadInProgress = false;
            // NE resetuj file input ovde - ostavi ga za korisnika da vidi šta je izabrao
        }
    }

    async uploadRouting() { 
        if (this.uploadInProgress) {
            this.showMessage('⏳ Upload je u toku, sačekajte...', 'info');
            return;
        }

        const fileInput = document.getElementById('routingFile');
        if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
            this.showMessage('📁 Molimo odaberite .route fajl', 'error');
            return;
        }

        const file = fileInput.files[0];
        if (!file.name.toLowerCase().endsWith('.route')) {
            this.showMessage('❌ Podržani format: .route', 'error');
            this.resetFileInput('routingFile');
            return;
        }

        if (!this.currentArchitecture) {
            this.showMessage('❌ Prvo učitajte arhitekturu (.xml) pre rutiranja', 'error');
            return;
        }

        this.uploadInProgress = true;
        this.showMessage('🔄 Učitavam rutiranje...', 'info');

        const formData = new FormData();
        formData.append('file', file);

        try {
            console.log('📤 Šaljem routing:', file.name);
            const response = await fetch('/upload/routing', {
                method: 'POST',
                body: formData
            });

            console.log('📥 Status:', response.status);
            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`Server error: ${response.status}`);
            }

            const data = await response.json();
            console.log('📊 Odgovor:', data);

            if (data.success) {
                this.showMessage('✅ Rutiranje uspešno učitano!', 'success');
                this.currentRouting = data.routing;
                this.updateStatus();
            } else {
                this.showMessage('❌ ' + data.error, 'error');
            }
        } catch (error) {
            console.error('💥 Greška:', error);
            this.showMessage('💥 Greška: ' + error.message, 'error');
        } finally {
            this.uploadInProgress = false;
        }
    }

    async uploadCircuit() {
        if (this.uploadInProgress) {
            this.showMessage('⏳ Upload je u toku, sačekajte...', 'info');
            return;
        }

        const fileInput = document.getElementById('circuitFile');
        if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
            this.showMessage('📁 Molimo odaberite Verilog ili BLIF fajl', 'error');
            return;
        }

        const file = fileInput.files[0];
        
        // Proveri tip fajla
        const fileName = file.name.toLowerCase();
        if (!fileName.endsWith('.v') && !fileName.endsWith('.blif')) {
            this.showMessage('❌ Podržani formati: .v (Verilog) ili .blif', 'error');
            this.resetFileInput('circuitFile');
            return;
        }

        this.uploadInProgress = true;
        this.showMessage('🔄 Učitavam kolo...', 'info');

        const formData = new FormData();
        formData.append('file', file);

        try {
            console.log('📤 Šaljem kolo:', file.name);
            
            const response = await fetch('/upload/circuit', {
                method: 'POST',
                body: formData
            });
            
            console.log('📥 Status:', response.status);
            
            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`Server error: ${response.status}`);
            }
            
            const data = await response.json();
            console.log('📊 Odgovor:', data);
            
            if (data.success) {
                this.showMessage('✅ Kolo uspešno učitano!', 'success');
                this.currentCircuit = data.circuit;
                this.updateStatus();
            } else {
                this.showMessage('❌ ' + data.error, 'error');
            }
            
        } catch (error) {
            console.error('💥 Greška:', error);
            this.showMessage('💥 Greška: ' + error.message, 'error');
        } finally {
            this.uploadInProgress = false;
            // NE resetuj file input ovde
        }
    }

    resetFileInput(inputId) {
        const fileInput = document.getElementById(inputId);
        if (fileInput) {
            fileInput.value = '';
            console.log(`🔄 Resetovan file input: ${inputId}`);
        }
    }

    async visualizeSignals() {
        this.visualizeSelectedSignals();
    }

    setAreaMessage(text, color = '#333') {
        if (!this.area) return;
        this.area.innerHTML = `<p class="small center" style="padding:40px;color:${color}">${text}</p>`;
    }

    async analyzeConflicts() {
        console.log('🔍 analyzeConflicts() pozvana');
        
        // Proveri da li je učitan routing ili circuit
        if (!this.currentRouting && !this.currentCircuit) {
            console.log('❌ Nema učitanog routing-a ili circuit-a');
            this.showMessage('Prvo učitajte rutiranje (.route fajl)', 'error');
            return;
        }

        // Prikupi selektovane signale
        const selectedSignals = this.getSelectedSignals();
        console.log(`📋 Selektovano signala: ${selectedSignals.length}`, selectedSignals);
        
        if (selectedSignals.length === 0) {
            this.showMessage('Molimo selektujte bar jedan signal', 'error');
            return;
        }

        this.showMessage(`Analiziram konflikte za ${selectedSignals.length} signala...`, 'info');

        try {
            console.log('📤 Šaljem POST zahtev na /analysis/conflicts');
            const response = await fetch('/analysis/conflicts', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    selected_signals: selectedSignals
                })
            });
            
            console.log(`📥 Response status: ${response.status}`);
            
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            const data = await response.json();
            console.log('📊 Response data:', data);
            
            if (data.success) {
                this.showMessage(`Analiza konflikata završena za ${data.num_signals || selectedSignals.length} signala!`, 'success');
                this.displayConflictResults(data);
            } else {
                this.showMessage(data.error, 'error');
            }
        } catch (error) {
            console.error('💥 Greška:', error);
            this.showMessage('Greška: ' + error.message, 'error');
        }
    }

    async showStatistics() {
        if (!this.currentCircuit || !this.currentArchitecture) {
            this.showMessage('Prvo učitajte kolo i arhitekturu', 'error');
            return;
        }

        this.showMessage('Računam statistiku...', 'info');

        try {
            const response = await fetch('/analysis/statistics');
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            const data = await response.json();
            
            if (data.success) {
                this.showMessage('✅ Statistika uspešno izračunata!', 'success');
                this.displayStatistics(data.statistics);
            } else {
                this.showMessage('❌ ' + data.error, 'error');
            }
        } catch (error) {
            console.error('💥 Greška:', error);
            this.showMessage('💥 Greška: ' + error.message, 'error');
        }
    }

    renderImage(filename) {
        const vizArea = document.getElementById('visualizationArea');
        if (!vizArea) {
            console.error('❌ Visualization area ne postoji!');
            return;
        }

        // ✅ Samo ime fajla (bez putanje)
        const safe = filename.replace(/^static\/output\//, '').replace(/\\/g, '/');
        const url = `/download/${encodeURIComponent(safe)}`;
        const bust = `?t=${Date.now()}`;

        console.log(`🖼️ Učitavam sliku: ${url}${bust}`);  // DEBUG

        vizArea.innerHTML = `
            <div class="results-section">
                <h3>👁️ Vizuelizacija Signala</h3>
                <div class="image-container">
                    <img id="visualizationImage"
                        src="${url}${bust}"
                        alt="Signal Visualization"
                        class="visualization-image"
                        onload="console.log('✅ Slika učitana!');"
                        onerror="console.error('❌ Greška pri učitavanju slike:', this.src); this.onerror=null;">
                </div>
                <div class="image-actions">
                    <a href="${url}" download class="download-link">Preuzmi sliku</a>
                    <button onclick="window.open('${url}', '_blank')" class="view-link">Otvori u novom prozoru</button>
                </div>
            </div>
        `;
    }

    displayConflictResults(data) {
        const resultsDiv = document.getElementById('conflictResults');
        if (!resultsDiv) return;
        
        const hubs = data.hubs && data.hubs.length > 0 ? data.hubs.join(', ') : 'Nema habova';
        const metrics = data.metrics || {};
        
        let metricsHtml = '';
        for (const [key, value] of Object.entries(metrics)) {
            metricsHtml += `<li><strong>${key}:</strong> ${typeof value === 'number' ? value.toFixed(3) : value}</li>`;
        }
        
        let conflictVizHtml = '';
        if (data.conflict_viz_path) {
            const conflictFilename = this.normalizeImagePath(data.conflict_viz_path);
            const bust = `?t=${Date.now()}`;
            conflictVizHtml = `
                <div class="result-item">
                    <h4>Konflikt Graf:</h4>
                    <div class="visualization-container">
                        <div class="image-container">
                            <img src="/download/${conflictFilename}${bust}" 
                                 alt="Conflict Graph" 
                                 class="visualization-image"
                                 onload="console.log('Konflikt graf učitan!');"
                                 onerror="this.onerror=null; console.error('Greška pri učitavanju konflikt grafa');">
                        </div>
                        <div class="image-actions">
                            <a href="/download/${conflictFilename}" download class="download-link">Preuzmi sliku</a>
                            <button onclick="window.open('/download/${conflictFilename}', '_blank')" class="view-link">Otvori u novom prozoru</button>
                        </div>
                    </div>
                </div>
            `;
        }
        
        resultsDiv.innerHTML = `
            <div class="results-section">
                <h3>Rezultati Analize Konflikata</h3>
                ${conflictVizHtml}
                <div class="result-item">
                    <h4>Habovi:</h4>
                    <div class="hubs-list">${hubs}</div>
                </div>
                <div class="result-item">
                    <h4>Metrike:</h4>
                    <ul class="metrics-list">${metricsHtml}</ul>
                </div>
            </div>
        `;
        
        // Scroll do rezultata
        resultsDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    displayStatistics(stats) {
        const statsDiv = document.getElementById('statisticsResults');
        if (!statsDiv) return;
        
        let statsHtml = '';
        for (const [key, value] of Object.entries(stats)) {
            const displayValue = typeof value === 'number' ? value.toFixed(3) : value;
            statsHtml += `
                <tr>
                    <td>${key}</td>
                    <td>${displayValue}</td>
                </tr>
            `;
        }
        
        statsDiv.innerHTML = `
            <div class="results-section">
                <h3>📊 Statistička Analiza</h3>
                <div class="table-container">
                    <table class="stats-table">
                        <thead>
                            <tr>
                                <th>Metrika</th>
                                <th>Vrednost</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${statsHtml}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }

    normalizeImagePath(fullPath) {
        if (!fullPath) return '';
        let normalized = fullPath.replace(/\\/g, '/');
        normalized = normalized.replace(/^output\//, '').replace(/^\.\//, '');
        return normalized;
    }

    updateStatus() {
        console.log('🔄 Status aplikacije:', {
            'Arhitektura': this.currentArchitecture ? '✅ Učitana' : '❌ Nije učitana',
            'Kolo': this.currentCircuit ? '✅ Učitano' : '❌ Nije učitano',
            'Rutiranje': this.currentRouting ? '✅ Učitano' : '❌ Nije učitano'
        });
    }

    showMessage(message, type) {
        console.log(`[${type.toUpperCase()}] ${message}`);
        
        const existingMessages = document.querySelectorAll('.status-message');
        existingMessages.forEach(msg => msg.remove());
        
        const messageDiv = document.createElement('div');
        messageDiv.className = `status-message ${type}`;
        messageDiv.textContent = message;
        messageDiv.style.cssText = `
            padding: 12px;
            margin: 10px 0;
            border-radius: 4px;
            border: 1px solid;
            font-weight: bold;
        `;
        
        if (type === 'success') {
            messageDiv.style.backgroundColor = '#d4edda';
            messageDiv.style.color = '#155724';
            messageDiv.style.borderColor = '#c3e6cb';
        } else if (type === 'error') {
            messageDiv.style.backgroundColor = '#f8d7da';
            messageDiv.style.color = '#721c24';
            messageDiv.style.borderColor = '#f5c6cb';
        } else if (type === 'info') {
            messageDiv.style.backgroundColor = '#d1ecf1';
            messageDiv.style.color = '#0c5460';
            messageDiv.style.borderColor = '#bee5eb';
        }
        
        const container = document.querySelector('.container');
        if (container) {
            const mainContent = document.querySelector('.main-content');
            if (mainContent) {
                container.insertBefore(messageDiv, mainContent);
            } else {
                container.appendChild(messageDiv);
            }
        }
        
        setTimeout(() => {
            if (messageDiv.parentNode) {
                messageDiv.parentNode.removeChild(messageDiv);
            }
        }, 5000);
    }
}

// Inicijalizacija kada se stranica učita
document.addEventListener('DOMContentLoaded', () => {
    console.log("🚀 FPGA Visualizer se pokreće...");
    window.fpgaViz = new FPGAVisualizer();
    console.log("✅ FPGA Visualizer je spreman!");
});