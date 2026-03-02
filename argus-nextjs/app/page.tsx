'use client';

import { useEffect, useRef, useState, useCallback } from 'react';

type Log = {
    ts: string;
    cam: string;
    type: string;
    conf: number;
    score: number;
    severity: string;
    note: string;
};

type Snapshot = {
    ts: string;
    cam: string;
    type: string;
    severity: string;
    dataUrl: string;
};

type Camera = {
    id: string;
    name: string;
};

const cameras: Camera[] = [
    { id: "CAM-1", name: "ATM Lobby" },
    { id: "CAM-2", name: "ATM Exterior" },
    { id: "CAM-3", name: "Side Entrance" },
    { id: "CAM-4", name: "Parking View" },
];

const DEFAULT_BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

export default function Home() {
    /* State */
    const [role, setRole] = useState("GUARD");
    const [selectedCam, setSelectedCam] = useState("CAM-1");
    const [riskScore, setRiskScore] = useState(0);
    const [gateLocked, setGateLocked] = useState(false);
    const [detectionReasons, setDetectionReasons] = useState<string[]>([]);
    const [logs, setLogs] = useState<Log[]>([]);
    const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
    const [networkStatus, setNetworkStatus] = useState("CONNECTING");
    const [hwConnected, setHwConnected] = useState(false);
    const [hwPort, setHwPort] = useState<string | null>(null);
    const [arduinoConnecting, setArduinoConnecting] = useState(false);
    const [arduinoMessage, setArduinoMessage] = useState("");
    const [arduinoPortInput, setArduinoPortInput] = useState("COM9");
    const [remoteStatus, setRemoteStatus] = useState("Standby");
    const [ackText, setAckText] = useState("");
    const [ackLog, setAckLog] = useState("No acknowledgement yet.");
    const [isConnected, setIsConnected] = useState(false);
    const [camSearch, setCamSearch] = useState("");
    const [sirenPlaying, setSirenPlaying] = useState(false);
    const [audioBlocked, setAudioBlocked] = useState(false);
    const [threatPatternText, setThreatPatternText] = useState("Pattern: Monitoring normal activity");
    const [backendUrl, setBackendUrl] = useState(DEFAULT_BACKEND);
    const [backendInput, setBackendInput] = useState(DEFAULT_BACKEND);
    const [showBackendInput, setShowBackendInput] = useState(false);

    /* Toggles */
    const [soundEnabled, setSoundEnabled] = useState(true);
    const [autoLockEnabled, setAutoLockEnabled] = useState(true);
    const [flashEnabled, setFlashEnabled] = useState(true);

    /* Refs */
    const imgRef = useRef<HTMLImageElement>(null);
    const videoWsRef = useRef<WebSocket | null>(null);
    const statusWsRef = useRef<WebSocket | null>(null);
    const sirenAudioRef = useRef<HTMLAudioElement | null>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);

    /* Helper Functions */
    const nowStr = () => new Date().toLocaleString();
    const timeOnly = () => new Date().toLocaleTimeString();
    const clamp = (n: number, a: number, b: number) => Math.max(a, Math.min(b, n));

    const wsUrl = (path: string) => {
        const url = new URL(backendUrl);
        const proto = url.protocol === 'https:' ? 'wss:' : 'ws:';
        // ngrok free plan: skip browser interstitial via query param
        return `${proto}//${url.host}${path}?ngrok-skip-browser-warning=true`;
    };

    const apiFetch = (path: string, options: RequestInit = {}) => {
        return fetch(`${backendUrl}${path}`, {
            ...options,
            headers: {
                'ngrok-skip-browser-warning': 'true',
                'Content-Type': 'application/json',
                ...(options.headers || {}),
            },
        });
    };

    const severityFromScore = (score: number) => {
        if (score >= 75) return "high";
        if (score >= 40) return "med";
        return "low";
    };

    const riskTextFromScore = (score: number) => {
        if (score >= 75) return "HIGH";
        if (score >= 40) return "MEDIUM";
        return "LOW";
    };

    const riskFillColor = (score: number) => {
        if (score >= 75) return "rgba(239,68,68,0.85)";
        if (score >= 40) return "rgba(245,158,11,0.90)";
        return "rgba(16,185,129,0.85)";
    };

    const timeMultiplier = () => {
        const h = new Date().getHours();
        if (h >= 22 || h <= 5) return 1.25;
        if (h >= 6 && h <= 8) return 1.10;
        return 1.00;
    };

    const updateThreatPattern = (currentLogs: Log[]) => {
        if (currentLogs.length === 0) {
            setThreatPatternText("Pattern: Monitoring normal activity");
            return;
        }
        const last5 = currentLogs.slice(-5);
        const types = last5.map(x => x.type.toLowerCase());
        const hasWeapon = types.some(t => t.includes("weapon") || t.includes("gun"));
        const hasMask = types.some(t => t.includes("mask"));
        const hasCrowd = types.some(t => t.includes("crowd"));
        const hasLoiter = types.some(t => t.includes("loiter"));

        if (hasWeapon && hasMask) setThreatPatternText("Pattern: Weapon + Mask → possible robbery attempt");
        else if (hasMask && hasLoiter) setThreatPatternText("Pattern: Mask + Loitering → possible preparation / casing");
        else if (hasCrowd && hasMask) setThreatPatternText("Pattern: Crowd + Mask → diversion risk; monitor closely");
        else if (hasWeapon) setThreatPatternText("Pattern: Weapon signal detected → immediate response recommended");
        else setThreatPatternText("Pattern: Suspicious activity detected; continue monitoring");
    };

    const generateReport = () => {
        const lines = [];
        lines.push("ARGUS INCIDENT REPORT");
        lines.push("=====================");
        lines.push(`Generated: ${nowStr()}`);
        lines.push(`ATM-ID: ATM-01`);
        lines.push(`Selected Camera: ${selectedCam}`);
        lines.push(`Current Risk Score: ${riskScore}/100 (${riskTextFromScore(riskScore)})`);
        lines.push(`Gate Status: ${gateLocked ? "LOCKED" : "UNLOCKED"}`);
        lines.push(`Backend: ${backendUrl}`);
        lines.push(`Arduino: ${hwConnected ? `Connected on ${hwPort}` : 'Disconnected'}`);
        lines.push("");
        lines.push("DETECTIONS:");
        if (logs.length === 0) {
            lines.push("  - None");
        } else {
            logs.forEach((l, i) => {
                lines.push(`  ${i + 1}. [${l.ts}] ${l.cam} • ${l.type.toUpperCase()} • Risk ${l.score} • ${l.note}`);
            });
        }
        lines.push("");
        lines.push("ACKNOWLEDGEMENT:");
        lines.push("  " + ackLog);
        lines.push("");
        lines.push("System: ARGUS • AI-Based Auto Theft Door Lock");
        lines.push("=====================");

        const blob = new Blob([lines.join("\n")], { type: "text/plain" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `ARGUS_Report_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.txt`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 500);
    };

    const saveSnapshot = (type = "info") => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext("2d");
        if (!ctx) return;
        canvas.width = 640;
        canvas.height = 360;
        ctx.fillStyle = "#0b0f1a";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        if (imgRef.current && imgRef.current.complete) {
            ctx.drawImage(imgRef.current, 0, 0, canvas.width, canvas.height);
        }
        ctx.fillStyle = "rgba(0,0,0,0.5)";
        ctx.fillRect(0, 0, canvas.width, 100);
        ctx.fillStyle = "rgba(255,255,255,0.92)";
        ctx.font = "bold 24px Arial";
        ctx.fillText("ARGUS SNAPSHOT", 18, 40);
        ctx.font = "14px Arial";
        ctx.fillStyle = "rgba(255,255,255,0.75)";
        ctx.fillText(`Camera: ${selectedCam}`, 18, 65);
        ctx.fillText(`Time: ${nowStr()}`, 18, 85);
        ctx.fillText(`Type: ${type.toUpperCase()}`, 300, 65);
        ctx.fillText(`Risk: ${riskScore}/100`, 300, 85);
        const dataUrl = canvas.toDataURL("image/png");
        const newSnapshot = { ts: timeOnly(), cam: selectedCam, type, severity: severityFromScore(riskScore), dataUrl };
        setSnapshots(prev => [newSnapshot, ...prev].slice(0, 9));
    };

    /* Actions */
    const playBeep = () => {
        if (!soundEnabled) return;
        try {
            const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
            const o = ctx.createOscillator();
            const g = ctx.createGain();
            o.type = "sine";
            o.frequency.value = 880;
            g.gain.value = 0.08;
            o.connect(g);
            g.connect(ctx.destination);
            o.start();
            setTimeout(() => { o.stop(); ctx.close(); }, 180);
        } catch (e) { /* ignore */ }
    };

    const playSiren = () => {
        const utterance = new SpeechSynthesisUtterance("Warning. Threat detected.");
        utterance.rate = 1.2;
        window.speechSynthesis.speak(utterance);
        if (!soundEnabled) return;
        if (sirenAudioRef.current && sirenAudioRef.current.paused) {
            sirenAudioRef.current.play()
                .then(() => setAudioBlocked(false))
                .catch(() => setAudioBlocked(true));
            setSirenPlaying(true);
        }
    };

    const stopSiren = () => {
        if (sirenAudioRef.current) {
            sirenAudioRef.current.pause();
            sirenAudioRef.current.currentTime = 0;
            setSirenPlaying(false);
        }
        apiFetch('/control/siren', {
            method: 'POST',
            body: JSON.stringify({ state: 'OFF' })
        }).catch(() => { });
    };

    const lockGate = () => { setGateLocked(true); setRemoteStatus("Gate Locked ✅"); };
    const unlockGate = () => {
        if (role !== "ADMIN") return alert("Admin access required for unlock.");
        setGateLocked(false);
        setRemoteStatus("Unlocked ✅");
        stopSiren();
    };

    const sirenOn = () => {
        setRemoteStatus("Siren Activated ✅");
        playSiren();
        apiFetch('/control/siren', {
            method: 'POST',
            body: JSON.stringify({ state: 'ON' })
        }).catch(() => { });
    };

    /* Arduino Connect */
    const connectArduino = async () => {
        setArduinoConnecting(true);
        setArduinoMessage("Connecting...");
        try {
            const res = await apiFetch('/control/arduino/connect', {
                method: 'POST',
                body: JSON.stringify({ port: arduinoPortInput })
            });
            const data = await res.json();
            setHwConnected(data.success);
            setHwPort(data.port);
            setArduinoMessage(data.message);
            setRemoteStatus(data.success ? `Arduino connected on ${data.port} ✅` : `Connection failed ❌`);
        } catch (e) {
            setArduinoMessage("Backend unreachable. Is the server running?");
            setHwConnected(false);
        } finally {
            setArduinoConnecting(false);
        }
    };

    const checkArduinoStatus = async () => {
        try {
            const res = await apiFetch('/control/arduino/status');
            const data = await res.json();
            setHwConnected(data.connected);
            setHwPort(data.port);
        } catch { setHwConnected(false); }
    };

    /* Connect WebSockets */
    const connectWebSockets = useCallback(() => {
        // Close existing
        if (videoWsRef.current) videoWsRef.current.close();
        if (statusWsRef.current) statusWsRef.current.close();

        const videoWs = new WebSocket(wsUrl('/ws/video'));
        videoWsRef.current = videoWs;
        videoWs.onopen = () => { setIsConnected(true); setNetworkStatus("ONLINE"); };
        videoWs.onclose = () => { setIsConnected(false); setNetworkStatus("OFFLINE"); };
        videoWs.onmessage = (event) => {
            if (imgRef.current) {
                const prevUrl = imgRef.current.src;
                const newUrl = URL.createObjectURL(event.data);
                imgRef.current.src = newUrl;
                if (prevUrl && prevUrl.startsWith('blob:')) URL.revokeObjectURL(prevUrl);
            }
        };

        const statusWs = new WebSocket(wsUrl('/ws/status'));
        statusWsRef.current = statusWs;
        statusWs.onmessage = (event) => {
            const data = JSON.parse(event.data);
            const score = data.threat_score;
            setRiskScore(score);
            setHwConnected(data.hardware ?? false);
            if (data.reasons && data.reasons.length > 0) {
                setDetectionReasons(data.reasons);
                const firstReason = data.reasons[0];
                let type = "info";
                if (firstReason.toLowerCase().includes("weapon") || firstReason.toLowerCase().includes("gun")) type = "weapon";
                else if (firstReason.toLowerCase().includes("mask")) type = "mask";
                else if (firstReason.toLowerCase().includes("crowd")) type = "crowd";
                else if (firstReason.toLowerCase().includes("loiter")) type = "loitering";

                const newEntry: Log = {
                    ts: new Date().toLocaleTimeString(),
                    cam: selectedCam,
                    type,
                    conf: 0.9,
                    score,
                    severity: severityFromScore(score),
                    note: firstReason
                };
                setLogs(prev => {
                    const updated = [newEntry, ...prev].slice(0, 12);
                    updateThreatPattern(updated);
                    return updated;
                });
                if (score >= 75) {
                    playBeep();
                    if (autoLockEnabled && !gateLocked) lockGate();
                    saveSnapshot(type);
                }
            }
            if (data.lock_status === 'LOCKED') setGateLocked(true);
            if (data.siren && !sirenPlaying) { if (soundEnabled) playSiren(); }
            else if (!data.siren && sirenPlaying) { stopSiren(); }
        };
    }, [backendUrl]);

    /* Effects */
    useEffect(() => {
        sirenAudioRef.current = new Audio('/sounds/custom_siren.mp3');
        sirenAudioRef.current.loop = true;
        connectWebSockets();
        checkArduinoStatus();
        // Poll arduino status every 10s
        const poll = setInterval(checkArduinoStatus, 10000);
        return () => {
            clearInterval(poll);
            videoWsRef.current?.close();
            statusWsRef.current?.close();
        };
    }, [connectWebSockets]);

    /* Computed Styles */
    const radarX = 30 + (riskScore * 0.5);
    const radarY = 20 + (Math.abs(50 - riskScore) * 0.35);
    const dotColor = riskScore >= 75 ? "rgba(239,68,68,0.95)" : riskScore >= 40 ? "rgba(245,158,11,0.95)" : "rgba(16,185,129,0.95)";
    const camDetails = cameras.find(c => c.id === selectedCam);

    return (
        <main className="layout">
            <header className="topbar" style={{ gridColumn: "1 / -1" }}>
                <div className="brand">
                    <img src="/images/nextgen-logo.png" alt="Logo" className="ngd-logo" />
                    <div className="brand-text">
                        <h1>ARGUS <span style={{ fontSize: '0.6em', color: hwConnected ? '#10B981' : '#EF4444', border: '1px solid currentColor', borderRadius: '4px', padding: '2px 6px', marginLeft: '10px' }}>
                            {hwConnected ? `🟢 ARDUINO ${hwPort || 'ONLINE'}` : "🔴 ARDUINO OFF"}
                        </span></h1>
                        <p>AI-Powered Auto Theft Door Lock &amp; Surveillance</p>
                    </div>
                </div>
                <div className="top-right">
                    {/* Backend URL Config */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                        <button
                            onClick={() => setShowBackendInput(v => !v)}
                            style={{ fontSize: '10px', padding: '3px 8px', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '4px', color: '#aaa', cursor: 'pointer' }}
                        >
                            ⚙ Backend: {backendUrl.replace('http://', '').replace('https://', '')}
                        </button>
                        {showBackendInput && (
                            <div style={{ display: 'flex', gap: '4px' }}>
                                <input
                                    value={backendInput}
                                    onChange={e => setBackendInput(e.target.value)}
                                    placeholder="http://..."
                                    style={{ fontSize: '11px', padding: '2px 6px', background: 'rgba(0,0,0,0.5)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '4px', color: '#fff', width: '200px' }}
                                />
                                <button onClick={() => { setBackendUrl(backendInput); setShowBackendInput(false); connectWebSockets(); }}
                                    style={{ fontSize: '11px', padding: '2px 8px', background: '#10B981', border: 'none', borderRadius: '4px', color: '#fff', cursor: 'pointer' }}>Apply</button>
                            </div>
                        )}
                    </div>
                    <div className="chips">
                        <div className="chip">ATM-ID: <b>ATM-01</b></div>
                        <div className="chip">Role: <b>{role}</b></div>
                    </div>
                    <div className="statusRow">
                        <div className={`pill net ${networkStatus.toLowerCase()}`}>{networkStatus}</div>
                        <div className={`pill ${riskScore >= 75 ? 'crit' : riskScore >= 40 ? 'warn' : 'safe'}`}>
                            {riskScore >= 75 ? 'CRITICAL' : riskScore >= 40 ? 'WARNING' : 'SAFE'}
                        </div>
                    </div>
                </div>
            </header>

            <aside className="card sidebar">
                <div className="card-head">
                    <h2>Cameras</h2>
                    <span className="hint">Switch live feeds</span>
                </div>
                <div className="searchBox">
                    <input placeholder="Search camera…" value={camSearch} onChange={(e) => setCamSearch(e.target.value)} />
                </div>
                <div className="camList">
                    {cameras.filter(c => c.id.toLowerCase().includes(camSearch.toLowerCase()) || c.name.toLowerCase().includes(camSearch.toLowerCase())).map(c => (
                        <button key={c.id} className={`camBtn ${selectedCam === c.id ? 'active' : ''}`} onClick={() => setSelectedCam(c.id)}>
                            <div className="camTitle">{c.id}</div>
                            <div className="camSub">{c.name}</div>
                        </button>
                    ))}
                </div>
                <div className="divider"></div>
                <div className="card-head">
                    <h2>User &amp; Controls</h2>
                    <span className="hint">Access control</span>
                </div>
                <div className="roleBox">
                    <button className={`btn small ${role === 'GUARD' ? 'primary' : ''}`} onClick={() => setRole('GUARD')}>Guard View</button>
                    <button className={`btn small ${role === 'ADMIN' ? 'primary' : ''}`} onClick={() => setRole('ADMIN')}>Admin View</button>
                </div>
                <div className="toggleRow">
                    <label className="toggle">
                        <input type="checkbox" checked={soundEnabled} onChange={(e) => setSoundEnabled(e.target.checked)} />
                        <span className="slider"></span>
                    </label>
                    <div><div className="toggleTitle">Alert Sound</div><div className="toggleSub">Beep/Siren on CRITICAL</div></div>
                </div>
                <div className="toggleRow">
                    <label className="toggle">
                        <input type="checkbox" checked={autoLockEnabled} onChange={(e) => setAutoLockEnabled(e.target.checked)} />
                        <span className="slider"></span>
                    </label>
                    <div><div className="toggleTitle">Auto Gate Lock</div><div className="toggleSub">Lock when risk is high</div></div>
                </div>
                <div className="toggleRow">
                    <label className="toggle">
                        <input type="checkbox" checked={flashEnabled} onChange={(e) => setFlashEnabled(e.target.checked)} />
                        <span className="slider"></span>
                    </label>
                    <div><div className="toggleTitle">Visual Alerts</div><div className="toggleSub">Flash border on critical</div></div>
                </div>
            </aside>

            <section className={`card camera ${flashEnabled && riskScore >= 75 ? 'flash' : ''}`} id="cameraCard">
                <div className="card-head">
                    <h2>Live Camera Feed</h2>
                    <span className="hint">Real-time monitoring</span>
                </div>
                <div className="videoBox">
                    <div className="videoTop">
                        <div className="camLabel">{camDetails?.id} • {camDetails?.name}</div>
                        <div className="liveTag">LIVE</div>
                    </div>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img ref={imgRef} alt="Live Feed" className="w-full h-full object-contain absolute inset-0" style={{ zIndex: 1 }} />
                    {!isConnected && (
                        <div className="videoPlaceholder absolute inset-0 z-0">CCTV STREAM DISCONNECTED<br /><span style={{ fontSize: '12px', opacity: 0.6 }}>Backend: {backendUrl}</span></div>
                    )}
                </div>
                <div className="actionRow">
                    <button className="btn small" onClick={() => alert("Guard Notified")}>Notify Guard</button>
                    <button className="btn small danger" onClick={() => alert("Police Notified")}>Notify Police</button>
                    <button className="btn small" onClick={() => generateReport()}>Save Report</button>
                    <button className="btn small" onClick={() => saveSnapshot('manual')}>Snapshot</button>
                </div>
            </section>

            <aside className="card rightPanel" style={{ opacity: role === "GUARD" ? 0.9 : 1 }}>
                <div className="card-head">
                    <h2>Risk Intelligence</h2>
                    <span className="hint">Score + patterns</span>
                </div>
                <div className="riskBlock">
                    <div className="riskTop">
                        <div>
                            <div className="smallLabel">RISK LEVEL</div>
                            <div className="riskValue" style={{ color: riskScore >= 75 ? '#fecaca' : riskScore >= 40 ? '#fde68a' : '#a7f3d0' }}>{riskTextFromScore(riskScore)}</div>
                        </div>
                        <div className="riskScoreBox">
                            <div className="smallLabel">SCORE</div>
                            <div className="score">{riskScore}</div>
                        </div>
                    </div>
                    <div className="riskBar">
                        <div className="fill" style={{ width: `${riskScore}%`, background: riskFillColor(riskScore) }}></div>
                    </div>
                    <div className="pattern mt-3 text-xs opacity-80 italic">{threatPatternText}</div>
                </div>

                <div className="radarCard">
                    <div className="card-head compact">
                        <h2>Threat Heat Radar</h2>
                        <span className="hint">Visual indicator</span>
                    </div>
                    <div className="radar">
                        <div className="ring r1"></div>
                        <div className="ring r2"></div>
                        <div className="ring r3"></div>
                        <div className="sweep"></div>
                        <div className="dot" style={{ left: `${clamp(radarX, 15, 85)}%`, top: `${clamp(radarY, 15, 80)}%`, background: dotColor }}></div>
                    </div>
                </div>

                {/* ===== ARDUINO DOOR CONNECT CARD ===== */}
                <div className="remoteCard mt-4" style={{ borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: '12px' }}>
                    <div className="card-head">
                        <h2>🚪 Arduino Door</h2>
                        <span className="hint" style={{ color: hwConnected ? '#10B981' : '#EF4444', fontWeight: 700 }}>
                            {hwConnected ? `Connected · ${hwPort}` : 'Disconnected'}
                        </span>
                    </div>
                    <div style={{ display: 'flex', gap: '6px', marginBottom: '8px', alignItems: 'center' }}>
                        <input
                            value={arduinoPortInput}
                            onChange={e => setArduinoPortInput(e.target.value)}
                            placeholder="COM Port (e.g. COM9)"
                            style={{ flex: 1, padding: '5px 8px', fontSize: '12px', background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '6px', color: '#fff', outline: 'none' }}
                        />
                        <button
                            id="arduino-connect-btn"
                            onClick={connectArduino}
                            disabled={arduinoConnecting}
                            style={{
                                padding: '6px 12px',
                                fontSize: '12px',
                                fontWeight: 700,
                                background: hwConnected ? 'rgba(239,68,68,0.3)' : 'rgba(16,185,129,0.3)',
                                border: `1px solid ${hwConnected ? '#EF4444' : '#10B981'}`,
                                borderRadius: '6px',
                                color: hwConnected ? '#fca5a5' : '#6ee7b7',
                                cursor: arduinoConnecting ? 'wait' : 'pointer',
                                whiteSpace: 'nowrap',
                                transition: 'all 0.2s'
                            }}
                        >
                            {arduinoConnecting ? '⏳ Connecting...' : hwConnected ? '🔴 Reconnect' : '🟢 Connect'}
                        </button>
                    </div>
                    {arduinoMessage && (
                        <div style={{ fontSize: '11px', padding: '4px 8px', background: hwConnected ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)', borderRadius: '4px', color: hwConnected ? '#6ee7b7' : '#fca5a5', marginBottom: '8px' }}>
                            {arduinoMessage}
                        </div>
                    )}
                </div>

                {/* Remote Control */}
                <div className="remoteCard mt-3">
                    <div className="card-head">
                        <h2>Remote Control</h2>
                        <span className="hint">IoT Actions ({gateLocked ? "LOCKED 🔒" : "UNLOCKED 🔓"})</span>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                        <button className="btn small danger font-bold" onClick={() => lockGate()}>LOCK GATE</button>
                        <button className="btn small primary font-bold" onClick={() => unlockGate()}>UNLOCK</button>
                        <button className={`btn small font-bold ${sirenPlaying ? 'danger animate-pulse' : ''}`} onClick={() => sirenOn()}>SIREN ON</button>
                        <button className="btn small" onClick={() => stopSiren()}>SILENCE</button>
                    </div>
                    <div className="remoteStatus mt-2 text-xs opacity-70">Status: {remoteStatus}</div>

                    <div className="ackBox mt-3 border-t border-white/5 pt-3">
                        <div className="smallLabel">Acknowledgement</div>
                        <div className="flex gap-2 mt-1">
                            <input
                                className="bg-black/40 border border-white/10 rounded px-2 py-1 text-xs w-full outline-none"
                                placeholder="Officer name..."
                                value={ackText}
                                onChange={(e) => setAckText(e.target.value)}
                            />
                            <button className="btn small primary" onClick={() => { setAckLog(`Ack by ${ackText || 'Officer'} at ${new Date().toLocaleTimeString()}`); setAckText(""); }}>Ack</button>
                        </div>
                        <div className="ackLog mt-1 text-[10px] opacity-60">{ackLog}</div>
                    </div>
                </div>

                <button className="btn panic mt-4" onClick={() => { setRiskScore(95); playBeep(); if (autoLockEnabled) lockGate(); }}>MANUAL EMERGENCY LOCKDOWN</button>
            </aside>

            <section className="card bottomWide">
                <div className="bottomGrid">
                    <div className="panel">
                        <div className="card-head">
                            <h2>Live Detections</h2>
                            <span className="hint">Latest threats</span>
                        </div>
                        <ul className="detList" style={{ maxHeight: '120px', overflowY: 'auto' }}>
                            {logs.length === 0 ? (
                                <li className="mutedItem">No threats detected</li>
                            ) : (
                                logs.map((l, i) => (
                                    <li key={i} className="detItem">
                                        <div className="detLeft">
                                            <b>{l.note}</b>
                                            <div className="detMeta">Cam: {l.cam} • {l.ts}</div>
                                        </div>
                                        <span className={`badge ${l.type}`}>{l.type.toUpperCase()}</span>
                                    </li>
                                ))
                            )}
                        </ul>
                    </div>

                    <div className="panel">
                        <div className="card-head">
                            <h2>Threat Timeline</h2>
                            <span className="hint">Recent activity</span>
                        </div>
                        <div className="timeline flex gap-2 flex-wrap">
                            {logs.length === 0 ? (
                                <div className="timelineEmpty text-xs opacity-50">Recording telemetry...</div>
                            ) : (
                                logs.map((l, i) => (
                                    <div key={i} className={`tDot ${l.severity}`} title={`${l.ts}: ${l.note}`}></div>
                                ))
                            )}
                        </div>
                    </div>

                    <div className="panel">
                        <div className="card-head">
                            <h2>Safety Snapshots</h2>
                            <span className="hint">Auto-captured</span>
                        </div>
                        <div className="snapGrid grid grid-cols-3 gap-2">
                            {snapshots.length === 0 ? (
                                <div className="mutedBox text-[10px]">No snapshots</div>
                            ) : (
                                snapshots.map((s, i) => (
                                    <div key={i} className="snap relative aspect-video bg-black/40 rounded overflow-hidden cursor-pointer" onClick={() => window.open(s.dataUrl, '_blank')}>
                                        {/* eslint-disable-next-line @next/next/no-img-element */}
                                        <img src={s.dataUrl} className="w-full h-full object-cover" alt="snapshot" />
                                        <div className="absolute bottom-0 left-0 right-0 bg-black/60 text-[8px] p-0.5 text-center">{s.ts}</div>
                                    </div>
                                ))
                            )}
                        </div>
                    </div>
                </div>
            </section>

            <canvas ref={canvasRef} style={{ display: 'none' }} />
        </main>
    );
}
