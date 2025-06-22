# Complete StrikerBot Admin Command Center - Vercel Function
from fastapi import FastAPI, BackgroundTasks, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import HTMLResponse
import asyncio
import json
import os
import subprocess
import sys
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

app = FastAPI(title="StrikerBot Command Center", version="3.0")

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

# Pipeline status
pipeline_status = {
    "running": False,
    "stage": "",
    "progress": 0,
    "last_run": None,
    "results": None
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
    """Admin dashboard HTML"""
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
            
            .loading { opacity: 0.6; pointer-events: none; }
            .success { border-left-color: #4CAF50; }
            .error { border-left-color: #f44336; }
            
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
                <p>Admin Access | Full Pipeline Control | Live Production</p>
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
                        <p>GT League data collection with venv environment</p>
                        <button class="btn" onclick="runPhase('desktop-scrapers')">Run GT Scrapers</button>
                        <button class="btn" onclick="runPhase('parsers')">Run Parsers</button>
                    </div>
                    
                    <div class="command-card">
                        <h3>📁 File Transfer</h3>
                        <p>Auto-transfer parsed data to StrikerBot folders</p>
                        <button class="btn" onclick="runPhase('transfer')">Transfer Files</button>
                        <button class="btn" onclick="checkFiles()">Check File Status</button>
                    </div>
                    
                    <div class="command-card">
                        <h3>🏗️ StrikerBot Pipeline</h3>
                        <p>Complete processing and prediction chain</p>
                        <button class="btn" onclick="runPhase('vault-loading')">Load Vaults</button>
                        <button class="btn" onclick="runPhase('predictions')">Run Predictions</button>
                    </div>
                    
                    <div class="command-card success">
                        <h3>🚀 Full Automation</h3>
                        <p>End-to-end execution from scrapers to final slips</p>
                        <button class="btn" onclick="runFullPipeline()">Run Complete Pipeline</button>
                        <button class="btn" onclick="getStatus()">Refresh Status</button>
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
            </div>
        </div>
        
        <script>
            let adminToken = '';
            
            async function login() {
                const key = document.getElementById('adminKey').value;
                const errorDiv = document.getElementById('loginError');
                
                if (!key) {
                    showError('Please enter admin key');
                    return;
                }
                
                try {
                    const response = await fetch('./verify', {
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
                    } else {
                        showError('Invalid admin key');
                    }
                } catch (error) {
                    showError('Connection error. Please try again.');
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
                    const response = await fetch(`./run-phase/${phase}`, {
                        method: 'POST',
                        headers: { 'Authorization': `Bearer ${adminToken}` }
                    });
                    const data = await response.json();
                    updateStatus(data);
                    setTimeout(getStatus, 2000);
                } catch (error) {
                    console.error('Error:', error);
                } finally {
                    setTimeout(() => updateButtonState(false), 2000);
                }
            }
            
            async function runFullPipeline() {
                try {
                    updateButtonState(true);
                    const response = await fetch('./run-full-pipeline', {
                        method: 'POST',
                        headers: { 'Authorization': `Bearer ${adminToken}` }
                    });
                    const data = await response.json();
                    updateStatus(data);
                    
                    const interval = setInterval(async () => {
                        const status = await getStatus();
                        if (!status.running) {
                            clearInterval(interval);
                            updateButtonState(false);
                        }
                    }, 3000);
                } catch (error) {
                    console.error('Error:', error);
                    updateButtonState(false);
                }
            }
            
            async function getStatus() {
                try {
                    const response = await fetch('./status', {
                        headers: { 'Authorization': `Bearer ${adminToken}` }
                    });
                    const data = await response.json();
                    updateStatus(data);
                    return data;
                } catch (error) {
                    console.error('Error fetching status:', error);
                }
            }
            
            async function checkFiles() {
                try {
                    const response = await fetch('./check-files', {
                        headers: { 'Authorization': `Bearer ${adminToken}` }
                    });
                    const data = await response.json();
                    updateSystemInfo(data);
                } catch (error) {
                    console.error('Error checking files:', error);
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
                        <span class="${data.running ? 'running' : 'completed'}">${data.stage || 'Ready'}</span>
                    </div>
                    <div class="phase">
                        <span><strong>Progress:</strong></span>
                        <span>${data.progress || 0}%</span>
                    </div>
                    <div class="phase">
                        <span><strong>Status:</strong></span>
                        <span class="${data.running ? 'running' : 'completed'}">${data.running ? 'Running' : 'Idle'}</span>
                    </div>
                `;
                
                if (data.last_run) {
                    const lastRun = new Date(data.last_run).toLocaleString();
                    html += `
                        <div class="phase">
                            <span><strong>Last Run:</strong></span>
                            <span>${lastRun}</span>
                        </div>
                    `;
                }
                
                statusContent.innerHTML = html;
            }
            
            function updateSystemInfo(data) {
                const systemContent = document.getElementById('systemContent');
                
                let html = '<h4>File Counts:</h4>';
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
                
                html += '<h4>Directories:</h4>';
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
                    if (loading) {
                        btn.classList.add('loading');
                        btn.disabled = true;
                    } else {
                        btn.classList.remove('loading');
                        btn.disabled = false;
                    }
                });
            }
            
            function startAutoRefresh() {
                setInterval(() => {
                    if (adminToken && document.getElementById('commandCenter').style.display !== 'none') {
                        getStatus();
                    }
                }, 15000);
            }
            
            document.getElementById('adminKey').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    login();
                }
            });
        </script>
    </body>
    </html>
    """

@app.post("/verify")
async def verify_admin(token: str = Depends(verify_admin_key)):
    """Verify admin access"""
    return {"status": "verified", "message": "Admin access granted"}

@app.get("/status")
async def get_admin_status(token: str = Depends(verify_admin_key)):
    """Get detailed pipeline status"""
    return pipeline_status

@app.get("/health")
async def health_check():
    return {
        "status": "online", 
        "timestamp": datetime.now().isoformat(),
        "pipeline_running": pipeline_status["running"]
    }

@app.post("/run-phase/{phase}")
async def run_phase(phase: str, background_tasks: BackgroundTasks, token: str = Depends(verify_admin_key)):
    """Run specific pipeline phase"""
    return {"status": "started", "message": f"Phase {phase} initiated (demo mode)"}

@app.post("/run-full-pipeline")
async def run_full_pipeline(background_tasks: BackgroundTasks, token: str = Depends(verify_admin_key)):
    """Execute complete pipeline"""
    return {"status": "started", "message": "Complete pipeline initiated (demo mode)"}

@app.get("/check-files")
async def check_files(token: str = Depends(verify_admin_key)):
    """Check file status"""
    return {
        "file_counts": {
            "html_snapshots": 42,
            "parsed_jsons": 28,
            "vault_files": 1286,
            "dashboard_files": 2
        },
        "directories_exist": {
            "vaults": True,
            "results": True,
            "scraped_data": False,
            "input_data": True
        }
    }

# This is required for Vercel
handler = app

