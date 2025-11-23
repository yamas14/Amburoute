mapboxgl.accessToken = 'pk.eyJ1Ijoic2F0cmFqaXRoIiwiYSI6ImNtZjVpMTRlaTA1ZTIya3M4bjZjb2U5Z2cifQ.7GFkmIE8LP75DkaSzm8UVA';

const API_BASE_URL = 'http://localhost:8001';
const AMBULANCE_START_LOCATION = [12.9716, 77.5946]; // Fixed start for demo
// Per-route traffic factors for the current simulation run
let trafficFactors = {}; // { [hospitalId]: factor }

function renderHospitalList() {
    const listEl = document.getElementById('hospital-list');
    if (!listEl) return;
    listEl.innerHTML = '';
    hospitals.forEach((h) => {
        const { dx, dy } = getJitterOffset(h.id);
        const li = document.createElement('div');
        li.style.padding = '4px 6px';
        li.style.cursor = 'pointer';
        li.style.borderBottom = '1px solid #eee';
        li.textContent = `${h.id}. ${h.name}  (${h.latitude.toFixed(5)}, ${h.longitude.toFixed(5)})`;
        li.onclick = () => {
            map.flyTo({ center: [h.longitude + dx, h.latitude + dy], zoom: 13, duration: 700 });
        };
        listEl.appendChild(li);
    });
}

// Compute a radial jitter offset in degrees to separate overlapping markers
function getJitterOffset(id, base = 0.0006) { // ~60m
    const degToRad = Math.PI / 180;
    const angleDeg = (id * 137.508) % 360; // golden-angle based distribution
    const angle = angleDeg * degToRad;
    const ring = (id % 4) + 1; // 1..4 rings
    const radius = base * (ring / 4); // 0.00015 .. 0.0006
    const dx = Math.cos(angle) * radius; // lng offset
    const dy = Math.sin(angle) * radius; // lat offset
    return { dx, dy };
}

const map = new mapboxgl.Map({
    container: 'map',
    style: 'mapbox://styles/mapbox/streets-v12',
    center: AMBULANCE_START_LOCATION.slice().reverse(),
    zoom: 11
});

let hospitals = [];
let hospitalMarkers = [];
let signalMarkers = []; // For traffic signals
let ambulanceMarker = null;
let animationFrameId = null;

// Returns a stable random traffic factor per hospital for this run
function getTrafficFactorFor(hospitalId) {
    if (!trafficFactors[hospitalId]) {
        // 0.6x to 1.8x to increase variability between runs and routes
        trafficFactors[hospitalId] = 0.6 + Math.random() * 1.2;
    }
    return trafficFactors[hospitalId];
}

// --- Data Fetching and Simulation ---
async function startSimulation() {
    console.log('Starting simulation...');
    try {
        // 0. Reset traffic factors so each run gets fresh, per-route traffic
        trafficFactors = {};

        // 1. Simulate bed updates
        const response = await fetch(`${API_BASE_URL}/hospitals/simulate-updates`, { method: 'POST' });
        if (!response.ok) throw new Error('Failed to simulate bed updates');
        hospitals = await response.json();
        // Update hospital count in dashboard
        const cntEl = document.getElementById('hospital-count');
        if (cntEl) cntEl.textContent = hospitals.length;

        // 2. Clear old markers and routes
        clearMap();
        displayHospitals();
        fitMapToHospitals();
        renderHospitalList();

        // 3. Get AI recommendation (but don't block if it fails)
        let bestHospital = null;
        try {
            const aiResponse = await fetch(`${API_BASE_URL}/route/drl`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ambulance_location: AMBULANCE_START_LOCATION })
            });
            if (aiResponse.ok) {
                const aiData = await aiResponse.json();
                bestHospital = aiData.hospital || null;
            } else {
                console.warn('AI route/drl not available, falling back to client-side selection');
            }
        } catch (e) {
            console.warn('AI route/drl failed, continuing with client-side selection:', e);
        }

        // 4. Display all routes (which includes generating traffic)
        //    Determine best route based on current random trafficMultiplier so
        //    hospital choice and ETA can change each run.
        const { selectedHospital, selectedRoute, selectedRouteAdjustedDuration, selectedTrafficFactor } = await displayAllRoutes(bestHospital);
        // 4b. Update dashboard using adjusted duration
        updateDashboard(selectedHospital, { ...selectedRoute, duration: selectedRouteAdjustedDuration });

        // 5. Place signals and start animation (speed scaled by traffic)
        placeTrafficSignals(selectedRoute.geometry.coordinates);
        const baseMs = Math.max(12000, Math.min(40000, (selectedRoute.duration || 900) * 1000));
        const travelMs = baseMs * selectedTrafficFactor; // slower when factor > 1
        animateAmbulance(selectedRoute.geometry.coordinates, travelMs);

    } catch (error) {
        console.error('Simulation Error:', error);
        alert(`Simulation failed: ${error.message}`);
    }
}

