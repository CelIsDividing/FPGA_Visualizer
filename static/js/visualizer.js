// FPGA Visualizer - JavaScript client code

class FPGAVisualizer {
    constructor() {
        this.currentArchitecture = null;
        this.currentCircuit = null;
        this.currentRouting = null;
        this.uploadInProgress = false;
        this.area = document.getElementById('visualizationArea');
        this.btnVisualize = document.getElementById('visualizeBtn');
        this.chkGrid = document.getElementById('showGrid');
        
        // History of loaded files
        this.architectureHistory = [];
        this.routingHistory = [];
        
        console.log("🔧 FPGA Visualizer initialized");
        this.initEventListeners();
    }

    initEventListeners() {
        console.log("🔧 Initializing event listeners...");
        
        // Manually bind all buttons
        this.bindButton('#visualizeBtn', () => this.visualizeSelectedSignals());
        this.bindButton('#analyzeBtn', () => this.analyzeConflicts());  // Fixed: analyzeBtn instead of analyzeConflictsBtn
        
        // Bind file input change events
        this.bindFileInput('archFile', () => this.onArchFileSelected());
        this.bindFileInput('circuitFile', () => this.onCircuitFileSelected());
        this.bindFileInput('routingFile', () => this.onRoutingFileSelected());

        // Bind the demo files button
        this.bindButton('#loadDemoBtn', () => this.loadDemoFiles());

        this.bindButton('#selectAllSignals', () => this.selectAllSignals());
        this.bindButton('#deselectAllSignals', () => this.deselectAllSignals());
        
        // Filter button
        this.bindButton('#applyFilterBtn', () => this.applySignalFilter());
        
        // Heat map checkbox logic
        const heatmapCheckbox = document.getElementById('showHeatmap');
        if (heatmapCheckbox) {
            heatmapCheckbox.addEventListener('change', () => this.onHeatmapToggle());
        }
        
        // Other checkboxes - if checked, uncheck the heat map
        const otherCheckboxes = ['showSignals', 'showDirections', 'showBoundingBoxes', 'showSignalLabels'];
        otherCheckboxes.forEach(id => {
            const checkbox = document.getElementById(id);
            if (checkbox) {
                checkbox.addEventListener('change', () => this.onOtherOptionToggle());
            }
        });

        console.log("✅ Event listeners initialized");
    }

    bindButton(selector, handler) {
        const button = document.querySelector(selector);
        if (button) {
            button.addEventListener('click', () => {
                console.log(`🖱️ Button clicked: ${selector}`);
                handler();
            });
            console.log(`✅ Bound button: ${selector}`);
        } else {
            console.log(`❌ Button not found: ${selector}`);
        }
    }

    bindFileInput(inputId, changeHandler) {
        const input = document.getElementById(inputId);
        if (input) {
            input.addEventListener('change', changeHandler);
            console.log(`✅ Bound file input: ${inputId}`);
        }
    }

    onArchFileSelected() {
        const fileInput = document.getElementById('archFile');
        if (fileInput.files.length > 0) {
            console.log('🏗️ Selected architecture:', fileInput.files[0].name);
            // Automatically start upload
            this.uploadArchitecture();
        }
    }

    onRoutingFileSelected() { 
        const fileInput = document.getElementById('routingFile');
        if (fileInput.files.length > 0) {
            console.log('🧭 Selected routing:', fileInput.files[0].name);
            this.uploadRoutingAndParseSignals();
        }
    }

