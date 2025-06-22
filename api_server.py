# Complete StrikerBot Remote Command Center - Full Version
from fastapi import FastAPI, HTTPException, Depends, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import HTMLResponse
import json
import os
from datetime import datetime
from typing import Dict, Optional
import uuid
import asyncio

app = FastAPI(title="StrikerBot Remote Command Center", version="3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()
ADMIN_KEY = os.getenv("ADMIN_KEY", "FLAMEBOUND_DEV_TEAM_2025")

# Command queue and status tracking
command_queue = {}
agent_status = {}
pipeline_status = {
    "running": False,
    "stage": "ready",
    "progress": 0,
    "last_run": None,
    "phases": {
        "desktop_scrapers": {"completed": False, "duration": 0},
        "parsers": {"completed": False, "duration": 0},
        "file_transfer": {"completed": False, "duration": 0},
        "vault_loading": {"completed": False, "duration": 0},
        "predictions": {"completed": False, "duration": 0}
    },
    "file_counts": {
        "html_snapshots": 0,
        "parsed_jsons": 0,
        "transferred_files": 0,
        "vault_matches": 0
    }
}

def verify_admin_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify admin access key"""
    if credentials.credentials != ADMIN_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials

@app.get("/", response_class=HTMLResponse)
async def admin_dashboard():
    """Complete admin dashboard HTML - exactly like your local version"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>StrikerBot Command Center</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%); 
                color: #fff; 
                min-height: 100vh;
                padding: 20px;
            }
            .container { max-width: 1200px; margin: 0 auto; }
            .header { 
                text-align: center; 
                margin-bottom: 40px; 
                padding: 30px 0;
                border-bottom: 2px solid #ff6b35;
            }
            .header h1 { 
                font-size: 3rem; 
                margin-bottom: 10px; 
                background: linear-gradient(45deg, #ff6b35, #f39c12);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }
            .header p { font-size: 1.2rem; opacity: 0.8; }
            
            .connection-status {
                background: rgba(42, 42, 42, 0.9);
                padding: 15px;
                border-radius: 10px;
                margin-bottom: 20px;
                text-align: center;
                border-left: 5px solid #666;
            }
            .online { border-left-color: #4CAF50; }
            .offline { border-left-color: #f44336; }
            
            .admin-login { 
                max-width: 450px; 
                margin: 50px auto; 
                background: rgba(42, 42, 42, 0.9); 
                padding: 40px; 
                border-radius: 15px; 
                box-shadow: 0 10px 30px rgba(0,0,0,0.5);
                backdrop-filter: blur(10px);
            }
            .admin-login h3 { margin-bottom: 20px; text-align: center; }
            .admin-login input { 
                width: 100%; 
                padding: 15px; 
                margin: 15px 0; 
                border: 2px solid #444;
                border-radius: 8px;
                background: #333;
                color: #fff;
                font-size: 16px;
                transition: border-color 0.3s;
            }
            .admin-login input:focus {
                outline: none;
                border-color: #ff6b35;
            }
            
            .command-grid { 
                display: grid; 
                grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); 
                gap: 25px; 
                margin-bottom: 30px;
            }
            .command-card { 
                background: linear-gradient(135deg, rgba(42, 42, 42, 0.9) 0%, rgba(35, 35, 35, 0.9) 100%); 
                padding: 25px; 
                border-radius: 15px; 
                border-left: 5px solid #ff6b35;
                box-shadow: 0 8px 25px rgba(0,0,0,0.3);
                transition: transform 0.3s, box-shadow 0.3s;
            }
            .command-card:hover {
                transform: translateY(-5px);
                box-shadow: 0 15px 35px rgba(255, 107, 53, 0.2);
            }
            .command-card h3 { 
                margin-bottom: 15px; 
                color: #ff6b35;
                font-size: 1.3rem;
            }
            .command-card p { 
                margin-bottom: 20px; 
                opacity: 0.8; 
                line-height: 1.5;
            }
            
            .btn { 
                background: linear-gradient(45deg, #ff6b35, #e55a2b); 
                color: white; 
                padding: 12px 24px; 
                border: none; 
                border-radius: 8px; 
                cursor: pointer; 
                margin: 8px 8px 8px 0; 
                font-size: 14px;
                font-weight: 600;
                transition: all 0.3s;
                box-shadow: 0 4px 15px rgba(255, 107, 53, 0.3);
            }
            .btn:hover { 
                background: linear-gradient(45deg, #e55a2b, #d44d1f);
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(255, 107, 53, 0.4);
            }
            .btn:active { transform: translateY(0); }
            .btn:disabled { 
                opacity: 0.5; 
                cursor: not-allowed; 
                transform: none;
                box-shadow: none;
            }
            
            .status { 
                background: rgba(51, 51, 51, 0.9); 
                padding: 25px; 
                border-radius: 15px; 
                margin: 20px 0;
                border: 1px solid #444;
            }
            .status h3 { 
                margin-bottom: 15px; 
                color: #ff6b35;
                font-size: 1.3rem;
            }
            .phase { 
                display: flex; 
                justify-content: space-between; 
                align-items: center; 
                margin: 10px 0; 
                padding: 8px 0;
                border-bottom: 1px solid #444;
            }
            .phase:last-child { border-bottom: none; }
            .completed { color: #4CAF50; font-weight: 600; }
            .running { color: #ff9800; font-weight: 600; }
            .pending { color: #666; }
            .error { color: #f44336; }
            
            .progress-bar {
                width: 100%;
                height: 8px;
                background: #333;
                border-radius: 4px;
                overflow: hidden;
                margin: 10px 0;
            }
            .progress-fill {
                height: 100%;
                background: linear-gradient(90deg, #ff6b35, #f39c12);
                width: 0%;
                transition: width 0.3s ease;
            }
            
            .log-output {
                background: #000;
                color: #0f0;
                padding: 15px;
                border-radius: 8px;
                font-family: 'Courier New', monospace;
                font-size: 12px;
                max-height: 300px;
                overflow-y: auto;
                margin: 10px 0;
                border: 1px solid #333;
            }
            
            .success { border-left-color: #4CAF50; }
            .warning { border-left-color: #ff9800; }
            
            @media (max-width: 768px) {
                .header h1 { font-size: 2rem; }
                .command-grid { grid-template-columns: 1fr; }
                .admin-login { margin: 20px; padding: 25px; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🔥 STRIKERBOT COMMAND CENTER</h1>
                <p>Remote Control | Local PC Integration | Global Access</p>
            </div>
            
            <div class="connection-status" id="connectionStatus">
                <div>🔄 Checking local PC connection...</div>
            </div>
            
            <div class="admin-login" id="loginSection">
                <h3>🔑 Admin Access Required</h3>
                <input type="password" id="adminKey" placeholder="Enter Admin Key" autocomplete="off">
                <button class="btn" onclick="login()" style="width: 100%;">Access Command Center</button>
                <div id="loginError" style="color: #f44336; margin-top: 10px; display: none;"></div>
            </div>
            
            <div id="commandCenter" style="display: none;">
                <div class="command-grid">
                    <div class="command-card">
                        <h3>🕷️ Desktop Scrapers</h3>
                        <p>GT League data collection with venv on your local PC</p>
                        <button class="btn" onclick="runPhase('desktop-scrapers')">Run GT Scrapers</button>
                        <button class="btn" onclick="runPhase('parsers')">Run Parsers</button>
                    </div>
                    
                    <div class="command-card">
                        <h3>📁 File Transfer</h3>
                        <p>Auto-transfer parsed data to StrikerBot on local PC</p>
                        <button class="btn" onclick="runPhase('transfer')">Transfer Files</button>
                        <button class="btn" onclick="checkFiles()">Check File Status</button>
                    </div>
                    
                    <div class="command-card">
                        <h3>🏗️ StrikerBot Pipeline</h3>
                        <p>Complete processing chain on your local PC</p>
                        <button class="btn" onclick="runPhase('match-context')">Match Context</button>
                        <button class="btn" onclick="runPhase('vault-loading')">Load Vaults</button>
                        <button class="btn" onclick="runPhase('predictions')">Predictions</button>
                    </div>
                    
                    <div class="command-card success">
                        <h3>🚀 Full Automation</h3>
                        <p>End-to-end execution from scrapers to final slips</p>
                        <button class="btn" onclick="runFullPipeline()" style="background: linear-gradient(45deg, #4CAF50, #45a049);">Run Complete Pipeline</button>
                        <button class="btn" onclick="getStatus()">Check Status</button>
                    </div>
                </div>
                
                <div class="status" id="statusDisplay">
                    <h3>📊 Pipeline Status</h3>
                    <div class="progress-bar">
                        <div class="progress-fill" id="progressBar"></div>
                    </div>
                    <div id="statusContent">Ready to execute...</div>
                </div>
                
                <div class="status" id="systemInfo">
                    <h3>🔧 System Information</h3>
                    <div id="systemContent">Loading system info...</div>
                </div>
                
                <div class="status" id="logDisplay">
                    <h3>📝 Execution Logs</h3>
                    <div class="log-output" id="logContent">Waiting for commands...</div>
                </div>
            </div>
        </div>
        
        <script>
            let adminToken = '';
            let refreshInterval = null;
            
            async function login() {
                const key = document.getElementById('adminKey').value;
                const errorDiv = document.getElementById('loginError');
                
                if (!key) {
                    showError('Please enter admin key');
                    return;
                }
                
                try {
                    const response = await fetch('/api/admin/verify', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${key}`
                        }
                    });
                    
                    if (response.ok) {
                        adminToken = key;
                        document.getElementById('loginSection').style.display = 'none';
                        document.getElementById('commandCenter').style.display = 'block';
                        await getStatus();
                        await checkFiles();
                        startAutoRefresh();
                        addLog('✅ Admin access granted - Command Center active');
                    } else {
                        showError('Invalid admin key');
                    }
                } catch (error) {
                    showError('Connection error: ' + error.message);
                }
            }
            
            function showError(message) {
                const errorDiv = document.getElementById('loginError');
                errorDiv.textContent = message;
                errorDiv.style.display = 'block';
                setTimeout(() => {
                    errorDiv.style.display = 'none';
                }, 3000);
            }
            
            async function runPhase(phase) {
                try {
                    updateButtonState(true);
                    addLog(`🚀 Starting phase: ${phase} on local PC`);
                    
                    const response = await fetch(`/api/admin/run-phase/${phase}`, {
                        method: 'POST',
                        headers: { 'Authorization': `Bearer ${adminToken}` }
                    });
                    const data = await response.json();
                    
                    if (response.ok) {
                        addLog(`✅ Phase ${phase} sent to local PC successfully`);
                        updateStatus(data);
                        
                        // Poll for updates more frequently during execution
                        if (refreshInterval) clearInterval(refreshInterval);
                        refreshInterval = setInterval(getStatus, 2000);
                        
                        // Reset to normal refresh after 30 seconds
                        setTimeout(() => {
                            if (refreshInterval) clearInterval(refreshInterval);
                            startAutoRefresh();
                        }, 30000);
                    } else {
                        addLog(`❌ Error in phase ${phase}: ${data.message || 'Unknown error'}`);
                    }
                } catch (error) {
                    addLog(`❌ Connection error: ${error.message}`);
                } finally {
                    setTimeout(() => updateButtonState(false), 3000);
                }
            }
            
            async function runFullPipeline() {
                try {
                    updateButtonState(true);
                    addLog('🔥 STARTING COMPLETE STRIKERBOT PIPELINE ON LOCAL PC');
                    
                    const response = await fetch('/api/admin/run-full-pipeline', {
                        method: 'POST',
                        headers: { 'Authorization': `Bearer ${adminToken}` }
                    });
                    const data = await response.json();
                    
                    if (response.ok) {
                        addLog('✅ Full pipeline sent to local PC - monitoring progress...');
                        updateStatus(data);
                        
                        // Continuous monitoring during full pipeline
                        if (refreshInterval) clearInterval(refreshInterval);
                        refreshInterval = setInterval(async () => {
                            const status = await getStatus();
                            if (!status.running) {
                                clearInterval(refreshInterval);
                                startAutoRefresh();
                                updateButtonState(false);
                                addLog('🏁 Pipeline execution completed on local PC');
                            }
                        }, 3000);
                    } else {
                        addLog(`❌ Pipeline start error: ${data.message || 'Unknown error'}`);
                        updateButtonState(false);
                    }
                } catch (error) {
                    addLog(`❌ Pipeline connection error: ${error.message}`);
                    updateButtonState(false);
                }
            }
            
            async function getStatus() {
                try {
                    const response = await fetch('/api/admin/status', {
                        headers: { 'Authorization': `Bearer ${adminToken}` }
                    });
                    const data = await response.json();
                    updateStatus(data);
                    updateConnectionStatus();
                    return data;
                } catch (error) {
                    console.error('Error fetching status:', error);
                    return null;
                }
            }
            
            async function checkFiles() {
                try {
                    const response = await fetch('/api/admin/check-files', {
                        headers: { 'Authorization': `Bearer ${adminToken}` }
                    });
                    const data = await response.json();
                    updateSystemInfo(data);
                } catch (error) {
                    console.error('Error checking files:', error);
                }
            }
            
            async function updateConnectionStatus() {
                try {
                    const response = await fetch('/agent-status', {
                        headers: { 'Authorization': `Bearer ${adminToken}` }
                    });
                    const data = await response.json();
                    
                    const statusDiv = document.getElementById('connectionStatus');
                    if (data.online) {
                        statusDiv.className = 'connection-status online';
                        statusDiv.innerHTML = `
                            <div>✅ Local PC Online & Ready</div>
                            <small>Last seen: ${new Date(data.last_seen).toLocaleString()}</small>
                        `;
                    } else {
                        statusDiv.className = 'connection-status offline';
                        statusDiv.innerHTML = `
                            <div>❌ Local PC Offline</div>
                            <small>Make sure local_agent.py is running on your PC</small>
                        `;
                    }
                } catch (error) {
                    const statusDiv = document.getElementById('connectionStatus');
                    statusDiv.className = 'connection-status offline';
                    statusDiv.innerHTML = '<div>❌ Connection Error</div>';
                }
            }
            
            function updateStatus(data) {
                const statusContent = document.getElementById('statusContent');
                const progressBar = document.getElementById('progressBar');
                
                if (data.progress !== undefined) {
                    progressBar.style.width = data.progress + '%';
                }
                
                let html = `
                    <div class="phase">
                        <span><strong>Current Stage:</strong></span>
                        <span class="${data.running ? 'running' : (data.stage?.includes('error') ? 'error' : 'completed')}">${data.stage || 'Ready'}</span>
                    </div>
                    <div class="phase">
                        <span><strong>Progress:</strong></span>
                        <span>${data.progress || 0}%</span>
                    </div>
                    <div class="phase">
                        <span><strong>Status:</strong></span>
                        <span class="${data.running ? 'running' : 'completed'}">${data.running ? '🏃 Running' : '✅ Ready'}</span>
                    </div>
                `;
                
                if (data.phases) {
                    html += '<h4 style="margin: 15px 0 10px 0; color: #ff6b35;">Phase Status:</h4>';
                    for (const [phase, status] of Object.entries(data.phases)) {
                        const className = status.completed ? 'completed' : 'pending';
                        html += `
                            <div class="phase">
                                <span>${phase.replace(/_/g, ' ').toUpperCase()}:</span>
                                <span class="${className}">${status.completed ? '✅' : '⏳'} ${status.duration}s</span>
                            </div>
                        `;
                    }
                }
                
                if (data.file_counts) {
                    html += '<h4 style="margin: 15px 0 10px 0; color: #ff6b35;">File Counts:</h4>';
                    for (const [type, count] of Object.entries(data.file_counts)) {
                        html += `
                            <div class="phase">
                                <span>${type.replace(/_/g, ' ').toUpperCase()}:</span>
                                <span class="completed">${count}</span>
                            </div>
                        `;
                    }
                }
                
                if (data.last_run) {
                    const lastRun = new Date(data.last_run).toLocaleString();
                    html += `
                        <div class="phase">
                            <span><strong>Last Run:</strong></span>
                            <span class="completed">${lastRun}</span>
                        </div>
                    `;
                }
                
                statusContent.innerHTML = html;
            }
            
            function updateSystemInfo(data) {
                const systemContent = document.getElementById('systemContent');
                
                let html = '<h4>Local PC Paths:</h4>';
                if (data.desktop_paths) {
                    for (const [path, location] of Object.entries(data.desktop_paths)) {
                        html += `
                            <div class="phase">
                                <span>${path.replace(/_/g, ' ').toUpperCase()}:</span>
                                <span class="completed" style="font-size: 0.8em;">${location}</span>
                            </div>
                        `;
                    }
                }
                
                html += '<h4>File Counts:</h4>';
                if (data.file_counts) {
                    for (const [type, count] of Object.entries(data.file_counts)) {
                        html += `
                            <div class="phase">
                                <span>${type.replace(/_/g, ' ').toUpperCase()}:</span>
                                <span class="completed">${count}</span>
                            </div>
                        `;
                    }
                }
                
                html += '<h4>Directories Status:</h4>';
                if (data.directories_exist) {
                    for (const [dir, exists] of Object.entries(data.directories_exist)) {
                        html += `
                            <div class="phase">
                                <span>${dir.replace(/_/g, ' ').toUpperCase()}:</span>
                                <span class="${exists ? 'completed' : 'error'}">${exists ? '✅ Exists' : '❌ Missing'}</span>
                            </div>
                        `;
                    }
                }
                
                systemContent.innerHTML = html;
            }
            
            function updateButtonState(loading) {
                const buttons = document.querySelectorAll('.btn');
                buttons.forEach(btn => {
                    btn.disabled = loading;
                    btn.style.opacity = loading ? '0.6' : '1';
                    btn.style.cursor = loading ? 'not-allowed' : 'pointer';
                });
            }
            
            function addLog(message) {
                const logContent = document.getElementById('logContent');
                const timestamp = new Date().toLocaleTimeString();
                const logLine = `[${timestamp}] ${message}`;
                
                logContent.innerHTML += logLine + '\\n';
                logContent.scrollTop = logContent.scrollHeight;
                
                // Keep only last 50 lines
                const lines = logContent.innerHTML.split('\\n');
                if (lines.length > 50) {
                    logContent.innerHTML = lines.slice(-50).join('\\n');
                }
            }
            
            function startAutoRefresh() {
                if (refreshInterval) clearInterval(refreshInterval);
                refreshInterval = setInterval(() => {
                    if (adminToken && document.getElementById('commandCenter').style.display !== 'none') {
                        getStatus();
                        updateConnectionStatus();
                    }
                }, 10000);
            }
            
            // Keyboard shortcuts
            document.getElementById('adminKey').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    login();
                }
            });
            
            // Auto-focus on admin key input
            setTimeout(() => {
                document.getElementById('adminKey').focus();
                updateConnectionStatus();
            }, 500);
        </script>
    </body>
    </html>
    """

# API Endpoints - exactly like your local version
@app.post("/api/admin/verify")
async def verify_admin(token: str = Depends(verify_admin_key)):
    """Verify admin access"""
    return {"status": "verified", "message": "Admin access granted"}

@app.get("/api/admin/status")
async def get_admin_status(token: str = Depends(verify_admin_key)):
    """Get detailed pipeline status"""
    return pipeline_status

@app.post("/api/admin/run-phase/{phase}")
async def run_phase(phase: str, background_tasks: BackgroundTasks, token: str = Depends(verify_admin_key)):
    """Run specific pipeline phase on local PC"""
    command_id = str(uuid.uuid4())
    
    # Map phase names to match your local system
    phase_mapping = {
        "desktop-scrapers": "desktop-scrapers",
        "parsers": "parsers", 
        "transfer": "file-transfer",
        "match-context": "match-context",
        "vault-loading": "vault-loading",
        "predictions": "predictions"
    }
    
    mapped_phase = phase_mapping.get(phase, phase)
    
    command = {
        "id": command_id,
        "type": mapped_phase,
        "timestamp": datetime.now().isoformat(),
        "status": "pending"
    }
    
    command_queue[command_id] = command
    pipeline_status["running"] = True
    pipeline_status["stage"] = f"sending_{mapped_phase}_to_local_pc"
    
    return {"status": "started", "message": f"Phase {phase} sent to local PC", "command_id": command_id}

@app.post("/api/admin/run-full-pipeline")
async def run_full_pipeline(background_tasks: BackgroundTasks, token: str = Depends(verify_admin_key)):
    """Execute complete pipeline on local PC"""
    if pipeline_status["running"]:
        return {"status": "already_running", "message": "Pipeline is already running"}
    
    command_id = str(uuid.uuid4())
    
    command = {
        "id": command_id,
        "type": "full-pipeline",
        "timestamp": datetime.now().isoformat(),
        "status": "pending"
    }
    
    command_queue[command_id] = command
    pipeline_status["running"] = True
    pipeline_status["stage"] = "sending_full_pipeline_to_local_pc"
    pipeline_status["progress"] = 0
    
    return {"status": "started", "message": "Complete StrikerBot pipeline sent to local PC", "command_id": command_id}

@app.get("/api/admin/check-files")
async def check_files(token: str = Depends(verify_admin_key)):
    """Check file status on local PC"""
    # Return cached/mock data since we're remote
    # The local agent will update these via status reports
    return {
        "desktop_paths": {
            "gt_scrapers": "~/Desktop/GT_Scrapers",
            "gt_snapshots": "~/Desktop/gt_snapshots", 
            "gt_json": "~/Desktop/gt_json"
        },
        "strikerbot_paths": {
            "input_data": "./input_data",
            "dashboard_scrapes": "./dashboard_scrapes",
            "vaults": "./vaults"
        },
        "file_counts": pipeline_status["file_counts"],
        "directories_exist": {
            "gt_scrapers": True,
            "gt_snapshots": True,
            "gt_json": True,
            "input_data": True,
            "dashboard_scrapes": True
        }
    }

# Agent communication endpoints
@app.get("/agent/commands/{agent_id}")
async def get_agent_commands(agent_id: str):
    """Get pending commands for local agent"""
    for cmd_id, command in command_queue.items():
        if command["status"] == "pending":
            command["status"] = "sent"
            return {
                "has_command": True,
                "command": command
            }
    
    return {"has_command": False}

@app.post("/agent/status")
async def update_agent_status(status_data: dict):
    """Update agent status from local PC"""
    agent_id = status_data.get("agent_id")
    command_id = status_data.get("command_id")
    status = status_data.get("status")
    message = status_data.get("message", "")
    
    # Update command status
    if command_id in command_queue:
        command_queue[command_id]["status"] = status
        command_queue[command_id]["result"] = message
        
        # Update pipeline status based on command result
        if status == "running":
            pipeline_status["running"] = True
            pipeline_status["stage"] = f"executing_{command_queue[command_id]['type']}"
        elif status == "completed":
            pipeline_status["running"] = False
            pipeline_status["stage"] = f"{command_queue[command_id]['type']}_completed"
            pipeline_status["progress"] = 100
            pipeline_status["last_run"] = datetime.now().isoformat()
        elif status == "failed":
            pipeline_status["running"] = False
            pipeline_status["stage"] = f"{command_queue[command_id]['type']}_failed: {message}"
            pipeline_status["progress"] = 0
    
    # Update agent heartbeat
    agent_status[agent_id] = {
        "last_seen": datetime.now().isoformat(),
        "online": True
    }
    
    return {"status": "updated"}

@app.get("/agent-status")
async def get_agent_status(token: str = Depends(verify_admin_key)):
    """Get local PC agent online status"""
    agent_id = "local_pc_agent"
    
    if agent_id in agent_status:
        last_seen = datetime.fromisoformat(agent_status[agent_id]["last_seen"])
        is_online = (datetime.now() - last_seen).total_seconds() < 60  # Online if seen within 60 seconds
        
        return {
            "online": is_online,
            "last_seen": agent_status[agent_id]["last_seen"],
            "agent_id": agent_id
        }
    else:
        return {
            "online": False,
            "last_seen": None,
            "agent_id": agent_id
        }

@app.get("/command-status")
async def get_command_status(token: str = Depends(verify_admin_key)):
    """Get command execution status"""
    active_commands = len([cmd for cmd in command_queue.values() if cmd["status"] in ["pending", "running"]])
    completed_today = len([cmd for cmd in command_queue.values() if cmd["status"] == "completed"])
    
    last_command = None
    if command_queue:
        latest = max(command_queue.values(), key=lambda x: x["timestamp"])
        last_command = f"{latest['type']} - {latest['status']}"
    
    return {
        "active_commands": active_commands,
        "completed_today": completed_today,
        "last_command": last_command,
        "total_commands": len(command_queue)
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "online",
        "timestamp": datetime.now().isoformat(),
        "environment": "railway_remote_control",
        "pipeline_running": pipeline_status["running"],
        "active_agents": len([a for a in agent_status.values() if a.get("online", False)]),
        "pending_commands": len([cmd for cmd in command_queue.values() if cmd["status"] == "pending"])
    }

# API endpoints for frontend integration (same as your local version)
@app.get("/api/live-matches")
async def get_live_matches():
    """Get live matches for frontend"""
    mock_matches = [
        {
            "id": "match_001",
            "home_team": "Barcelona",
            "away_team": "Real Madrid",
            "home_player": "Messi",
            "away_player": "Ronaldo",
            "kickoff": "14:00",
            "time_slot": "Live",
            "status": "scheduled",
            "league": "GT League",
            "date": datetime.now().strftime("%Y-%m-%d")
        },
        {
            "id": "match_002",
            "home_team": "Liverpool",
            "away_team": "Manchester City",
            "home_player": "Salah",
            "away_player": "Haaland",
            "kickoff": "16:30",
            "time_slot": "Live",
            "status": "scheduled",
            "league": "GT League",
            "date": datetime.now().strftime("%Y-%m-%d")
        }
    ]
    
    return {
        "status": "success",
        "data": mock_matches,
        "total_matches": len(mock_matches),
        "time_slots": 1,
        "date": datetime.now().strftime("%Y-%m-%d")
    }

@app.get("/api/predictions/{match_id}")
async def get_match_prediction(match_id: str):
    """Get prediction for specific match"""
    prediction = {
        "match_id": match_id,
        "home_team": "Team A",
        "away_team": "Team B",
        "home_player": "Player A",
        "away_player": "Player B",
        "predictions": {
            "winner": {
                "home": 65,
                "away": 25,
                "tie": 10,
                "confidence": "B+ 🟢 SAFE"
            },
            "total_goals": {
                "over_3_5": 72,
                "under_3_5": 28,
                "confidence": "B- 🟡 WATCH"
            },
            "exact_score": "2-1 to 3-1",
            "patterns": ["P05 - MIDFIELD ENFORCER", "P01 - EARLY MOMENTUM LOCK"],
            "final_grade": "A- (87%) 🟢 SAFE"
        },
        "generated_at": datetime.now().isoformat()
    }
    
    return {"status": "success", "data": prediction}

@app.get("/api/vault-stats")
async def get_vault_stats():
    """Get vault statistics"""
    return {
        "status": "success",
        "data": {
            "total_matches": 1286,
            "winner_distribution": {"HOME": 45.2, "AWAY": 32.1, "TIE": 22.7},
            "goals_distribution": {"over_3_5": 58.3, "under_3_5": 41.7},
            "last_updated": datetime.now().isoformat()
        }
    }

# For Railway deployment
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