// --- Map Display Functions ---
function displayHospitals() {
    // 1) Add HTML markers for interactivity
    hospitals.forEach(hospital => {
        const el = document.createElement('div');
        el.className = 'marker';
        const color = hospital.available_beds > 0 ? '#007bff' : '#6c757d';
        el.style.backgroundColor = color;
        el.style.width = '16px';
        el.style.height = '16px';
        el.style.borderRadius = '50%';
        el.style.border = '2px solid #fff';
        el.style.opacity = '0.95';
        el.style.boxShadow = '0 0 6px rgba(0,0,0,0.35)';

        // Jitter markers using radial offset to avoid exact overlap
        const { dx, dy } = getJitterOffset(hospital.id);
        const marker = new mapboxgl.Marker(el)
            .setLngLat([hospital.longitude + dx, hospital.latitude + dy])
            .setPopup(new mapboxgl.Popup().setHTML(`<strong>${hospital.name}</strong><br>Beds: ${hospital.available_beds}`))
            .addTo(map);
        hospitalMarkers.push(marker);
    });
    console.log(`Plotted markers: ${hospitalMarkers.length}`);

    // 2) Also add a GeoJSON circle layer to ensure all points are visibly rendered
    const features = hospitals.map(h => {
        const { dx, dy } = getJitterOffset(h.id);
        return {
            type: 'Feature',
            properties: {
                id: h.id,
                name: h.name,
                beds: h.available_beds || 0
            },
            geometry: {
                type: 'Point',
                coordinates: [h.longitude + dx, h.latitude + dy]
            }
        };
    });
    const fc = { type: 'FeatureCollection', features };

    if (map.getSource('hospitals-points')) {
        map.getSource('hospitals-points').setData(fc);
    } else {
        map.addSource('hospitals-points', { type: 'geojson', data: fc });
        map.addLayer({
            id: 'hospitals-points',
            type: 'circle',
            source: 'hospitals-points',
            paint: {
                'circle-radius': 5,
                'circle-color': [
                    'case',
                    ['>', ['get', 'beds'], 0], '#1E90FF', // blue if beds
                    '#6c757d' // gray otherwise
                ],
                'circle-stroke-width': 1.5,
                'circle-stroke-color': '#ffffff'
            }
        });
    }
}

function fitMapToHospitals() {
    if (!hospitals || hospitals.length === 0) return;
    const bounds = new mapboxgl.LngLatBounds();
    hospitals.forEach(h => {
        const { dx, dy } = getJitterOffset(h.id);
        bounds.extend([h.longitude + dx, h.latitude + dy]);
    });
    try {
        map.fitBounds(bounds, { padding: 80, duration: 800 });
    } catch (e) {
        console.warn('fitBounds failed:', e);
    }
}