    async uploadRoutingAndParseSignals() {
        const fileInput = document.getElementById('routingFile');
        const file = fileInput.files[0];
        if (!file) return;

        this.uploadInProgress = true;
        this.showMessage('Loading .route file...', 'info');

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
                this.showMessage(`Loaded ${this.loadedSignals.length} signals`, 'success');
                
                // Add to history
                this.addToRoutingHistory(file.name);
                
                // Set currentRouting and currentArchitecture as "loaded"
                // (required for the "Analyze Conflicts" button)
                this.currentRouting = { loaded: true };
                this.currentArchitecture = { loaded: true };
            } else {
                throw new Error(data.error || 'Unknown error');
            }

        } catch (error) {
            console.error('Error loading routing file:', error);
            this.showMessage(`Error: ${error.message}`, 'error');
        } finally {
            this.uploadInProgress = false;
        }
    }

    async loadDemoFiles() {
        if (this.uploadInProgress) {
            this.showMessage('Upload in progress, please wait...', 'info');
            return;
        }

        this.uploadInProgress = true;
        this.showMessage('Loading demo files (rrg.xml, b9.route)...', 'info');

        try {
            const response = await fetch('/demo/load', {
                method: 'POST'
            });

            const data = await response.json();

            if (!response.ok || !data.success) {
                throw new Error(data.error || `HTTP ${response.status}`);
            }

            this.loadedSignals = data.signals || [];
            this.populateSignalsList(this.loadedSignals);

            // Add to history
            this.addToArchitectureHistory(data.architecture_filename || 'rrg.xml');
            this.addToRoutingHistory(data.routing_filename || 'b9.route');

            // Set currentRouting and currentArchitecture as "loaded"
            // (required for the "Analyze Conflicts" button)
            this.currentRouting = { loaded: true };
            this.currentArchitecture = { loaded: true };

            this.showMessage(`Demo loaded: ${this.loadedSignals.length} signals`, 'success');
        } catch (error) {
            console.error('Error loading demo files:', error);
            this.showMessage(`Error: ${error.message}`, 'error');
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
            info.textContent = `${signal.segment_count || signal.fanout || '?'} nodes`;
            
            
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
        const timestamp = new Date().toLocaleString('en-US', {
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
        const timestamp = new Date().toLocaleString('en-US', {
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
        // Update the architecture list
        const archList = document.getElementById('archHistoryList');
        if (archList) {
            if (this.architectureHistory.length === 0) {
                archList.innerHTML = '<li class="history-empty">No files loaded</li>';
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
        
        // Update the routing list
        const routeList = document.getElementById('routeHistoryList');
        if (routeList) {
            if (this.routingHistory.length === 0) {
                routeList.innerHTML = '<li class="history-empty">No files loaded</li>';
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
            // Check all signals
            allCheckboxes.forEach(cb => cb.checked = true);
            this.showMessage('All signals selected', 'success');
            return;
        }
        
        // First uncheck all
        allCheckboxes.forEach(cb => cb.checked = false);
        
        if (filterType === 'first') {
            // Check the first N signals
            const toCheck = allCheckboxes.slice(0, filterValue);
            toCheck.forEach(cb => cb.checked = true);
            const unchecked = totalSignals - toCheck.length;
            this.showMessage(`Selected first ${toCheck.length} signals (${unchecked} unchecked)`, 'success');
        }
        else if (filterType === 'last') {
            // Check the last N signals
            const toCheck = allCheckboxes.slice(-filterValue);
            toCheck.forEach(cb => cb.checked = true);
            const unchecked = totalSignals - toCheck.length;
            this.showMessage(`Selected last ${toCheck.length} signals (${unchecked} unchecked)`, 'success');
        }
        else if (filterType === 'less_than') {
            // Check signals with fewer than N segments
            const filtered = allCheckboxes.filter(cb => {
                const segmentCount = parseInt(cb.dataset.segmentCount) || 0;
                return segmentCount < filterValue;
            });
            filtered.forEach(cb => cb.checked = true);
            const unchecked = totalSignals - filtered.length;
            this.showMessage(`Selected ${filtered.length} signals with fewer than ${filterValue} segments (${unchecked} unchecked)`, 'success');
        }
        else if (filterType === 'more_than') {
            // Check signals with more than N segments
            const filtered = allCheckboxes.filter(cb => {
                const segmentCount = parseInt(cb.dataset.segmentCount) || 0;
                return segmentCount > filterValue;
            });
            filtered.forEach(cb => cb.checked = true);
            const unchecked = totalSignals - filtered.length;
            this.showMessage(`Selected ${filtered.length} signals with more than ${filterValue} segments (${unchecked} unchecked)`, 'success');
        }
    }

    onHeatmapToggle() {
        const heatmapCheckbox = document.getElementById('showHeatmap');
        
        if (heatmapCheckbox && heatmapCheckbox.checked) {
            // If the heat map is checked, uncheck all other options
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
        
        // If any other option is checked, uncheck the heat map
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
            this.showMessage('No signals selected', 'warning');
            return;
        }

        const showSignals = document.getElementById('showSignals');
        const showDirections = document.getElementById('showDirections');
        const showBoundingBoxes = document.getElementById('showBoundingBoxes');
        const showSignalLabels = document.getElementById('showSignalLabels');
        const showHeatmap = document.getElementById('showHeatmap');
        
        // Get filter information
        const filterType = document.getElementById('filterType');
        const filterValue = document.getElementById('filterValue');

        try {
            this.showMessage('Generating visualization...', 'info');
            
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
                this.showMessage(`Visualized ${data.signals_visualized} signals`, 'success');
            } else {
                throw new Error(data.error || 'Unknown error');
            }

        } catch (error) {
            console.error('Visualization error:', error);
            this.showMessage(`Error: ${error.message}`, 'error');
        }
    }

    onCircuitFileSelected() {
        const fileInput = document.getElementById('circuitFile');
        if (fileInput.files.length > 0) {
            console.log('🔌 Selected circuit:', fileInput.files[0].name);
            // Automatically start upload
            this.uploadCircuit();
        }
    }

    async uploadArchitecture() {
        if (this.uploadInProgress) {
            this.showMessage('Upload in progress, please wait...', 'info');
            return;
        }

        const fileInput = document.getElementById('archFile');
        if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
            this.showMessage('Please select an XML file', 'error');
            return;
        }

        const file = fileInput.files[0];
        
        // Check file type
        if (!file.name.toLowerCase().endsWith('.xml')) {
            this.showMessage('Supported format: .xml', 'error');
            this.resetFileInput('archFile');
            return;
        }

        this.uploadInProgress = true;
        this.showMessage('Loading architecture...', 'info');

        const formData = new FormData();
        formData.append('file', file);

        try {
            console.log('📤 Sending architecture:', file.name);
            
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
            console.log('📊 Response:', data);
            
            if (data.success) {
                this.showMessage('Architecture loaded successfully!', 'success');
                this.currentArchitecture = data.architecture || { loaded: true };
                
                // Add to history
                this.addToArchitectureHistory(file.name);
                
                this.updateStatus();
            } else {
                this.showMessage(data.error, 'error');
            }
            
        } catch (error) {
            console.error('💥 Error:', error);
            this.showMessage('💥 Error: ' + error.message, 'error');
        } finally {
            this.uploadInProgress = false;
            // DO NOT reset the file input here - leave it so the user can see what they selected
        }
    }

    resetFileInput(inputId) {
        const fileInput = document.getElementById(inputId);
        if (fileInput) {
            fileInput.value = '';
            console.log(`🔄 Reset file input: ${inputId}`);
        }
    }

    async analyzeConflicts() {
        if (!this.currentRouting && !this.currentCircuit) {
            this.showMessage('Load the routing first (.route file)', 'error');
            return;
        }

        const selectedSignals = this.getSelectedSignals();
        
        if (selectedSignals.length === 0) {
            this.showMessage('Please select at least one signal', 'error');
            return;
        }

        this.showMessage(`Analyzing conflicts for ${selectedSignals.length} signals...`, 'info');

        try {
            const response = await fetch('/analysis/conflicts', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    selected_signals: selectedSignals
                })
            });
            
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            const data = await response.json();
            
            if (data.success) {
                this.showMessage(`Conflict analysis completed for ${data.num_signals || selectedSignals.length} signals!`, 'success');
                this.displayConflictResults(data);
            } else {
                this.showMessage(data.error, 'error');
            }
        } catch (error) {
            console.error('Error:', error);
            this.showMessage('Error: ' + error.message, 'error');
        }
    }

    renderImage(filename) {
        const vizArea = document.getElementById('visualizationArea');
        if (!vizArea) {
            console.error('❌ Visualization area does not exist!');
            return;
        }

        // ✅ File name only (without path)
        const safe = filename.replace(/^static\/output\//, '').replace(/\\/g, '/');
        const url = `/download/${encodeURIComponent(safe)}`;
        const bust = `?t=${Date.now()}`;

        console.log(`🖼️ Loading image: ${url}${bust}`);  // DEBUG

        vizArea.innerHTML = `
            <div class="results-section">
                <h3>👁️ Signal Visualization</h3>
                <div class="image-container">
                    <img id="visualizationImage"
                        src="${url}${bust}"
                        alt="Signal Visualization"
                        class="visualization-image"
                        onload="console.log('✅ Image loaded!');"
                        onerror="console.error('❌ Error loading image:', this.src); this.onerror=null;">
                </div>
                <div class="image-actions">
                    <a href="${url}" download class="download-link">Download image</a>
                    <button onclick="window.open('${url}', '_blank')" class="view-link">Open in new window</button>
                </div>
            </div>
        `;
    }

    displayConflictResults(data) {
        const resultsDiv = document.getElementById('conflictResults');
        if (!resultsDiv) return;
        
        const hubs = data.hubs && data.hubs.length > 0 ? data.hubs.join(', ') : 'No hubs';
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
                    <h4>Conflict Graph:</h4>
                    <div class="visualization-container">
                        <div class="image-container">
                            <img src="/download/${conflictFilename}${bust}" 
                                 alt="Conflict Graph" 
                                 class="visualization-image">
                        </div>
                        <div class="image-actions">
                            <a href="/download/${conflictFilename}" download class="download-link">Download image</a>
                            <button onclick="window.open('/download/${conflictFilename}', '_blank')" class="view-link">Open in new window</button>
                        </div>
                    </div>
                </div>
            `;
        }
        
        resultsDiv.innerHTML = `
            <div class="results-section">
                <h3>Conflict Analysis Results</h3>
                ${conflictVizHtml}
                <div class="result-item">
                    <h4>Hubs:</h4>
                    <div class="hubs-list">${hubs}</div>
                </div>
                <div class="result-item">
                    <h4>Metrics:</h4>
                    <ul class="metrics-list">${metricsHtml}</ul>
                </div>
            </div>
        `;
        
        resultsDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    normalizeImagePath(fullPath) {
        if (!fullPath) return '';
        let normalized = fullPath.replace(/\\/g, '/');
        normalized = normalized.replace(/^output\//, '').replace(/^\.\//, '');
        return normalized;
    }

    updateStatus() {
        // Status info
    }

    showMessage(message, type) {
        
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

// Initialization when the page loads
document.addEventListener('DOMContentLoaded', () => {
    console.log("🚀 FPGA Visualizer is starting...");
    window.fpgaViz = new FPGAVisualizer();
    console.log("✅ FPGA Visualizer is ready!");
});