async function displayAllRoutes(bestHospital) {
    const routePromises = hospitals.map(hospital => 
        fetch(`${API_BASE_URL}/route`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ start_coords: AMBULANCE_START_LOCATION, end_coords: [hospital.latitude, hospital.longitude] })
        }).then(res => res.json()).then(route => ({...route, hospitalId: hospital.id}))
    );

    let allRoutes = [];
    try {
        allRoutes = await Promise.all(routePromises);
    } catch (e) {
        console.warn('Some route requests failed:', e);
    }
    // Filter out any routes missing geometry
    allRoutes = allRoutes.filter(r => r && r.geometry && r.geometry.coordinates && r.geometry.coordinates.length > 1);

    if (allRoutes.length === 0) {
        alert('No routes available from the API. Please try again.');
        return { selectedHospital: bestHospital || hospitals[0], selectedRoute: null, selectedRouteAdjustedDuration: null, selectedTrafficFactor: 1.0 };
    }

    // Use real traffic data if available, otherwise fallback to simulated traffic
    const withAdjusted = allRoutes.map(r => {
        let trafficFactor = 1.0;
        if (r.traffic_data && r.traffic_data.traffic_factor) {
            // Use real traffic factor from Mapbox
            trafficFactor = r.traffic_data.traffic_factor;
            console.log(`Hospital ${r.hospitalId}: Real traffic factor ${trafficFactor.toFixed(2)}x`);
        } else {
            // Fallback to simulated traffic factor
            trafficFactor = getTrafficFactorFor(r.hospitalId);
            console.log(`Hospital ${r.hospitalId}: Simulated traffic factor ${trafficFactor.toFixed(2)}x`);
        }
        return {
            ...r,
            trafficFactor: trafficFactor,
            adjustedDuration: (r.duration || r.duration_typical || 900) * trafficFactor
        };
    });

    // Pick the best route by adjusted duration (ignoring DRL pick if traffic is heavy)
    withAdjusted.sort((a, b) => a.adjustedDuration - b.adjustedDuration);
    const bestRoute = withAdjusted[0];
    const otherRoutes = withAdjusted.slice(1);
    
    console.log(`Best route: Hospital ${bestRoute.hospitalId}, Traffic: ${bestRoute.trafficFactor.toFixed(2)}x, Duration: ${(bestRoute.adjustedDuration/60).toFixed(1)} min`);

    // Generate traffic from the non-optimal routes (visual only)
    generateLineTraffic(otherRoutes.map(r => ({ geometry: r.geometry, trafficFactor: r.trafficFactor })));

    // Draw the non-optimal routes in red
    otherRoutes.forEach(route => {
        drawRoute(route.geometry, 'red', `route-red-${route.hospitalId}`);
    });

    // Draw the optimal route in green on top
    drawRoute(bestRoute.geometry, 'green', 'route-green');

    // Return the selected hospital and route so caller can update UI and animation
    const selectedHospital = hospitals.find(h => h.id === bestRoute.hospitalId) || bestHospital || hospitals[0];
    return { selectedHospital, selectedRoute: bestRoute, selectedRouteAdjustedDuration: bestRoute.adjustedDuration, selectedTrafficFactor: bestRoute.trafficFactor };
}

function drawRoute(geometry, color, id) {
    const isGreenRoute = color === 'green';

    if (map.getSource(id)) {
        map.getSource(id).setData(geometry);
    } else {
        map.addSource(id, { type: 'geojson', data: geometry });
        map.addLayer({
            id: id,
            type: 'line',
            source: id,
            paint: {
                'line-color': color,
                'line-width': isGreenRoute ? 6 : 3,
                'line-opacity': isGreenRoute ? 0.9 : 0.5
            }
        });
    }

    // If this is the main green route, also set up the 'traveled' route layer
    if (isGreenRoute) {
        const emptyGeoJSON = { type: 'FeatureCollection', features: [] };
        if (!map.getSource('route-traveled')) {
            map.addSource('route-traveled', { type: 'geojson', data: emptyGeoJSON });
            map.addLayer({
                id: 'route-traveled',
                type: 'line',
                source: 'route-traveled',
                paint: {
                    'line-color': '#343a40', // Dark gray for traveled path
                    'line-width': 6,
                    'line-opacity': 0.9
                }
            });
        } else {
            map.getSource('route-traveled').setData(emptyGeoJSON);
        }
    }
}

function animateAmbulance(routeCoordinates, durationMs = 15000) {
    if (!ambulanceMarker) {
        console.error('Ambulance marker not initialized!');
        return;
    }
    
    let startTime = null;
    const duration = durationMs; // scaled by traffic
    const routeLine = turf.lineString(routeCoordinates);
    const totalDistance = turf.length(routeLine);
    
    console.log(`Starting ambulance animation: ${routeCoordinates.length} points, ${durationMs}ms`);

    const frame = (timestamp) => {
        if (!startTime) startTime = timestamp;
        const progress = Math.min((timestamp - startTime) / duration, 1);

        const traveledDistance = progress * totalDistance;
        const currentPoint = turf.along(routeLine, traveledDistance);

        // Update ambulance marker position
        ambulanceMarker.setLngLat(currentPoint.geometry.coordinates);

        // Update traveled and remaining route segments
        const traveledLine = turf.lineSlice(turf.point(routeCoordinates[0]), currentPoint, routeLine);
        const remainingLine = turf.lineSlice(currentPoint, turf.point(routeCoordinates[routeCoordinates.length - 1]), routeLine);

        map.getSource('route-traveled').setData(traveledLine.geometry);
        map.getSource('route-green').setData(remainingLine.geometry);

        // Check for signal changes
        updateTrafficSignals(currentPoint);

        if (progress < 1) {
            animationFrameId = requestAnimationFrame(frame);
        } else {
            // Ensure the final state is perfect
            map.getSource('route-traveled').setData(routeLine.geometry);
            map.getSource('route-green').setData({ type: 'FeatureCollection', features: [] });
        }
    };
    animationFrameId = requestAnimationFrame(frame);
}

function updateTrafficSignals(ambulancePoint) {
    signalMarkers.forEach(signal => {
        const distanceToSignal = turf.distance(ambulancePoint, turf.point(signal.coords), { units: 'meters' });
        
        // If ambulance is approaching a red signal, turn it green
        if (distanceToSignal < 100 && signal.state === 'red') {
            signal.state = 'green';
            const el = signal.marker.getElement();
            el.style.backgroundColor = '#28a745';
            el.style.boxShadow = '0 0 12px #28a745';
        }
        // If ambulance has passed a green signal, turn it red again
        else if (distanceToSignal > 150 && signal.state === 'green') {
            const ambulanceBearing = turf.bearing(turf.point(ambulanceMarker.getLngLat().toArray()), ambulancePoint);
            const signalBearing = turf.bearing(turf.point(ambulanceMarker.getLngLat().toArray()), turf.point(signal.coords));
            // A simple check to see if the signal is now 'behind' the ambulance
            if (Math.abs(ambulanceBearing - signalBearing) > 90) {
                 signal.state = 'red';
                 const el = signal.marker.getElement();
                 el.style.backgroundColor = '#dc3545';
                 el.style.boxShadow = '0 0 8px #dc3545';
            }
        }
    });
}

function updateDashboard(hospital, route) {
    document.getElementById('hospital-name').textContent = hospital.name;
    const minutes = route && route.duration ? Math.round(route.duration / 60) : '—';
    document.getElementById('hospital-eta').textContent = `${minutes} mins`;
    document.getElementById('hospital-beds').textContent = hospital.available_beds;
    document.getElementById('hospital-icu-beds').textContent = hospital.available_icu_beds;
    
    // Display traffic information if available
    if (route && route.traffic_data) {
        const trafficFactor = route.traffic_data.traffic_factor || 1.0;
        const trafficInfo = document.getElementById('traffic-info');
        if (trafficInfo) {
            const baseMinutes = Math.round(route.traffic_data.base_duration / 60);
            const trafficMinutes = Math.round(route.traffic_data.traffic_duration / 60);
            trafficInfo.innerHTML = `
                🚦 Traffic Factor: ${trafficFactor.toFixed(2)}x<br>
                ⏱️ Base: ${baseMinutes}min → Traffic: ${trafficMinutes}min
            `;
            trafficInfo.style.display = 'block';
        }
    }
}

function generateLineTraffic(routeEntries) {
    const trafficSegments = { type: 'FeatureCollection', features: [] };
    const trafficColors = ['#28a745', '#ffc107', '#fd7e14', '#dc3545']; // Green, Yellow, Orange, Red

    routeEntries.forEach(({ geometry, trafficFactor }) => {
        const line = turf.lineString(geometry.coordinates);
        const chunks = turf.lineChunk(line, 0.2, { units: 'kilometers' });
        chunks.features.forEach(chunk => {
            // Bias color selection based on trafficFactor
            const bias = Math.min(Math.max((trafficFactor - 1.0) * 0.6, -0.3), 0.8); // map factor to bias range
            const roll = Math.random() + bias; // higher -> more congested
            let color = trafficColors[1]; // default yellow
            if (roll < 0.2) color = trafficColors[0]; // green
            else if (roll < 0.55) color = trafficColors[1]; // yellow
            else if (roll < 0.85) color = trafficColors[2]; // orange
            else color = trafficColors[3]; // red
            chunk.properties.trafficColor = color;
            trafficSegments.features.push(chunk);
        });
    });

    if (map.getSource('traffic')) {
        map.getSource('traffic').setData(trafficSegments);
    } else {
        map.addSource('traffic', { type: 'geojson', data: trafficSegments });
        map.addLayer({
            id: 'traffic',
            type: 'line',
            source: 'traffic',
            paint: {
                'line-color': ['get', 'trafficColor'],
                'line-width': 3,
                'line-opacity': 0.6
            }
        });
    }
}

function placeTrafficSignals(routeCoordinates) {
    const routeLine = turf.lineString(routeCoordinates);
    const distance = turf.length(routeLine, { units: 'kilometers' });
    const interval = 0.5; // Place a signal every 500 meters

    for (let i = interval; i < distance; i += interval) {
        const point = turf.along(routeLine, i, { units: 'kilometers' });
        const el = document.createElement('div');
        el.className = 'signal-marker';
        el.style.backgroundColor = '#dc3545'; // Red
        el.style.width = '12px';
        el.style.height = '12px';
        el.style.borderRadius = '50%';
        el.style.border = '2px solid white';
        el.style.boxShadow = '0 0 8px #dc3545';
        
        const signal = new mapboxgl.Marker(el)
            .setLngLat(point.geometry.coordinates)
            .addTo(map);
        
        signalMarkers.push({ marker: signal, coords: point.geometry.coordinates, state: 'red' });
    }
}

function clearMap() {
    // Clear markers
    hospitalMarkers.forEach(marker => marker.remove());
    hospitalMarkers = [];
    signalMarkers.forEach(signal => signal.marker.remove());
    signalMarkers = [];
    // Clear routes
    for (let i = 0; i < Math.min(50, hospitals.length + 10); i++) { // Assuming max 50 hospitals
        if (map.getLayer(`route-red-${i}`)) map.removeLayer(`route-red-${i}`);
        if (map.getSource(`route-red-${i}`)) map.removeSource(`route-red-${i}`);
    }
    if (map.getLayer('route-green')) map.removeLayer('route-green');
    if (map.getSource('route-green')) map.removeSource('route-green');
    if (map.getLayer('route-traveled')) map.removeLayer('route-traveled');
    if (map.getSource('route-traveled')) map.removeSource('route-traveled');
    // Clear hospitals circle layer
    if (map.getLayer('hospitals-points')) map.removeLayer('hospitals-points');
    if (map.getSource('hospitals-points')) map.removeSource('hospitals-points');
    // Clear simulated traffic (but keep real traffic layer)
    if (map.getLayer('traffic')) map.removeLayer('traffic');
    if (map.getSource('traffic')) map.removeSource('traffic');
    // Note: Don't remove real traffic layer (traffic-layer only)
    // Stop animation
    if (animationFrameId) cancelAnimationFrame(animationFrameId);
}

// --- Initial Load and Event Listeners ---
let trafficLayerVisible = true;

document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded, setting up event listeners...');
    
    // Set up event listeners
    const startEmergencyBtn = document.getElementById('start-emergency');
    const toggleTrafficBtn = document.getElementById('toggle-traffic');
    
    if (startEmergencyBtn) {
        startEmergencyBtn.addEventListener('click', startSimulation);
        console.log('Start emergency button listener attached');
    } else {
        console.error('Start emergency button not found!');
    }
    
    if (toggleTrafficBtn) {
        toggleTrafficBtn.addEventListener('click', () => {
            const hasTrafficLayer = map.getLayer('traffic-layer');
            
            if (hasTrafficLayer) {
                if (trafficLayerVisible) {
                    map.setLayoutProperty('traffic-layer', 'visibility', 'none');
                    toggleTrafficBtn.textContent = 'Show Traffic Layer';
                    console.log('Traffic layer hidden');
                } else {
                    map.setLayoutProperty('traffic-layer', 'visibility', 'visible');
                    toggleTrafficBtn.textContent = 'Hide Traffic Layer';
                    console.log('Traffic layer shown');
                }
                trafficLayerVisible = !trafficLayerVisible;
            } else {
                console.error('Traffic layer not found!');
                // Try to add it again
                addTrafficLayersToMap();
            }
        });
        console.log('Toggle traffic button listener attached');
    } else {
        console.error('Toggle traffic button not found!');
    }
});

function addTrafficLayersToMap() {
    if (!map.getSource('mapbox-traffic')) {
        map.addSource('mapbox-traffic', {
            type: 'vector',
            url: 'mapbox://mapbox.mapbox-traffic-v1'
        });
    }
    
    if (!map.getLayer('traffic-layer')) {
        map.addLayer({
            id: 'traffic-layer',
            type: 'line',
            source: 'mapbox-traffic',
            'source-layer': 'traffic',
            minzoom: 0,
            paint: {
                'line-color': [
                    'case',
                    ['==', ['get', 'congestion'], 'low'], '#00ff00',
                    ['==', ['get', 'congestion'], 'moderate'], '#ffff00', 
                    ['==', ['get', 'congestion'], 'heavy'], '#ff9900',
                    ['==', ['get', 'congestion'], 'severe'], '#ff0000',
                    '#ff0000'
                ],
                'line-width': 8,
                'line-opacity': 0.9,
                'line-blur': 0
            }
        });
    }
    
    console.log('Traffic layer re-added successfully');
}

map.on('load', () => {
    console.log('Map loaded, adding traffic layer...');
    
    // Add Mapbox Traffic Layer (real-time traffic data)
    map.addSource('mapbox-traffic', {
        type: 'vector',
        url: 'mapbox://mapbox.mapbox-traffic-v1'
    });
    
    // Add traffic layer for live traffic visualization - ONLY LINES
    map.addLayer({
        id: 'traffic-layer',
        type: 'line',
        source: 'mapbox-traffic',
        'source-layer': 'traffic',
        minzoom: 0,
        paint: {
            'line-color': [
                'case',
                ['==', ['get', 'congestion'], 'low'], '#00ff00',
                ['==', ['get', 'congestion'], 'moderate'], '#ffff00', 
                ['==', ['get', 'congestion'], 'heavy'], '#ff9900',
                ['==', ['get', 'congestion'], 'severe'], '#ff0000',
                '#ff0000' // Default to red for visibility
            ],
            'line-width': 8,
            'line-opacity': 0.9,
            'line-blur': 0
        }
    });
    
    console.log('Traffic layer added successfully');
    
    // Add a fixed ambulance marker at the start
    const el = document.createElement('div');
    el.className = 'ambulance-marker';
    el.style.backgroundImage = 'url(https://img.icons8.com/color/48/000000/ambulance.png)';
    el.style.width = '48px';
    el.style.height = '48px';
    el.style.backgroundSize = '100%';
    ambulanceMarker = new mapboxgl.Marker(el).setLngLat(AMBULANCE_START_LOCATION.slice().reverse()).addTo(map);
    
    // Fetch initial hospital data
    fetch(`${API_BASE_URL}/hospitals`).then(res => res.json()).then(data => {
        hospitals = data;
        const cntEl = document.getElementById('hospital-count');
        if (cntEl) cntEl.textContent = hospitals.length;
        console.log(`Hospitals loaded: ${hospitals.length}`);
        displayHospitals();
    });
});
